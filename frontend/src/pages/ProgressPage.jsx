import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import * as adherenceApi from '../api/adherenceApi'
import * as dashboardApi from '../api/dashboardApi'
import * as progressApi from '../api/progressApi'
import * as weightApi from '../api/weightApi'
import AdjustmentHistory from '../components/AdjustmentHistory'
import CircularGauge from '../components/CircularGauge'
import SectionPanel from '../components/SectionPanel'
import { useAuth } from '../context/AuthContext'
import {
  formatAdherenceLevel,
  formatCalories,
  formatCompactNumber,
  formatDateLabel,
  formatDayLabel,
  formatMass,
  formatPercent,
  formatSignedCalories,
  formatSignedMass,
  toConfidenceScore,
} from '../utils/stitch'

function getTodayDateInputValue() {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function buildTrendSeries(entries, expectedTrend, weeklyAverages) {
  const actualEntries = Array.isArray(entries) && entries.length > 0
    ? entries.map((entry) => ({
        chartDate: entry.date,
        axisLabel: formatDateLabel(entry.date),
        actualWeight: Number(entry.weight),
      }))
    : (weeklyAverages ?? []).map((entry) => ({
        chartDate: entry.end_date,
        axisLabel: entry.week_label,
        actualWeight: Number(entry.average_weight),
      }))

  const byDate = Object.fromEntries(actualEntries.map((entry) => [entry.chartDate, entry]))

  for (const point of expectedTrend ?? []) {
    const chartDate = point.date
    if (!byDate[chartDate]) {
      byDate[chartDate] = {
        chartDate,
        axisLabel: formatDateLabel(chartDate),
      }
      actualEntries.push(byDate[chartDate])
    }
    byDate[chartDate].expectedWeight = Number(point.expected_weight)
  }

  return actualEntries.sort((left, right) => new Date(left.chartDate) - new Date(right.chartDate))
}

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  const actual = payload.find((item) => item.dataKey === 'actualWeight')
  const expected = payload.find((item) => item.dataKey === 'expectedWeight')

  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {actual ? <p>Actual: {formatMass(actual.value)}</p> : null}
      {expected ? <p>Esperado: {formatMass(expected.value)}</p> : null}
    </div>
  )
}

function ProgressPage() {
  const { refreshUser, token } = useAuth()
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [weeklyAverages, setWeeklyAverages] = useState([])
  const [weeklyAnalysis, setWeeklyAnalysis] = useState(null)
  const [weeklyAdherenceSummary, setWeeklyAdherenceSummary] = useState(null)
  const [adjustmentHistory, setAdjustmentHistory] = useState([])
  const [dashboardSnapshot, setDashboardSnapshot] = useState(null)
  const [weightForm, setWeightForm] = useState({
    weight: '',
    date: getTodayDateInputValue(),
  })
  const [historyError, setHistoryError] = useState('')
  const [summaryError, setSummaryError] = useState('')
  const [weeklyAveragesError, setWeeklyAveragesError] = useState('')
  const [weeklyAnalysisError, setWeeklyAnalysisError] = useState('')
  const [weeklyAdherenceError, setWeeklyAdherenceError] = useState('')
  const [dashboardError, setDashboardError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [applyError, setApplyError] = useState('')
  const [applyMessage, setApplyMessage] = useState('')
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [isSummaryLoading, setIsSummaryLoading] = useState(false)
  const [isWeeklyAveragesLoading, setIsWeeklyAveragesLoading] = useState(false)
  const [isWeeklyAnalysisLoading, setIsWeeklyAnalysisLoading] = useState(false)
  const [isWeeklyAdherenceLoading, setIsWeeklyAdherenceLoading] = useState(false)
  const [isDashboardLoading, setIsDashboardLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isApplyingAdjustment, setIsApplyingAdjustment] = useState(false)
  const [deletingEntryId, setDeletingEntryId] = useState('')

  async function loadWeightHistory(activeToken = token) {
    if (!activeToken) return []
    setIsHistoryLoading(true)
    setHistoryError('')
    try {
      const response = await weightApi.getWeightHistory(activeToken)
      setEntries(response.entries)
      return response.entries
    } catch (error) {
      setEntries([])
      setHistoryError(error.message)
      return []
    } finally {
      setIsHistoryLoading(false)
    }
  }

  async function loadProgressSummary(activeToken = token) {
    if (!activeToken) return null
    setIsSummaryLoading(true)
    setSummaryError('')
    try {
      const response = await weightApi.getProgressSummary(activeToken)
      setSummary(response)
      return response
    } catch (error) {
      setSummary(null)
      setSummaryError(error.message)
      return null
    } finally {
      setIsSummaryLoading(false)
    }
  }

  async function loadWeeklyAverages(activeToken = token) {
    if (!activeToken) return []
    setIsWeeklyAveragesLoading(true)
    setWeeklyAveragesError('')
    try {
      const response = await progressApi.getWeeklyAverages(activeToken)
      setWeeklyAverages(response.averages)
      return response.averages
    } catch (error) {
      setWeeklyAverages([])
      setWeeklyAveragesError(error.message)
      return []
    } finally {
      setIsWeeklyAveragesLoading(false)
    }
  }

  async function loadWeeklyAnalysis(activeToken = token) {
    if (!activeToken) return null
    setIsWeeklyAnalysisLoading(true)
    setWeeklyAnalysisError('')
    try {
      const response = await progressApi.getWeeklyAnalysis(activeToken)
      setWeeklyAnalysis(response)
      return response
    } catch (error) {
      setWeeklyAnalysis(null)
      setWeeklyAnalysisError(error.message)
      return null
    } finally {
      setIsWeeklyAnalysisLoading(false)
    }
  }

  async function loadWeeklyAdherenceSummary(activeToken = token, targetWeekLabel = weeklyAnalysis?.current_week_label ?? null) {
    if (!activeToken) return null
    setIsWeeklyAdherenceLoading(true)
    setWeeklyAdherenceError('')
    try {
      const response = await adherenceApi.getWeeklyAdherenceSummary(activeToken, targetWeekLabel ? { week_label: targetWeekLabel } : {})
      setWeeklyAdherenceSummary(response)
      return response
    } catch (error) {
      setWeeklyAdherenceSummary(null)
      setWeeklyAdherenceError(error.message)
      return null
    } finally {
      setIsWeeklyAdherenceLoading(false)
    }
  }

  async function loadAdjustmentHistory(activeToken = token) {
    if (!activeToken) return []
    try {
      const response = await progressApi.getAdjustmentHistory(activeToken)
      setAdjustmentHistory(response.entries)
      return response.entries
    } catch {
      setAdjustmentHistory([])
      return []
    }
  }

  async function loadDashboardSnapshot(activeToken = token) {
    if (!activeToken) return null
    setIsDashboardLoading(true)
    setDashboardError('')
    try {
      const response = await dashboardApi.getDashboardOverview(activeToken)
      setDashboardSnapshot(response)
      return response
    } catch (error) {
      setDashboardSnapshot(null)
      setDashboardError(error.message)
      return null
    } finally {
      setIsDashboardLoading(false)
    }
  }

  async function reloadAll(activeToken = token) {
    const [, , analysis] = await Promise.all([
      loadWeightHistory(activeToken),
      loadProgressSummary(activeToken),
      loadWeeklyAnalysis(activeToken),
      loadWeeklyAverages(activeToken),
      loadAdjustmentHistory(activeToken),
      loadDashboardSnapshot(activeToken),
    ])
    await loadWeeklyAdherenceSummary(activeToken, analysis?.current_week_label ?? null)
  }

  useEffect(() => {
    if (!token) return
    reloadAll(token)
  }, [token])

  useEffect(() => {
    if (!token) return undefined
    async function handleAdherenceUpdated() {
      await loadWeeklyAdherenceSummary(token, weeklyAnalysis?.current_week_label ?? null)
      await loadDashboardSnapshot(token)
    }
    window.addEventListener('adherence:updated', handleAdherenceUpdated)
    return () => window.removeEventListener('adherence:updated', handleAdherenceUpdated)
  }, [token, weeklyAnalysis?.current_week_label])

  async function handleSave(event) {
    event.preventDefault()
    if (!token) return
    setIsSaving(true)
    setSaveError('')
    setSaveMessage('')
    try {
      await weightApi.createWeightEntry(token, {
        weight: Number(weightForm.weight),
        date: weightForm.date,
      })
      await reloadAll(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      setSaveMessage('Registro de peso guardado correctamente.')
      setWeightForm((current) => ({ ...current, weight: '' }))
    } catch (error) {
      setSaveError(error.message)
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDelete(entryId) {
    if (!token) return
    setDeletingEntryId(entryId)
    try {
      await weightApi.deleteWeightEntry(token, entryId)
      await reloadAll(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
    } catch (error) {
      setHistoryError(error.message)
    } finally {
      setDeletingEntryId('')
    }
  }

  async function handleApplyAdjustment() {
    if (!token) return
    setIsApplyingAdjustment(true)
    setApplyError('')
    setApplyMessage('')
    try {
      const response = await progressApi.applyWeeklyAdjustment(token)
      setWeeklyAnalysis(response.analysis)
      await refreshUser(token)
      await reloadAll(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      setApplyMessage(response.adjustment?.adjustment_applied ? 'Ajuste semanal aplicado y guardado.' : response.analysis.adjustment_reason)
    } catch (error) {
      setApplyError(error.message)
    } finally {
      setIsApplyingAdjustment(false)
    }
  }

  const chartSeries = buildTrendSeries(
    dashboardSnapshot?.weight_progress?.entries,
    dashboardSnapshot?.weight_progress?.expected_trend,
    weeklyAverages,
  )
  const confidenceScore = toConfidenceScore(weeklyAdherenceSummary?.weekly_adherence_factor ?? 0)
  const dailyBreakdown = dashboardSnapshot?.adherence?.daily_breakdown ?? []
  const recentEntries = [...entries].slice(-3).reverse()

  return (
    <div className="progress-page">
      {(isHistoryLoading || isSummaryLoading || isWeeklyAveragesLoading || isWeeklyAnalysisLoading || isWeeklyAdherenceLoading || isDashboardLoading)
        ? <p className="page-status">Cargando análisis de adherencia...</p>
        : null}
      {(historyError || summaryError || weeklyAveragesError || weeklyAnalysisError || weeklyAdherenceError || dashboardError || saveError || applyError)
        ? <p className="page-status page-status-error">{historyError || summaryError || weeklyAveragesError || weeklyAnalysisError || weeklyAdherenceError || dashboardError || saveError || applyError}</p>
        : null}

      <div className="progress-hero-grid">
        <SectionPanel eyebrow="Estado del Sistema" className="progress-hero-card progress-hero-copy">
          <h3>Fiabilidad de Datos: <span>{formatAdherenceLevel(weeklyAdherenceSummary?.adherence_level)}</span></h3>
          <p>{weeklyAdherenceSummary?.interpretation_message || dashboardSnapshot?.summary?.adherence_interpretation || 'El seguimiento de adherencia desbloqueará la interpretación de fiabilidad tras registrar comidas.'}</p>
          <button type="button" className="panel-cta-button" onClick={() => window.location.hash = '#diets'}>Revisar Registros de Dieta</button>
        </SectionPanel>

        <SectionPanel className="progress-hero-card progress-gauge-card">
          <CircularGauge value={confidenceScore} label="Confianza" />
          <div className="progress-gauge-meta">
            <div><small>Seguimiento</small><strong>{formatPercent(weeklyAdherenceSummary?.tracking_coverage_percentage ?? 0, 0)}</strong></div>
            <div><small>Precisión</small><strong>{weeklyAnalysis?.can_analyze ? 'Ultra' : 'Pendiente'}</strong></div>
          </div>
        </SectionPanel>

        <div className="progress-quick-stats">
          <SectionPanel className="progress-quick-card"><small>Delta Semanal</small><strong>{formatSignedMass(weeklyAnalysis?.weekly_change, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}</strong></SectionPanel>
          <SectionPanel className="progress-quick-card progress-quick-card-danger"><small>Flujo Calórico</small><strong>{formatSignedCalories(weeklyAnalysis?.calorie_change)}</strong></SectionPanel>
        </div>
      </div>

      <SectionPanel
        title="Tendencia de Análisis de Peso"
        description="Actual (neón) vs. proyección esperada del modelo actual del backend."
        actions={<div className="legend-group"><span><i className="legend-dot legend-dot-primary" />Actual</span><span><i className="legend-dot legend-dot-muted" />Objetivo</span></div>}
      >
        <div className="dashboard-chart-wrap">
          {chartSeries.length > 0 ? (
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={chartSeries}>
                <CartesianGrid stroke="rgba(118, 117, 118, 0.18)" strokeDasharray="4 6" vertical={false} />
                <XAxis dataKey="axisLabel" axisLine={false} tickLine={false} tick={{ fill: '#adacab', fontSize: 10, fontWeight: 700 }} />
                <YAxis hide domain={['auto', 'auto']} />
                <Tooltip content={<TrendTooltip />} />
                <Line type="monotone" dataKey="expectedWeight" stroke="#484849" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="actualWeight" stroke="#daf900" strokeWidth={4} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : <p className="panel-placeholder">Los datos de tendencia de peso aparecerán tras los primeros registros.</p>}
        </div>
      </SectionPanel>

      <div className="progress-bottom-layout">
        <SectionPanel title="Mapa de Calor de Adherencia">
          <div className="adherence-heatmap-grid">
            {(dailyBreakdown.length > 0 ? dailyBreakdown : new Array(7).fill(null)).map((day, index) => (
              <div key={`heat-${index}`} className="adherence-heatmap-cell-wrap">
                <span>{day ? day.day_label : ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'][index]}</span>
                <div className={`adherence-heatmap-cell adherence-heatmap-level-${day ? Math.max(0, Math.min(4, Math.round((day.adherence_percentage || 0) / 25))) : 0}`} />
              </div>
            ))}
          </div>
        </SectionPanel>

        <SectionPanel title="Registros Recientes">
          {recentEntries.length > 0 ? (
            <div className="recent-log-list">
              {recentEntries.map((entry) => (
                <article key={entry.id} className="recent-log-item">
                  <div>
                    <strong>{formatMass(entry.weight)}</strong>
                    <small>{formatDayLabel(entry.date)} // {formatDateLabel(entry.date, { month: 'short', day: '2-digit', year: 'numeric' })}</small>
                  </div>
                  <button type="button" className="protocol-chip-button" disabled={deletingEntryId === entry.id} onClick={() => handleDelete(entry.id)}>
                    {deletingEntryId === entry.id ? 'Borrando...' : 'Borrar'}
                  </button>
                </article>
              ))}
            </div>
          ) : <p className="panel-placeholder">Los registros de peso recientes aparecerán aquí.</p>}
        </SectionPanel>
      </div>

      <SectionPanel className="progress-footer-bar">
        <form className="progress-log-form" onSubmit={handleSave}>
          <label><span>Peso (kg)</span><input type="number" step="0.1" min="0" value={weightForm.weight} onChange={(event) => setWeightForm((current) => ({ ...current, weight: event.target.value }))} required /></label>
          <label><span>Fecha</span><input type="date" value={weightForm.date} onChange={(event) => setWeightForm((current) => ({ ...current, date: event.target.value }))} required /></label>
          <button type="submit" className="protocol-secondary-button" disabled={isSaving}>{isSaving ? 'Guardando...' : 'Registrar Peso'}</button>
        </form>

        <div className="progress-footer-copy">
          <strong>{summary?.latest_weight ? `Último peso ${formatMass(summary.latest_weight)}` : 'Aún no hay último peso'}</strong>
          <span>{summary?.number_of_entries ? `${summary.number_of_entries} registros observados` : 'Comienza a registrar tu peso para activar el análisis.'}</span>
        </div>

        <button type="button" className="panel-cta-button" disabled={isApplyingAdjustment} onClick={handleApplyAdjustment}>
          {isApplyingAdjustment ? 'Aplicando...' : 'Aplicar Ajuste Semanal'}
        </button>
      </SectionPanel>

      <AdjustmentHistory entries={adjustmentHistory} isLoading={false} error="" />

      {saveMessage ? <p className="page-status page-status-success">{saveMessage}</p> : null}
      {applyMessage ? <p className="page-status page-status-success">{applyMessage}</p> : null}
    </div>
  )
}

export default ProgressPage
