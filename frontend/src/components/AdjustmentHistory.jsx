function AdjustmentHistory({ entries, error, isLoading }) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Historial de ajustes</span>
        <h2>Analisis realizados</h2>
        <p>Cada registro explica el cambio semanal detectado y si se ajustaron o no las calorias.</p>
      </div>

      {isLoading ? <p className="info-note">Cargando historial de ajustes...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && entries.length === 0 ? (
        <p className="info-note">Todavia no se ha guardado ningun analisis semanal.</p>
      ) : null}

      {!isLoading && !error && entries.length > 0 ? (
        <div className="adjustment-history-list">
          {entries.map((entry) => (
            <article key={entry.id} className="adjustment-card">
              <div className="adjustment-card-header">
                <strong>{entry.current_week_label}</strong>
                <span>{entry.adjustment_applied ? 'Ajuste aplicado' : 'Sin ajuste'}</span>
              </div>
              <p>
                {entry.previous_week_label}: {entry.previous_week_avg} | {entry.current_week_label}: {entry.current_week_avg}
              </p>
              <p>Cambio semanal: {entry.weekly_change}</p>
              <p>Calorias: {entry.previous_target_calories} {'->'} {entry.new_target_calories}</p>
              <p>{entry.reason}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default AdjustmentHistory
