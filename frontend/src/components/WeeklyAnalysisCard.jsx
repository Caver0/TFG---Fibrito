import {
  formatDirectionStatus,
  formatProgressMetric,
  formatRateStatus,
} from '../utils/progressFormat'
import { resolveConfidencePercentage } from '../utils/stitch'

function getStatusLabel(status) {
  if (status === 'on_track') {
    return 'En objetivo'
  }
  if (status === 'needs_adjustment') {
    return 'Requiere ajuste'
  }
  // Añadimos el nuevo label para el estado de atención por adherencia
  if (status === 'needs_attention') {
    return 'Revisión por adherencia'
  }
  if (status === 'insufficient_data') {
    return 'Faltan datos'
  }
  return 'Perfil incompleto'
}

function formatAdherenceLevel(level) {
  if (level === 'alta') {
    return 'Alta adherencia'
  }
  if (level === 'media') {
    return 'Adherencia media'
  }
  return 'Baja adherencia'
}

function WeeklyAnalysisCard({
  analysis,
  adherenceSummary,
  applyError,
  applyMessage,
  error,
  isApplying,
  isLoading,
  onApply,
}) {
  // Identificamos si es un caso de baja adherencia para cambiar el comportamiento del botón
  const isOptionalAdjustment = analysis?.progress_status === 'needs_attention'
  const confidenceScore = resolveConfidencePercentage(adherenceSummary)

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
              <strong>{formatProgressMetric(analysis.previous_week_avg)}</strong>
            </article>
            <article className="metric-card">
              <span>Media actual</span>
              <strong>{formatProgressMetric(analysis.current_week_avg)}</strong>
            </article>
            <article className="metric-card">
              <span>Cambio semanal</span>
              <strong>{formatProgressMetric(analysis.weekly_change)}</strong>
            </article>
            <article className="metric-card">
              <span>Direccion del progreso</span>
              <strong>{formatDirectionStatus(analysis.progress_direction_ok)}</strong>
            </article>
            <article className="metric-card">
              <span>Velocidad del progreso</span>
              <strong>{formatRateStatus(analysis.progress_rate_ok)}</strong>
            </article>
            {analysis.max_weekly_loss !== null && analysis.max_weekly_loss !== undefined ? (
              <article className="metric-card">
                <span>Limite maximo de bajada</span>
                <strong>{formatProgressMetric(analysis.max_weekly_loss)}</strong>
              </article>
            ) : null}
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

          <p className="info-note">{analysis.adjustment_reason}</p>

          {adherenceSummary ? (
            <article className="analysis-adherence-note">
              <div className="analysis-adherence-header">
                <strong>Fiabilidad interpretativa</strong>
                <span className={`weekly-adherence-badge weekly-adherence-badge-${adherenceSummary.adherence_level}`}>
                  {formatAdherenceLevel(adherenceSummary.adherence_level)}
                </span>
              </div>
              <p>
                Fiabilidad semanal {Number(confidenceScore).toFixed(0)}%. Cobertura {Number(adherenceSummary.tracking_coverage_percentage ?? 0).toFixed(0)}%. {adherenceSummary.interpretation_message}
              </p>
            </article>
          ) : null}
        </>
      ) : null}

      {applyError ? <p className="form-error">{applyError}</p> : null}
      {applyMessage ? <p className="form-success">{applyMessage}</p> : null}

      <div className="analysis-actions">
        <button type="button" onClick={onApply} disabled={isApplying}>
          {isApplying 
            ? 'Aplicando ajuste...' 
            : isOptionalAdjustment 
              ? 'Aplicar ajuste correctivo opcional' 
              : 'Analizar y aplicar ajuste semanal'}
        </button>
      </div>
    </section>
  )
}

export default WeeklyAnalysisCard
