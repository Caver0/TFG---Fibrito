function formatPercentage(value) {
  return `${Number(value ?? 0).toFixed(1)}%`
}

function AdherencePanel({
  error,
  isLoading,
  message,
  onDateChange,
  selectedDate,
  summary,
}) {
  return (
    <section className="profile-section">
      <div className="adherence-panel-header">
        <div className="section-heading">
          <span className="eyebrow">Adherencia diaria</span>
          <h2>Cumplimiento del plan por comida</h2>
          <p>Marca lo que has hecho realmente para distinguir si el resultado del peso viene del plan o de desviaciones en la ejecucion.</p>
        </div>

        <label className="adherence-date-field">
          <span>Fecha a registrar</span>
          <input type="date" value={selectedDate} onChange={(event) => onDateChange(event.target.value)} />
        </label>
      </div>

      {isLoading ? <p className="info-note">Cargando adherencia del dia...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && message ? <p className="form-success">{message}</p> : null}
      {!isLoading && !error && !summary ? (
        <p className="info-note">Selecciona una dieta para empezar a registrar adherencia.</p>
      ) : null}

      {!isLoading && !error && summary ? (
        <>
          <div className="adherence-summary-grid">
            <article className="metric-card">
              <span>Cumplimiento del dia</span>
              <strong>{formatPercentage(summary.adherence_percentage)}</strong>
            </article>
            <article className="metric-card">
              <span>Comidas registradas</span>
              <strong>{summary.registered_meals} / {summary.total_meals}</strong>
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
            <article className="metric-card">
              <span>Pendientes</span>
              <strong>{summary.pending_meals}</strong>
            </article>
          </div>

          <p className="info-note">
            Regla actual: completada = 1.0, modificada = 0.5, omitida = 0.0 y pendiente cuenta como no registrada dentro del resumen diario.
          </p>
        </>
      ) : null}
    </section>
  )
}

export default AdherencePanel
