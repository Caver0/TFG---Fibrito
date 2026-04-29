import { useState } from 'react'
import { formatProgressMetric } from '../utils/progressFormat'
import { formatMacro, formatSignedCalories } from '../utils/stitch'

function resolveDecision(entry) {
  if (entry.adjustment_applied) {
    return {
      label: 'Ajuste aplicado',
      note: 'Se actualizo el objetivo semanal.',
    }
  }

  if (entry.calorie_change === 0) {
    return {
      label: 'Sin ajuste',
      note: 'La tendencia se mantuvo estable.',
    }
  }

  return {
    label: 'No aplicado',
    note: 'La recomendacion quedo bloqueada por fiabilidad o cobertura.',
  }
}

function renderMacroSummary(macros) {
  if (!macros) return 'Macros N/A'
  return `P ${formatMacro(macros.protein_grams)} / C ${formatMacro(macros.carb_grams)} / G ${formatMacro(macros.fat_grams)}`
}

function renderAppliedSummary(entry) {
  if (entry.adjustment_applied) {
    return formatSignedCalories(entry.calorie_change)
  }

  if (entry.calorie_change === 0) {
    return 'Sin cambios'
  }

  return 'No aplicado'
}

function AdjustmentHistory({ entries, error, isLoading }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <section className="profile-section">
      <div className="collapsible-section-header">
        <div className="section-heading">
          <span className="eyebrow">Historial de ajustes</span>
          <h2>Analisis semanales</h2>
          <p>Cada fila resume la semana analizada, el peso inicial y final, la decision tomada y el ajuste aplicado.</p>
        </div>

        {entries.length > 0 ? (
          <button
            type="button"
            className="secondary-button collapsible-toggle"
            onClick={() => setIsExpanded((value) => !value)}
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
        <div className="adjustment-history-table-wrap">
          <table className="adjustment-history-table">
            <thead>
              <tr>
                <th>Semana</th>
                <th>Peso inicial / final</th>
                <th>Cambio semanal</th>
                <th>Decision</th>
                <th>Ajuste aplicado</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const weeklyChange = entry.weekly_change ?? null
                const changeClass =
                  weeklyChange === null
                    ? 'adj-change-neutral'
                    : weeklyChange > 0
                      ? 'adj-change-positive'
                      : weeklyChange < 0
                        ? 'adj-change-negative'
                        : 'adj-change-neutral'
                const sign = weeklyChange > 0 ? '+' : ''
                const decision = resolveDecision(entry)

                return (
                  <tr key={entry.id}>
                    <td className="adj-week-cell">
                      <strong>{entry.current_week_label}</strong>
                      <small>{entry.previous_week_label}</small>
                    </td>
                    <td className="adj-weight-cell">
                      <strong>{formatProgressMetric(entry.previous_week_avg)}</strong>
                      <span className="adj-arrow">{'->'}</span>
                      <strong>{formatProgressMetric(entry.current_week_avg)}</strong>
                    </td>
                    <td className={`adj-change-cell ${changeClass}`}>
                      {weeklyChange !== null ? `${sign}${formatProgressMetric(weeklyChange)}` : '-'}
                    </td>
                    <td className="adj-decision-cell">
                      <strong>{decision.label}</strong>
                      <small>{decision.note}</small>
                    </td>
                    <td className="adj-outcome-cell">
                      <strong>{renderAppliedSummary(entry)}</strong>
                      <small>{renderMacroSummary(entry.new_target_macros)}</small>
                    </td>
                    <td className="adj-reason-cell">{entry.adjustment_reason}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}

export default AdjustmentHistory
