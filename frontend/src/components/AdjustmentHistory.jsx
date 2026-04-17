import { useState } from 'react'
import {
  formatDirectionStatus,
  formatProgressMetric,
  formatRateStatus,
} from '../utils/progressFormat'
import { formatCalories, formatMacro } from '../utils/stitch'

function CalorieChangeCell({ previous, next, change }) {
  const className =
    change > 0 ? 'adj-change-positive' : change < 0 ? 'adj-change-negative' : 'adj-change-neutral'
  const sign = change > 0 ? '+' : ''

  return (
    <td className="adj-cal-cell">
      <span style={{ color: 'var(--lab-muted)', fontSize: '0.82em' }}>
        {formatCalories(previous)}
      </span>
      <span className="adj-arrow">→</span>
      <strong>{formatCalories(next)}</strong>
      {change !== 0 ? (
        <span className={className} style={{ marginLeft: 8, fontSize: '0.82em' }}>
          ({sign}{formatCalories(change)})
        </span>
      ) : null}
    </td>
  )
}

function MacroDeltaCell({ previousMacros, newMacros }) {
  if (!previousMacros || !newMacros) return <td>—</td>

  const rows = [
    { label: 'P', prev: previousMacros.protein_grams, next: newMacros.protein_grams },
    { label: 'H', prev: previousMacros.carb_grams,    next: newMacros.carb_grams },
    { label: 'G', prev: previousMacros.fat_grams,     next: newMacros.fat_grams },
  ]

  return (
    <td style={{ whiteSpace: 'nowrap' }}>
      {rows.map(({ label, prev, next }) => {
        const delta = Math.round((next - prev) * 10) / 10
        const sign  = delta > 0 ? '+' : ''
        const color = delta > 0 ? 'var(--lab-lime-soft)' : delta < 0 ? 'var(--lab-red)' : 'var(--lab-muted)'
        return (
          <div key={label} style={{ display: 'flex', gap: 6, fontSize: '0.82em', lineHeight: 1.6 }}>
            <span style={{ color: 'var(--lab-muted)', minWidth: 14 }}>{label}</span>
            <span>{formatMacro(prev)}</span>
            <span className="adj-arrow">→</span>
            <span>{formatMacro(next)}</span>
            {delta !== 0 ? (
              <span style={{ color }}>{sign}{delta}g</span>
            ) : null}
          </div>
        )
      })}
    </td>
  )
}

function AdjustmentHistory({ entries, error, isLoading }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <section className="profile-section">
      <div className="collapsible-section-header">
        <div className="section-heading">
          <span className="eyebrow">Historial de ajustes</span>
          <h2>Analisis realizados</h2>
          <p>Cada fila muestra el cambio semanal detectado, la decision tomada y el ajuste aplicado.</p>
        </div>

        {entries.length > 0 ? (
          <button
            type="button"
            className="secondary-button collapsible-toggle"
            onClick={() => setIsExpanded((v) => !v)}
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
                <th>Semana analizada</th>
                <th>Sem. anterior</th>
                <th>Cambio semanal</th>
                <th>Direccion</th>
                <th>Velocidad</th>
                <th>Calorias</th>
                <th>Macros (P / H / G)</th>
                <th>Razon</th>
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

                return (
                  <tr key={entry.id}>
                    <td className="adj-week-cell">{entry.current_week_label}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div>{entry.previous_week_label}</div>
                      <div style={{ color: 'var(--lab-muted)', fontSize: '0.82em' }}>
                        {formatProgressMetric(entry.previous_week_avg)}
                        <span className="adj-arrow">→</span>
                        {formatProgressMetric(entry.current_week_avg)}
                      </div>
                    </td>
                    <td className={`adj-change-cell ${changeClass}`}>
                      {weeklyChange !== null ? `${sign}${formatProgressMetric(weeklyChange)}` : '—'}
                    </td>
                    <td>{formatDirectionStatus(entry.progress_direction_ok)}</td>
                    <td>{formatRateStatus(entry.progress_rate_ok)}</td>
                    <CalorieChangeCell
                      previous={entry.previous_target_calories}
                      next={entry.new_target_calories}
                      change={entry.calorie_change ?? 0}
                    />
                    <MacroDeltaCell
                      previousMacros={entry.previous_target_macros}
                      newMacros={entry.new_target_macros}
                    />
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
