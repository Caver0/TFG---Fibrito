import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatFactor, formatPercentage } from '../utils/dashboardFormat'

function buildTooltipContent({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null
  }

  const point = payload[0]?.payload
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <p>Completadas: {point.completed_meals}</p>
      <p>Modificadas: {point.modified_meals}</p>
      <p>Omitidas: {point.omitted_meals}</p>
      <p>Pendientes: {point.pending_meals}</p>
      <p>Adherencia del dia: {formatPercentage(point.adherence_percentage)}</p>
    </div>
  )
}

function AdherenceSummaryChart({ adherence }) {
  const dailyBreakdown = adherence?.daily_breakdown ?? []

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Adherencia</span>
        <h2>Cumplimiento de la semana analizada</h2>
        <p>Mostramos el grado de seguimiento real del plan y cuanta confianza aporta al interpretar la evolucion del peso.</p>
      </div>

      {!adherence ? (
        <p className="info-note">Todavia no hay datos de adherencia agregados para este dashboard.</p>
      ) : (
        <>
          <div className="dashboard-adherence-summary">
            <article className="dashboard-adherence-hero">
              <strong>{formatPercentage(adherence.adherence_percentage)}</strong>
              <span>Adherencia semanal</span>
              <p>{adherence.interpretation_message}</p>
            </article>

            <div className="dashboard-adherence-metrics">
              <article className="metric-card">
                <span>Factor interpretativo</span>
                <strong>{formatFactor(adherence.weekly_adherence_factor)}</strong>
              </article>
              <article className="metric-card">
                <span>Cobertura</span>
                <strong>{formatPercentage(adherence.tracking_coverage_percentage)}</strong>
              </article>
              <article className="metric-card">
                <span>Registradas</span>
                <strong>{adherence.total_meals_registered} / {adherence.total_planned_meals}</strong>
              </article>
            </div>
          </div>

          {dailyBreakdown.length > 0 ? (
            <div className="dashboard-chart-shell dashboard-chart-shell-compact">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={dailyBreakdown} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid stroke="rgba(152, 176, 214, 0.16)" strokeDasharray="4 4" />
                  <XAxis dataKey="day_label" tick={{ fill: '#8fa0bd', fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fill: '#8fa0bd', fontSize: 12 }} />
                  <Tooltip content={buildTooltipContent} />
                  <Bar dataKey="completed_meals" stackId="adherence" fill="#72d8ff" name="Completadas" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="modified_meals" stackId="adherence" fill="#5b7fff" name="Modificadas" />
                  <Bar dataKey="omitted_meals" stackId="adherence" fill="#ff6b6b" name="Omitidas" />
                  <Bar dataKey="pending_meals" stackId="adherence" fill="#32445f" name="Pendientes" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}

          <p className="info-note">
            Semana analizada: {adherence.start_date} a {adherence.end_date}. Completadas: {adherence.completed_meals}. Modificadas: {adherence.modified_meals}. Omitidas: {adherence.omitted_meals}.
          </p>
        </>
      )}
    </section>
  )
}

export default AdherenceSummaryChart
