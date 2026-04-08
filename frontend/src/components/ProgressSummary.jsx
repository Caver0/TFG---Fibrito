function ProgressSummary({ error, isLoading, summary }) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Progreso</span>
        <h2>Resumen basico</h2>
        <p>Mostramos una lectura simple de tu evolucion a partir de los pesos guardados.</p>
      </div>

      {isLoading ? <p className="info-note">Calculando resumen de progreso...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}

      {!isLoading && !error && summary ? (
        <div className="nutrition-grid">
          <article className="metric-card">
            <span>Primer peso</span>
            <strong>{summary.first_weight ?? 'Sin datos'}</strong>
          </article>
          <article className="metric-card">
            <span>Ultimo peso</span>
            <strong>{summary.latest_weight ?? 'Sin datos'}</strong>
          </article>
          <article className="metric-card">
            <span>Cambio total</span>
            <strong>{summary.total_change ?? 'Sin datos'}</strong>
          </article>
          <article className="metric-card">
            <span>Numero de registros</span>
            <strong>{summary.number_of_entries}</strong>
          </article>
          <article className="metric-card">
            <span>Fecha del ultimo registro</span>
            <strong>{summary.latest_entry_date ?? 'Sin datos'}</strong>
          </article>
        </div>
      ) : null}
    </section>
  )
}

export default ProgressSummary
