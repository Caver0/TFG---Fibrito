import {
  formatCalories,
  formatGoal,
  formatMacro,
  formatPercentage,
  formatSignedWeight,
  formatWeight,
} from '../utils/dashboardFormat'

function DashboardStats({ summary }) {
  const macros = summary?.current_macros ?? {}
  const confidencePercentage = Number(summary?.confidence_percentage ?? summary?.weekly_adherence_percentage ?? 0)
  const coveragePercentage = Number(summary?.tracking_coverage_percentage ?? 0)

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Vista rapida</span>
        <h2>Resumen actual del atleta</h2>
        <p>Unificamos las metricas mas importantes del momento para leer el estado del proceso de un vistazo.</p>
      </div>

      {!summary ? (
        <p className="info-note">Todavia no hay resumen suficiente para mostrar en el dashboard.</p>
      ) : (
        <div className="dashboard-stats-grid">
          <article className="metric-card dashboard-stat-card">
            <span>Peso actual</span>
            <strong>{formatWeight(summary.current_weight)}</strong>
            <small>
              {summary.current_weight_date
                ? `Ultimo registro disponible: ${summary.current_weight_date}`
                : 'Sin fecha de registro reciente'}
            </small>
          </article>

          <article className="metric-card dashboard-stat-card">
            <span>Cambio semanal</span>
            <strong>{formatSignedWeight(summary.latest_weekly_change)}</strong>
            <small>Lectura basada en las dos ultimas semanas completas.</small>
          </article>

          <article className="metric-card dashboard-stat-card">
            <span>Calorias objetivo actuales</span>
            <strong>{formatCalories(summary.current_target_calories)}</strong>
            <small>{formatGoal(summary.goal)}</small>
          </article>

          <article className="metric-card dashboard-stat-card">
            <span>Macros actuales</span>
            <strong className="dashboard-stat-macros">
              {formatMacro(macros.protein_grams)} P / {formatMacro(macros.carb_grams)} C / {formatMacro(macros.fat_grams)} G
            </strong>
            <small>Referencias vigentes del plan actual.</small>
          </article>

          <article className="metric-card dashboard-stat-card">
            <span>Fiabilidad semanal</span>
            <strong>{formatPercentage(confidencePercentage)}</strong>
            <small>{coveragePercentage > 0 ? `Cobertura ${formatPercentage(coveragePercentage)}` : (summary.adherence_level ? `Nivel ${summary.adherence_level}` : 'Sin nivel calculado')}</small>
          </article>

          <article className="metric-card dashboard-stat-card">
            <span>Adherencia registrada</span>
            <strong>{formatPercentage(Number(summary.weekly_adherence_factor ?? 0) * 100)}</strong>
            <small>{summary.adherence_interpretation || 'Sin mensaje interpretativo disponible.'}</small>
          </article>
        </div>
      )}
    </section>
  )
}

export default DashboardStats
