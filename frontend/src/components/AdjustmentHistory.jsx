import { useState } from 'react'
import {
  formatDirectionStatus,
  formatProgressMetric,
  formatRateStatus,
} from '../utils/progressFormat'

function AdjustmentHistory({ entries, error, isLoading }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <section className="profile-section">
      <div className="collapsible-section-header">
        <div className="section-heading">
          <span className="eyebrow">Historial de ajustes</span>
          <h2>Analisis realizados</h2>
          <p>Cada registro explica el cambio semanal detectado y si se ajustaron o no las calorias.</p>
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

      {isLoading ? <p className="info-note">Cargando historial de ajustes...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && entries.length === 0 ? (
        <p className="info-note">Todavia no se ha guardado ningun analisis semanal.</p>
      ) : null}

      {!isLoading && !error && entries.length > 0 && isExpanded ? (
        <div className="adjustment-history-list">
          {entries.map((entry) => (
            <article key={entry.id} className="adjustment-card">
              <div className="adjustment-card-header">
                <strong>{entry.current_week_label}</strong>
                <span>{entry.adjustment_applied ? 'Ajuste aplicado' : 'Sin ajuste'}</span>
              </div>
              <p>
                {entry.previous_week_label}: {formatProgressMetric(entry.previous_week_avg)} | {entry.current_week_label}:{' '}
                {formatProgressMetric(entry.current_week_avg)}
              </p>
              <p>Cambio semanal: {formatProgressMetric(entry.weekly_change)}</p>
              <p>Direccion del progreso: {formatDirectionStatus(entry.progress_direction_ok)}</p>
              <p>Velocidad del progreso: {formatRateStatus(entry.progress_rate_ok)}</p>
              {entry.max_weekly_loss !== null && entry.max_weekly_loss !== undefined ? (
                <p>Limite maximo de bajada: {formatProgressMetric(entry.max_weekly_loss)}</p>
              ) : null}
              <p>Calorias: {entry.previous_target_calories} {'->'} {entry.new_target_calories}</p>
              <p>{entry.adjustment_reason}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default AdjustmentHistory
