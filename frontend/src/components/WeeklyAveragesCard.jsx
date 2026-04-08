function WeeklyAveragesCard({ averages, error, isLoading }) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Medias semanales</span>
        <h2>Peso medio por semana</h2>
        <p>Usamos semanas ISO consistentes para agrupar los registros y calcular la media semanal.</p>
      </div>

      {isLoading ? <p className="info-note">Calculando medias semanales...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && averages.length === 0 ? (
        <p className="info-note">Todavia no hay suficientes datos para mostrar medias semanales.</p>
      ) : null}

      {!isLoading && !error && averages.length > 0 ? (
        <div className="weekly-averages-list">
          {averages.map((average) => (
            <article key={average.week_label} className="weekly-average-row">
              <div>
                <span className="history-label">Semana</span>
                <strong>{average.week_label}</strong>
              </div>
              <div>
                <span className="history-label">Media</span>
                <strong>{average.average_weight}</strong>
              </div>
              <div>
                <span className="history-label">Registros</span>
                <strong>{average.entry_count}</strong>
              </div>
              <div>
                <span className="history-label">Estado</span>
                <strong>{average.is_complete ? 'Completa' : 'En curso'}</strong>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default WeeklyAveragesCard
