function formatPercentage(value) {
  return `${Number(value ?? 0).toFixed(1)}%`
}

function formatFactor(value) {
  return Number(value ?? 0).toFixed(2)
}

function formatAdherenceLevel(level) {
  if (level === 'alta') {
    return 'Adherencia semanal alta'
  }
  if (level === 'media') {
    return 'Adherencia semanal media'
  }
  return 'Adherencia semanal baja'
}

function WeeklyAdherenceSummary({
  description = 'Resumen simple del cumplimiento real del plan durante la semana seleccionada.',
  error,
  isLoading,
  summary,
  title = 'Adherencia semanal',
}) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Seguimiento real</span>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>

      {isLoading ? <p className="info-note">Calculando adherencia semanal...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && !summary ? (
        <p className="info-note">Todavia no hay datos de adherencia semanal para mostrar.</p>
      ) : null}

      {!isLoading && !error && summary ? (
        <>
          <article className="weekly-adherence-hero">
            <div className="weekly-adherence-hero-header">
              <span className={`weekly-adherence-badge weekly-adherence-badge-${summary.adherence_level}`}>
                {formatAdherenceLevel(summary.adherence_level)}
              </span>
              <span className="weekly-adherence-week">{summary.week_label}</span>
            </div>

            <div className="weekly-adherence-hero-copy">
              <strong>Factor interpretable: {formatFactor(summary.weekly_adherence_factor)}</strong>
              <p>{summary.interpretation_message}</p>
            </div>
          </article>

          <div className="weekly-adherence-grid">
            <article className="metric-card">
              <span>Adherencia agregada</span>
              <strong>{formatPercentage(summary.adherence_percentage)}</strong>
            </article>
            <article className="metric-card">
              <span>Cobertura de registro</span>
              <strong>{formatPercentage(summary.tracking_coverage_percentage)}</strong>
            </article>
            <article className="metric-card">
              <span>Comidas registradas</span>
              <strong>{summary.total_meals_registered} / {summary.total_planned_meals}</strong>
            </article>
            <article className="metric-card">
              <span>Completadas</span>
              <strong>{summary.completed_meals}</strong>
            </article>
            <article className="metric-card">
              <span>Modificadas</span>
              <strong>{summary.modified_meals}</strong>
            </article>
            <article className="metric-card">
              <span>Omitidas</span>
              <strong>{summary.omitted_meals}</strong>
            </article>
          </div>

          <p className="info-note">
            Dias con registros: {summary.days_with_records}. Pendientes acumuladas: {summary.pending_meals}. Semana analizada: {summary.start_date} a {summary.end_date}.
          </p>
        </>
      ) : null}
    </section>
  )
}

export default WeeklyAdherenceSummary
