import { useState } from 'react'

function WeightHistory({ entries, error, isLoading, onDelete, deletingEntryId }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <section className="profile-section">
      <div className="collapsible-section-header">
        <div className="section-heading">
          <span className="eyebrow">Historial</span>
          <h2>Entradas registradas</h2>
          <p>El historial se muestra ordenado por fecha ascendente para seguir el progreso en el tiempo.</p>
        </div>

        {entries.length > 0 ? (
          <button
            type="button"
            className="secondary-button collapsible-toggle"
            onClick={() => setIsExpanded((currentValue) => !currentValue)}
          >
            {isExpanded ? 'Ocultar historial' : `Ver historial (${entries.length})`}
          </button>
        ) : null}
      </div>

      {isLoading ? <p className="info-note">Cargando historial de peso...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}

      {!isLoading && !error && entries.length === 0 ? (
        <p className="info-note">Todavia no hay registros de peso.</p>
      ) : null}

      {!isLoading && !error && entries.length > 0 && isExpanded ? (
        <div className="weight-history-list">
          {entries.map((entry) => (
            <article key={entry.id} className="history-row">
              <div>
                <span className="history-label">Fecha</span>
                <strong>{entry.date}</strong>
              </div>
              <div>
                <span className="history-label">Peso</span>
                <strong>{entry.weight}</strong>
              </div>
              <button
                type="button"
                className="history-action"
                onClick={() => onDelete(entry.id)}
                disabled={deletingEntryId === entry.id}
              >
                {deletingEntryId === entry.id ? 'Eliminando...' : 'Eliminar'}
              </button>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default WeightHistory
