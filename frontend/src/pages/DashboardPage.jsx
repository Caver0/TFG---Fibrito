import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import * as dashboardApi from '../api/dashboardApi'
import CircularGauge from '../components/CircularGauge'
import MetricCard from '../components/MetricCard'
import SectionPanel from '../components/SectionPanel'
import { useAuth } from '../context/AuthContext'
import {
  clampPercentage,
  formatCompactNumber,
  formatDateLabel,
  formatGoalLabel,
  formatMass,
  formatPercent,
  resolveConfidencePercentage,
  resolveRegisteredAdherencePercentage,
  formatSignedMass,
} from '../utils/stitch'

function getLatestDelta(entries) {
  if (!Array.isArray(entries) || entries.length < 2) {
    return null
  }

  const lastEntry = entries[entries.length - 1]
  const previousEntry = entries[entries.length - 2]
  if (lastEntry?.weight === undefined || previousEntry?.weight === undefined) {
    return null
  }

  return Number(lastEntry.weight) - Number(previousEntry.weight)
}

function buildTimestamp(value) {
  const parsedDate = new Date(value)
  const timestamp = parsedDate.getTime()
  return Number.isNaN(timestamp) ? null : timestamp
}

function getRelativeDayLabel(value) {
  if (!value) {
    return 'Esperando ajustes'
  }

  const targetDate = new Date(value)
  if (Number.isNaN(targetDate.getTime())) {
    return 'Esperando ajustes'
  }

  const today = new Date()
  const oneDay = 24 * 60 * 60 * 1000
  const differenceInDays = Math.max(0, Math.round((today.setHours(0, 0, 0, 0) - targetDate.setHours(0, 0, 0, 0)) / oneDay))

  if (differenceInDays === 0) {
    return 'Ajustado hoy'
  }
  if (differenceInDays === 1) {
    return 'Ajustado hace 1 día'
  }

  return `Ajustado hace ${differenceInDays} días`
}

function getProgressStatusNote(analysis) {
  if (!analysis?.can_analyze) {
    return 'Esperando semana de referencia completa'
  }

  if (analysis.adjustment_needed) {
    return analysis.progress_status === 'needs_adjustment'
      ? 'Se recomienda ajuste'
      : analysis.adjustment_reason
  }

  if (analysis.progress_status === 'on_track') {
    return 'Dentro del rango objetivo'
  }

  return analysis.adjustment_reason || 'Revisión semanal lista'
}

function buildWeightChartPayload(weightProgress) {
  const entries = Array.isArray(weightProgress?.entries) ? weightProgress.entries : []
  const weeklyAverages = Array.isArray(weightProgress?.weekly_averages) ? weightProgress.weekly_averages : []
  const adjustmentEvents = Array.isArray(weightProgress?.adjustment_events) ? weightProgress.adjustment_events : []
  const regressionTrend = Array.isArray(weightProgress?.regression_trend) ? weightProgress.regression_trend : []

  const pointsByDate = new Map()

  const historicalPoints = (
    entries.length > 0
      ? entries.map((point) => ({
          chartDate: point.date,
          timestamp: buildTimestamp(point.date),
          weight: Number(point.weight),
        }))
      : weeklyAverages.map((point) => ({
          chartDate: point.end_date,
          timestamp: buildTimestamp(point.end_date),
          weight: Number(point.average_weight),
        }))
  ).filter((point) => point.timestamp !== null)

  for (const point of historicalPoints) {
    pointsByDate.set(point.chartDate, point)
  }

  for (const point of regressionTrend) {
    if (point.is_projection) {
      continue
    }

    const existing = pointsByDate.get(point.date)
    if (existing) {
      existing.regressionWeight = Number(point.weight)
    }
  }

  const lastHistoricalRegression = [...regressionTrend].reverse().find((point) => !point.is_projection)
  if (lastHistoricalRegression) {
    const existing = pointsByDate.get(lastHistoricalRegression.date)
    if (existing) {
      existing.projectedWeight = Number(lastHistoricalRegression.weight)
    }
  }

  const projectionPoints = regressionTrend
    .filter((point) => point.is_projection)
    .map((point) => ({
      chartDate: point.date,
      timestamp: buildTimestamp(point.date),
      projectedWeight: Number(point.weight),
    }))
    .filter((point) => point.timestamp !== null)

  const sourcePoints = [...historicalPoints, ...projectionPoints]
    .sort((left, right) => left.timestamp - right.timestamp)

  if (sourcePoints.length === 0) {
    return { sourcePoints: [] }
  }

  for (const event of adjustmentEvents) {
    const eventTime = buildTimestamp(event.date)
    if (eventTime === null) {
      continue
    }

    let closest = historicalPoints[0] ?? sourcePoints[0]
    let minDiff = Math.abs(closest.timestamp - eventTime)

    for (const point of historicalPoints) {
      const diff = Math.abs(point.timestamp - eventTime)
      if (diff < minDiff) {
        minDiff = diff
        closest = point
      }
    }

    closest.calorieChange = event.calorie_change
    closest.adjustmentLabel = `${event.calorie_change > 0 ? '+' : ''}${event.calorie_change} KCAL`
  }

  return { sourcePoints }
}

function DashboardTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null
  }

  const weightPoint = payload.find((entry) => entry.dataKey === 'weight')
  const regressionPoint = payload.find((entry) => entry.dataKey === 'regressionWeight')
  const projectionPoint = payload.find((entry) => entry.dataKey === 'projectedWeight')
  const calorieChange = weightPoint?.payload?.calorieChange
  const pointDate = payload[0]?.payload?.chartDate

  return (
    <div className="chart-tooltip">
      <strong>{formatDateLabel(pointDate, { month: 'short', day: '2-digit', year: 'numeric' })}</strong>
      {weightPoint ? <p>Peso real: {formatMass(weightPoint.value)}</p> : null}
      {regressionPoint ? <p>Tendencia: {formatMass(regressionPoint.value)}</p> : null}
      {projectionPoint ? <p>Proyección: {formatMass(projectionPoint.value)}</p> : null}
      {calorieChange !== undefined ? <p>Ajuste: {calorieChange > 0 ? '+' : ''}{calorieChange} kcal</p> : null}
    </div>
  )
}

function DashboardPage() {
  const { token } = useAuth()
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function loadOverview(activeToken = token) {
    if (!activeToken) {
      return null
    }

    setIsLoading(true)
    setError('')

    try {
      const response = await dashboardApi.getDashboardOverview(activeToken)
      setOverview(response)
      return response
    } catch (loadError) {
      setOverview(null)
      setError(loadError.message)
      return null
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!token) {
      return
    }

    loadOverview(token)
  }, [token])

  useEffect(() => {
    if (!token) {
      return undefined
    }

    function handleDashboardRefresh() {
      loadOverview(token)
    }

    window.addEventListener('dashboard:refresh', handleDashboardRefresh)
    window.addEventListener('adherence:updated', handleDashboardRefresh)

    return () => {
      window.removeEventListener('dashboard:refresh', handleDashboardRefresh)
      window.removeEventListener('adherence:updated', handleDashboardRefresh)
    }
  }, [token])

  const summary = overview?.summary ?? null
  const weightProgress = overview?.weight_progress ?? null
  const adherence = overview?.adherence ?? null
  const activeDiet = overview?.active_diet ?? null
  const latestAnalysis = weightProgress?.latest_analysis ?? null
  const latestAdjustmentEvent = weightProgress?.adjustment_events?.[weightProgress.adjustment_events.length - 1] ?? null
  const lastEntryDelta = getLatestDelta(weightProgress?.entries ?? [])
  const chartPayload = buildWeightChartPayload(weightProgress)
  const adherenceWeekLabel = adherence?.week_label ?? latestAnalysis?.current_week_label ?? null
  const confidenceScore = resolveConfidencePercentage(adherence)
  const registeredAdherenceScore = resolveRegisteredAdherencePercentage(adherence)

  const metricCards = [
    {
      title: 'Peso actual',
      value: formatCompactNumber(summary?.current_weight, { maximumFractionDigits: 1, minimumFractionDigits: 1 }),
      suffix: 'KG',
      note: lastEntryDelta === null
        ? 'Esperando más pesajes'
        : `${formatSignedMass(lastEntryDelta, { maximumFractionDigits: 1, minimumFractionDigits: 1 }).toUpperCase()} DESDE EL ÚLTIMO REGISTRO`,
      noteTone: lastEntryDelta !== null && lastEntryDelta > 0 ? 'danger' : 'accent',
      icon: 'monitor_weight',
      highlight: true,
    },
    {
      title: 'Cambio semanal',
      value: formatCompactNumber(summary?.latest_weekly_change, { maximumFractionDigits: 1, minimumFractionDigits: 1 }),
      suffix: 'KG / SEM',
      note: getProgressStatusNote(latestAnalysis).toUpperCase(),
      noteTone: latestAnalysis?.adjustment_needed ? 'danger' : 'accent',
      icon: 'trending_down',
    },
    {
      title: 'Calorías objetivo',
      value: formatCompactNumber(activeDiet?.target_calories ?? summary?.current_target_calories, { maximumFractionDigits: 0 }),
      suffix: 'KCAL',
      note: getRelativeDayLabel(latestAdjustmentEvent?.date).toUpperCase(),
      noteTone: latestAdjustmentEvent ? 'danger' : 'muted',
      icon: 'bolt',
    },
    {
      title: 'Fiabilidad',
      value: formatCompactNumber(confidenceScore, { maximumFractionDigits: 1, minimumFractionDigits: 1 }),
      suffix: '%',
      note: (adherenceWeekLabel ? `Semana ${adherenceWeekLabel}` : 'Esperando datos semanales').toUpperCase(),
      noteTone: 'accent',
      icon: 'verified',
    },
  ]

  const dietMacroRows = [
    {
      key: 'protein',
      label: 'Proteína',
      current: activeDiet?.actual_protein_grams ?? activeDiet?.protein_grams ?? summary?.current_macros?.protein_grams,
      target: activeDiet?.protein_grams ?? summary?.current_macros?.protein_grams,
    },
    {
      key: 'carbs',
      label: 'Carbohidratos',
      current: activeDiet?.actual_carb_grams ?? activeDiet?.carb_grams ?? summary?.current_macros?.carb_grams,
      target: activeDiet?.carb_grams ?? summary?.current_macros?.carb_grams,
    },
    {
      key: 'fat',
      label: 'Grasas',
      current: activeDiet?.actual_fat_grams ?? activeDiet?.fat_grams ?? summary?.current_macros?.fat_grams,
      target: activeDiet?.fat_grams ?? summary?.current_macros?.fat_grams,
    },
  ]

  const dietMeals = activeDiet?.calories_per_meal ?? []
  const hasExtendedDietMeals = dietMeals.length > 3
  const insightRows = [
    {
      label: 'Objetivo',
      value: formatGoalLabel(summary?.goal),
    },
    {
      label: 'Semana de referencia',
      value: adherenceWeekLabel ?? 'N/A',
    },
    {
      label: 'Comidas planificadas',
      value: activeDiet?.meals_count ? `${activeDiet.meals_count}` : 'N/A',
    },
    {
      label: 'Comidas registradas',
      value: adherence ? `${adherence.total_meals_registered ?? 0} / ${adherence.total_planned_meals ?? 0}` : '0 / 0',
    },
    {
      label: 'Cobertura',
      value: formatPercent(adherence?.tracking_coverage_percentage ?? 0, 0),
    },
    {
      label: 'Adherencia registrada',
      value: formatPercent(registeredAdherenceScore, 0),
    },
  ]

  const logItems = weightProgress?.adjustment_events?.slice(-3).reverse() ?? []

  return (
    <div className="dashboard-page">
      {isLoading ? <p className="page-status">Cargando panel...</p> : null}
      {!isLoading && error ? <p className="page-status page-status-error">{error}</p> : null}

      {!isLoading && !error ? (
        <>
          <div className="metric-card-grid">
            {metricCards.map((card) => (
              <MetricCard key={card.title} {...card} />
            ))}
          </div>

          <div className="dashboard-main-layout">
            <div className="dashboard-main-column">
              <SectionPanel
                title="Evolución del peso"
                description="Peso a lo largo del tiempo y ajustes calóricos"
                actions={(
                  <div className="legend-group">
                    <span><i className="legend-dot legend-dot-primary" />Peso</span>
                    <span><i className="legend-dot legend-dot-info" />Tendencia</span>
                    <span><i className="legend-dot legend-dot-info legend-dot-dashed" />Proyección</span>
                    <span><i className="legend-dot legend-dot-danger" />Ajuste</span>
                  </div>
                )}
              >
                <div className="dashboard-chart-wrap">
                  {chartPayload.sourcePoints.length > 0 ? (
                    <ResponsiveContainer width="100%" height={360}>
                      <ComposedChart data={chartPayload.sourcePoints}>
                        <CartesianGrid stroke="rgba(118, 117, 118, 0.18)" strokeDasharray="4 6" vertical={false} />
                        <XAxis
                          dataKey="timestamp"
                          type="number"
                          scale="time"
                          domain={['dataMin', 'dataMax']}
                          tickFormatter={(value) => formatDateLabel(value)}
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: '#adacab', fontSize: 10, fontWeight: 700 }}
                        />
                        <YAxis hide domain={['auto', 'auto']} />
                        <Tooltip content={<DashboardTooltip />} />
                        <Line
                          type="monotone"
                          dataKey="weight"
                          stroke="#daf900"
                          strokeWidth={3}
                          connectNulls={false}
                          dot={(props) => {
                            if (props.payload?.calorieChange === undefined) return null
                            return <circle key={props.key} cx={props.cx} cy={props.cy} r={7} fill="#ff7162" stroke="#ff7162" strokeWidth={2} />
                          }}
                          activeDot={{ r: 4, fill: '#f6ffc0', stroke: '#daf900', strokeWidth: 2 }}
                        >
                          <LabelList
                            dataKey="adjustmentLabel"
                            position="top"
                            style={{ fill: '#ff7162', fontSize: 10, fontWeight: 700 }}
                            formatter={(value) => value ?? ''}
                          />
                        </Line>
                        <Line
                          type="linear"
                          dataKey="regressionWeight"
                          stroke="#00d4ff"
                          strokeWidth={2}
                          dot={false}
                          activeDot={false}
                          connectNulls={false}
                        />
                        <Line
                          type="linear"
                          dataKey="projectedWeight"
                          stroke="#00d4ff"
                          strokeWidth={2}
                          strokeDasharray="6 4"
                          dot={false}
                          activeDot={false}
                          connectNulls={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="panel-placeholder">Los datos de peso aparecerán aquí después de tus primeros registros.</p>
                  )}
                </div>
              </SectionPanel>

              <SectionPanel
                title="Dieta activa"
                actions={(
                  <span className="panel-tag">
                    {activeDiet ? 'ACTIVA' : 'SIN DIETA ACTIVA'}
                  </span>
                )}
              >
                {activeDiet ? (
                  <div className={`dashboard-diet-grid ${hasExtendedDietMeals ? 'dashboard-diet-grid-extended' : ''}`.trim()}>
                    <div className="dashboard-macro-stack">
                      {dietMacroRows.map((macro) => {
                        const currentValue = Number(macro.current ?? 0)
                        const targetValue = Number((macro.target ?? currentValue) || 0)
                        const progress = targetValue > 0 ? (currentValue / targetValue) * 100 : 0

                        return (
                          <div className="macro-line" key={macro.key}>
                            <div className="macro-line-head">
                              <span>{macro.label}</span>
                              <strong>{formatMacroLine(currentValue, targetValue)}</strong>
                            </div>
                            <div className="macro-line-track">
                              <div className="macro-line-fill" style={{ width: `${clampPercentage(progress, 100)}%` }} />
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    <div className={`dashboard-meal-stack ${hasExtendedDietMeals ? 'dashboard-meal-stack-extended' : ''}`.trim()}>
                      {dietMeals.map((meal) => (
                        <article key={meal.meal_number} className="dashboard-meal-preview">
                          <div>
                            <small>{`Comida ${String(meal.meal_number).padStart(2, '0')}`}</small>
                            <strong>{meal.label}</strong>
                          </div>
                          <p>
                            {formatCompactNumber(meal.actual_calories || meal.target_calories, { maximumFractionDigits: 0 })}
                            <span>KCAL</span>
                          </p>
                        </article>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="panel-placeholder">Genera una dieta para ver aquí su resumen.</p>
                )}
              </SectionPanel>
            </div>

            <div className="dashboard-side-column">
              <SectionPanel eyebrow="Fiabilidad" className="dashboard-gauge-panel">
                <CircularGauge
                  value={confidenceScore}
                  label="Fiabilidad"
                  caption={adherenceWeekLabel ? `Semana ${adherenceWeekLabel}` : undefined}
                />

                <div className="interpretation-card">
                  <span>{adherenceWeekLabel ? `Semana ${adherenceWeekLabel}` : 'Interpretación semanal'}</span>
                  <p>{summary?.adherence_interpretation || adherence?.interpretation_message || 'Los datos de adherencia aparecerán aquí cuando empieces a registrar comidas.'}</p>
                </div>
              </SectionPanel>

              <SectionPanel eyebrow="Resumen">
                <div className="key-value-stack">
                  {insightRows.map((row) => (
                    <div key={row.label} className="key-value-row">
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </div>
                  ))}
                </div>

                <button type="button" className="panel-cta-button" onClick={() => { window.location.hash = '#progress' }}>
                  Ver progreso
                </button>
              </SectionPanel>

              <SectionPanel eyebrow="Últimos ajustes">
                {logItems.length > 0 ? (
                  <div className="system-log-list">
                    {logItems.map((item) => (
                      <article key={item.id} className="system-log-item">
                        <small>{item.calorie_change === 0 ? 'Análisis' : 'Ajuste'}</small>
                        <strong>{item.adjustment_reason}</strong>
                        <p>{formatDateLabel(item.date, { month: 'short', day: '2-digit', year: 'numeric' })}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="panel-placeholder">Los ajustes semanales aparecerán aquí cuando estén disponibles.</p>
                )}
              </SectionPanel>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}

function formatMacroLine(currentValue, targetValue) {
  return `${formatCompactNumber(currentValue, { maximumFractionDigits: 0 })}g / ${formatCompactNumber(targetValue, { maximumFractionDigits: 0 })}g`
}

export default DashboardPage
