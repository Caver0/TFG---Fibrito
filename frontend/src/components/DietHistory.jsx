import { formatTrainingTimeOfDay } from '../utils/dietDistribution'

function formatDietTimestamp(value) {
  if (!value) {
    return 'Sin fecha'
  }

  return new Date(value).toLocaleString('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatDietKind(diet) {
  if (diet.food_data_source === 'legacy_structural') {
    return 'Estructural antigua'
  }

  return 'Por alimentos'
}

function DietHistory({
  diets,
  error,
  isLoading,
  onSelect,
  selectedDietId,
  viewingDietId,
}) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Historial de dietas</span>
        <h2>Dietas generadas</h2>
        <p>Puedes revisar tus generaciones anteriores y abrir el detalle completo de cualquier dieta guardada.</p>
      </div>

      {isLoading ? <p className="info-note">Cargando historial de dietas...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && diets.length === 0 ? (
        <p className="info-note">Todavia no has generado ninguna dieta diaria.</p>
      ) : null}

      {!isLoading && !error && diets.length > 0 ? (
        <div className="diet-history-list">
          {diets.map((diet) => (
            <article
              key={diet.id}
              className={`diet-history-row ${selectedDietId === diet.id ? 'diet-history-row-active' : ''}`}
            >
              <div>
                <span className="history-label">Creada</span>
                <strong>{formatDietTimestamp(diet.created_at)}</strong>
              </div>
              <div>
                <span className="history-label">Tipo</span>
                <strong>{formatDietKind(diet)}</strong>
              </div>
              <div>
                <span className="history-label">Calorias</span>
                <strong>{diet.actual_calories} / {diet.target_calories} kcal</strong>
              </div>
              <div>
                <span className="history-label">Entreno</span>
                <strong>
                  {diet.training_optimization_applied
                    ? `Optimizada (${formatTrainingTimeOfDay(diet.training_time_of_day)})`
                    : 'Sin optimizacion'}
                </strong>
              </div>
              <button
                type="button"
                className="history-action"
                disabled={viewingDietId === diet.id}
                onClick={() => onSelect(diet.id)}
              >
                {viewingDietId === diet.id ? 'Abriendo...' : 'Ver dieta'}
              </button>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default DietHistory
