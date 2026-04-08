function getStatusLabel(status) {
  if (status === 'on_track') {
    return 'En objetivo'
  }
  if (status === 'needs_adjustment') {
    return 'Requiere ajuste'
  }
  if (status === 'insufficient_data') {
    return 'Faltan datos'
  }
  return 'Perfil incompleto'
}

function WeeklyAnalysisCard({
  analysis,
  applyError,
  applyMessage,
  error,
  isApplying,
  isLoading,
  onApply,
}) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Analisis semanal</span>
        <h2>Comparacion entre semanas</h2>
        <p>El sistema compara las dos ultimas semanas completas y decide si las calorias deben ajustarse.</p>
      </div>

      {isLoading ? <p className="info-note">Analizando progreso semanal...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}

      {!isLoading && !error && analysis ? (
        <>
          <div className="analysis-header">
            <span className={`status-badge status-${analysis.progress_status}`}>
              {getStatusLabel(analysis.progress_status)}
            </span>
            <span className="analysis-goal">Objetivo: {analysis.goal ?? 'Sin definir'}</span>
          </div>

          <div className="nutrition-grid">
            <article className="metric-card">
              <span>Semana anterior</span>
              <strong>{analysis.previous_week_label ?? 'Sin datos'}</strong>
            </article>
            <article className="metric-card">
              <span>Semana actual analizada</span>
              <strong>{analysis.current_week_label ?? 'Sin datos'}</strong>
            </article>
            <article className="metric-card">
              <span>Media anterior</span>
              <strong>{analysis.previous_week_avg ?? 'Sin datos'}</strong>
            </article>
            <article className="metric-card">
              <span>Media actual</span>
              <strong>{analysis.current_week_avg ?? 'Sin datos'}</strong>
            </article>
            <article className="metric-card">
              <span>Cambio semanal</span>
              <strong>{analysis.weekly_change ?? 'Sin datos'}</strong>
            </article>
            <article className="metric-card">
              <span>Cambio calorico</span>
              <strong>{analysis.calorie_change}</strong>
            </article>
            <article className="metric-card">
              <span>Calorias anteriores</span>
              <strong>{analysis.previous_target_calories ?? 'Sin datos'}</strong>
            </article>
            <article className="metric-card">
              <span>Calorias nuevas</span>
              <strong>{analysis.new_target_calories ?? 'Sin datos'}</strong>
            </article>
          </div>

          <p className="info-note">{analysis.reason}</p>
        </>
      ) : null}

      {applyError ? <p className="form-error">{applyError}</p> : null}
      {applyMessage ? <p className="form-success">{applyMessage}</p> : null}

      <div className="analysis-actions">
        <button type="button" onClick={onApply} disabled={isApplying}>
          {isApplying ? 'Aplicando ajuste...' : 'Analizar y aplicar ajuste semanal'}
        </button>
      </div>
    </section>
  )
}

export default WeeklyAnalysisCard
