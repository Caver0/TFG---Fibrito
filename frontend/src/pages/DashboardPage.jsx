import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Scatter,
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
  formatCalories,
  formatCompactNumber,
  formatDateLabel,
  formatGoalLabel,
  formatMass,
  formatPercent,
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

function getRelativeDayLabel(value) {
  if (!value) {
    return 'Esperando eventos de ajuste'
  }

  const targetDate = new Date(value)
  if (Number.isNaN(targetDate.getTime())) {
    return 'Esperando eventos de ajuste'
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
    return 'Esperando ventana semanal completa'
  }

  if (analysis.adjustment_needed) {
    return analysis.progress_status === 'needs_adjustment'
      ? 'Ventana de ajuste detectada'
      : analysis.adjustment_reason
  }

  if (analysis.progress_status === 'on_track') {
    return 'Rango objetivo alcanzado'
  }

  return analysis.adjustment_reason || 'Análisis semanal listo'
}

function buildWeightChartPayload(weightProgress) {
  const entries = Array.isArray(weightProgress?.entries) ? weightProgress.entries : []
  const weeklyAverages = Array.isArray(weightProgress?.weekly_averages) ? weightProgress.weekly_averages : []
  const adjustmentEvents = Array.isArray(weightProgress?.adjustment_events) ? weightProgress.adjustment_events : []

  const sourcePoints = entries.length > 0
    ? entries.map((point) => ({
        chartDate: point.date,
        axisLabel: formatDateLabel(point.date),
        weight: Number(point.weight),
      }))
    : weeklyAverages.map((point) => ({
        chartDate: point.end_date,
        axisLabel: point.week_label,
        weight: Number(point.average_weight),
      }))

  const byDate = Object.fromEntries(sourcePoints.map((point) => [point.chartDate, point]))

  const adjustmentPoints = adjustmentEvents
    .map((event) => {
      const matchedPoint = byDate[event.date]
      return {
        chartDate: event.date,
        axisLabel: matchedPoint?.axisLabel ?? formatDateLabel(event.date),
        adjustmentWeight: Number(event.reference_weight ?? matchedPoint?.weight ?? sourcePoints[sourcePoints.length - 1]?.weight ?? 0),
        calorieChange: event.calorie_change,
      }
    })
    .filter((point) => Number.isFinite(point.adjustmentWeight))

  return {
    sourcePoints,
    adjustmentPoints,
  }
}

function DashboardTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null
  }

  const weightPoint = payload.find((entry) => entry.dataKey === 'weight')
  const adjustmentPoint = payload.find((entry) => entry.dataKey === 'adjustmentWeight')

  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {weightPoint ? <p>Peso: {formatMass(weightPoint.value)}</p> : null}
      {adjustmentPoint ? <p>Ajuste: {adjustmentPoint.payload.calorieChange > 0 ? '+' : ''}{adjustmentPoint.payload.calorieChange} kcal</p> : null}
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

  const metricCards = [
    {
      title: 'Peso Actual',
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
      title: 'Cambio Semanal',
      value: formatCompactNumber(summary?.latest_weekly_change, { maximumFractionDigits: 1, minimumFractionDigits: 1 }),
      suffix: 'KG / SEM',
      note: getProgressStatusNote(latestAnalysis).toUpperCase(),
      noteTone: latestAnalysis?.adjustment_needed ? 'danger' : 'accent',
      icon: 'trending_down',
    },
    {
      title: 'Calorías Objetivo',
      value: formatCompactNumber(summary?.current_target_calories, { maximumFractionDigits: 0 }),
      suffix: 'KCAL',
      note: getRelativeDayLabel(latestAdjustmentEvent?.date).toUpperCase(),
      noteTone: latestAdjustmentEvent ? 'danger' : 'muted',
      icon: 'bolt',
    },
    {
      title: '% Adherencia',
      value: formatCompactNumber(summary?.weekly_adherence_percentage, { maximumFractionDigits: 1, minimumFractionDigits: 1 }),
      suffix: '%',
      note: (summary?.adherence_interpretation || 'Resumen de cumplimiento semanal').toUpperCase(),
      noteTone: 'accent',
      icon: 'verified',
    },
  ]

  const dietMacroRows = [
    {
      key: 'protein',
      label: 'Proteína',
      current: activeDiet?.protein_grams ?? summary?.current_macros?.protein_grams,
      target: summary?.current_macros?.protein_grams ?? activeDiet?.protein_grams,
    },
    {
      key: 'carbs',
      label: 'Carbohidratos',
      current: activeDiet?.carb_grams ?? summary?.current_macros?.carb_grams,
      target: summary?.current_macros?.carb_grams ?? activeDiet?.carb_grams,
    },
    {
      key: 'fat',
      label: 'Grasas',
      current: activeDiet?.fat_grams ?? summary?.current_macros?.fat_grams,
      target: summary?.current_macros?.fat_grams ?? activeDiet?.fat_grams,
    },
  ]

  const dietMeals = activeDiet?.calories_per_meal?.slice(0, 3) ?? []
  const insightRows = [
    {
      label: 'Protocolo objetivo',
      value: formatGoalLabel(summary?.goal),
    },
    {
      label: 'Comidas planeadas',
      value: activeDiet?.meals_count ? `${activeDiet.meals_count}` : 'N/A',
    },
    {
      label: 'Comidas registradas',
      value: adherence?.total_meals_registered ? `${adherence.total_meals_registered}` : '0',
    },
    {
      label: 'Cobertura',
      value: formatPercent(adherence?.tracking_coverage_percentage ?? 0, 0),
    },
  ]

  const logItems = weightProgress?.adjustment_events?.slice(-3).reverse() ?? []

  return (
    <div className="dashboard-page">
      {isLoading ? <p className="page-status">Cargando núcleo del panel...</p> : null}
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
                title="Velocidad de Masa Corporal"
                description="PESO A LO LARGO DEL TIEMPO VS AJUSTES CALÓRICOS"
                actions={(
                  <div className="legend-group">
                    <span><i className="legend-dot legend-dot-primary" />Peso</span>
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
                          dataKey="axisLabel"
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
                          dot={false}
                          activeDot={{ r: 4, fill: '#f6ffc0', stroke: '#daf900', strokeWidth: 2 }}
                        />
                        <Scatter data={chartPayload.adjustmentPoints} dataKey="adjustmentWeight" fill="#ff7162">
                          <LabelList
                            dataKey="calorieChange"
                            position="top"
                            formatter={(value) => `${value > 0 ? '+' : ''}${value} KCAL`}
                            style={{ fill: '#ff7162', fontSize: 10, fontWeight: 700 }}
                          />
                        </Scatter>
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="panel-placeholder">Los datos de peso aparecerán aquí después de tus primeros registros.</p>
                  )}
                </div>
              </SectionPanel>

              <SectionPanel
                title="Protocolo de Dieta Activo"
                actions={(
                  <span className="panel-tag">
                    {activeDiet ? 'CALIBRACIÓN_EN_VIVO' : 'SIN DIETA ACTIVA'}
                  </span>
                )}
              >
                {activeDiet ? (
                  <div className="dashboard-diet-grid">
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

                    <div className="dashboard-meal-stack">
                      {dietMeals.map((meal) => (
                        <article key={meal.meal_number} className="dashboard-meal-preview">
                          <div>
                            <small>{`COMIDA ${String(meal.meal_number).padStart(2, '0')}`}</small>
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
                  <p className="panel-placeholder">Genera una dieta para poblar el bloque de protocolo activo.</p>
                )}
              </SectionPanel>
            </div>

            <div className="dashboard-side-column">
              <SectionPanel eyebrow="Cumplimiento Semanal" className="dashboard-gauge-panel">
                <CircularGauge
                  value={adherence?.adherence_percentage ?? 0}
                  label="Consistencia"
                />

                <div className="interpretation-card">
                  <span>Interpretación de IA</span>
                  <p>{summary?.adherence_interpretation || adherence?.interpretation_message || 'Los datos de adherencia guiarán esta interpretación una vez que se registren comidas.'}</p>
                </div>
              </SectionPanel>

              <SectionPanel eyebrow="Métricas de Protocolo">
                <div className="key-value-stack">
                  {insightRows.map((row) => (
                    <div key={row.label} className="key-value-row">
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </div>
                  ))}
                </div>

                <button type="button" className="panel-cta-button" onClick={() => { window.location.hash = '#progress' }}>
                  Ver Datos de Laboratorio
                </button>
              </SectionPanel>

              <SectionPanel eyebrow="Registros del Sistema">
                {logItems.length > 0 ? (
                  <div className="system-log-list">
                    {logItems.map((item) => (
                      <article key={item.id} className="system-log-item">
                        <small>{item.calorie_change === 0 ? 'EVENTO DE ANÁLISIS' : 'EVENTO DE AJUSTE'}</small>
                        <strong>{item.adjustment_reason}</strong>
                        <p>{formatDateLabel(item.date, { month: 'short', day: '2-digit', year: 'numeric' })}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="panel-placeholder">Los eventos de ajuste se listarán aquí después de aplicar el análisis semanal.</p>
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
