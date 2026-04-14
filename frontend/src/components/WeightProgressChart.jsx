import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  formatCalories,
  formatLongDate,
  formatShortDate,
  formatSignedWeight,
  formatWeight,
} from '../utils/dashboardFormat'

function buildTimestamp(value) {
  const parsedDate = new Date(value)
  return parsedDate.getTime()
}

function buildTooltipContent({ active, label, payload }) {
  if (!active || !payload?.length) {
    return null
  }

  const weightEntry = payload.find((item) => item.dataKey === 'weight')?.payload
  const weeklyAverage = payload.find((item) => item.dataKey === 'average_weight')?.payload
  const expectedTrend = payload.find((item) => item.dataKey === 'expected_weight')?.payload
  const adjustmentEvent = payload.find((item) => item.dataKey === 'reference_weight')?.payload

  return (
    <div className="chart-tooltip">
      <strong>{formatLongDate(label)}</strong>
      {weightEntry ? <p>Peso en ayunas: {formatWeight(weightEntry.weight)}</p> : null}
      {weeklyAverage ? (
        <p>
          Media semanal ({weeklyAverage.week_label}): {formatWeight(weeklyAverage.average_weight)}
        </p>
      ) : null}
      {expectedTrend ? <p>Referencia esperada: {formatWeight(expectedTrend.expected_weight)}</p> : null}
      {adjustmentEvent ? (
        <>
          <p>
            Ajuste calorico: {formatCalories(adjustmentEvent.previous_target_calories)} {'->'}{' '}
            {formatCalories(adjustmentEvent.new_target_calories)}
          </p>
          <p>{adjustmentEvent.adjustment_reason}</p>
        </>
      ) : null}
    </div>
  )
}

function WeightProgressChart({ weightProgress }) {
  const entries = weightProgress?.entries ?? []
  const weeklyAverages = weightProgress?.weekly_averages ?? []
  const expectedTrend = weightProgress?.expected_trend ?? []
  const adjustmentEvents = weightProgress?.adjustment_events ?? []
  const latestAnalysis = weightProgress?.latest_analysis ?? null

  const entriesData = entries.map((entry) => ({
    ...entry,
    timestamp: buildTimestamp(entry.date),
  }))
  const weeklyAveragesData = weeklyAverages.map((average) => ({
    ...average,
    timestamp: buildTimestamp(average.end_date),
  }))
  const expectedTrendData = expectedTrend.map((point) => ({
    ...point,
    timestamp: buildTimestamp(point.date),
  }))
  const adjustmentEventsData = adjustmentEvents.map((event) => ({
    ...event,
    timestamp: buildTimestamp(event.date),
  }))
  const recentEvents = [...adjustmentEvents].slice(-3).reverse()
  const hasChartData = entriesData.length > 0 || weeklyAveragesData.length > 0

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Progreso corporal</span>
        <h2>Evolucion del peso</h2>
        <p>La grafica une registros diarios, media semanal y los reajustes caloricos que marcaron momentos clave del proceso.</p>
      </div>

      {!hasChartData ? (
        <p className="info-note">Necesitamos registros de peso para construir la grafica principal del dashboard.</p>
      ) : (
        <div className="dashboard-chart-panel">
          <div className="dashboard-chart-legend">
            <span><i className="legend-dot legend-dot-weight" /> Peso diario</span>
            <span><i className="legend-dot legend-dot-weekly" /> Media semanal</span>
            {expectedTrendData.length > 0 ? <span><i className="legend-dot legend-dot-expected" /> Referencia esperada</span> : null}
            {adjustmentEventsData.length > 0 ? <span><i className="legend-dot legend-dot-adjustment" /> Ajustes caloricos</span> : null}
          </div>

          <div className="dashboard-chart-shell">
            <ResponsiveContainer width="100%" height={360}>
              <ComposedChart margin={{ top: 12, right: 18, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="rgba(152, 176, 214, 0.16)" strokeDasharray="4 4" />
                <XAxis
                  dataKey="timestamp"
                  domain={['dataMin', 'dataMax']}
                  scale="time"
                  type="number"
                  tickFormatter={(value) => formatShortDate(value)}
                  tick={{ fill: '#8fa0bd', fontSize: 12 }}
                />
                <YAxis
                  tickFormatter={(value) => `${Number(value).toFixed(1)} kg`}
                  tick={{ fill: '#8fa0bd', fontSize: 12 }}
                  width={82}
                />
                <Tooltip content={buildTooltipContent} labelFormatter={(value) => value} />
                <Line
                  type="monotone"
                  data={entriesData}
                  dataKey="weight"
                  name="Peso diario"
                  stroke="#72d8ff"
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: '#72d8ff' }}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  data={weeklyAveragesData}
                  dataKey="average_weight"
                  name="Media semanal"
                  stroke="#dfe9ff"
                  strokeWidth={3}
                  dot={{ r: 4, fill: '#dfe9ff' }}
                  activeDot={{ r: 5 }}
                />
                {expectedTrendData.length > 0 ? (
                  <Line
                    type="monotone"
                    data={expectedTrendData}
                    dataKey="expected_weight"
                    name="Referencia esperada"
                    stroke="#5b7fff"
                    strokeWidth={2}
                    strokeDasharray="6 5"
                    dot={false}
                  />
                ) : null}
                {adjustmentEventsData.length > 0 ? (
                  <Scatter
                    data={adjustmentEventsData}
                    dataKey="reference_weight"
                    name="Ajustes caloricos"
                    fill="#ff6b6b"
                    stroke="#ff6b6b"
                  />
                ) : null}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {weightProgress?.expected_trend_label ? (
        <p className="info-note">{weightProgress.expected_trend_label}</p>
      ) : null}

      {latestAnalysis ? (
        <article className="dashboard-signal-card">
          <div className="analysis-header">
            <strong>Lectura semanal mas reciente</strong>
            <span className={`status-badge status-${latestAnalysis.progress_status}`}>
              {latestAnalysis.adjustment_needed ? 'Requiere atencion' : 'Sin ajuste'}
            </span>
          </div>
          <p>{latestAnalysis.adjustment_reason}</p>
          <p>
            Cambio semanal detectado: <strong>{formatSignedWeight(latestAnalysis.weekly_change)}</strong>
          </p>
        </article>
      ) : null}

      {recentEvents.length > 0 ? (
        <div className="dashboard-event-grid">
          {recentEvents.map((event) => (
            <article key={event.id} className="dashboard-event-card">
              <span>{event.week_label}</span>
              <strong>{formatSignedCalories(event.calorie_change)} / {formatCalories(event.new_target_calories)}</strong>
              <p>{event.adjustment_reason}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default WeightProgressChart
