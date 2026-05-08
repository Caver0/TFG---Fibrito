import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
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
  formatCalories,
  formatCompactNumber,
  formatDateLabel,
  formatDayLabel,
  formatMass,
  formatPercent,
  resolveConfidencePercentage,
  resolveRegisteredAdherencePercentage,
  formatSignedCalories,
  formatSignedMass,
} from '../utils/stitch'

const WEEKDAY_LABELS = ['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB', 'DOM']

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

function buildWeeklyRegisteredMealsSeries(dailyBreakdown) {
  const source = Array.isArray(dailyBreakdown) && dailyBreakdown.length > 0
    ? dailyBreakdown
    : WEEKDAY_LABELS.map((dayLabel) => ({ day_label: dayLabel }))

  return source.map((day, index) => {
    const completedMeals = Number(day?.completed_meals ?? 0)
    const modifiedMeals = Number(day?.modified_meals ?? 0)
    const registeredMeals = Number(day?.registered_meals ?? 0)
    const omittedMeals = Math.max(0, registeredMeals - completedMeals - modifiedMeals)

    return {
      dayLabel: day?.day_label ?? WEEKDAY_LABELS[index] ?? `Dia ${index + 1}`,
      completedMeals,
      modifiedMeals,
      omittedMeals,
      registeredMeals,
    }
  })
}

function WeeklyRegisteredMealsTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  const point = payload[0]?.payload
  if (!point) return null

  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <p>Comidas registradas: {formatCompactNumber(point.registeredMeals, { maximumFractionDigits: 0 })}</p>
      <p>Completadas (1): {formatCompactNumber(point.completedMeals, { maximumFractionDigits: 0 })}</p>
      <p>Modificadas (0.5): {formatCompactNumber(point.modifiedMeals, { maximumFractionDigits: 0 })}</p>
      <p>Omitidas (0): {formatCompactNumber(point.omittedMeals, { maximumFractionDigits: 0 })}</p>
    </div>
  )
}

function isSameAdjustmentWeek(entry, analysis) {
  if (!entry || !analysis) return false
  return (
    entry.previous_week_label === analysis.previous_week_label
    && entry.current_week_label === analysis.current_week_label
  )
}

function isMonday(createdAt) {
  if (!createdAt) return false
  return new Date(createdAt).getDay() === 1
}

function buildWeeklyAdjustmentStatus(analysis, adjustment) {
  if (adjustment) {
    if (adjustment.adjustment_applied) {
      return {
        tone: 'success',
        label: isMonday(adjustment.created_at) ? 'Ajuste aplicado el lunes' : 'Ajuste aplicado esta semana',
        detail: adjustment.adjustment_reason,
        appliedChange: adjustment.calorie_change,
      }
    }

    if (adjustment.progress_status === 'needs_attention') {
      return {
        tone: 'muted',
        label: 'Ajuste no aplicado (datos insuficientes)',
        detail: adjustment.adjustment_reason,
        appliedChange: adjustment.calorie_change,
      }
    }

    return {
      tone: 'neutral',
      label: 'Sin ajuste (peso estable)',
      detail: adjustment.adjustment_reason,
      appliedChange: 0,
    }
  }

  if (!analysis?.can_analyze) {
    return {
      tone: 'muted',
      label: 'Ajuste no aplicado (datos insuficientes)',
      detail: analysis?.adjustment_reason || 'Todavia no hay una semana completa para analizar.',
      appliedChange: null,
    }
  }

  if (!analysis.adjustment_needed && analysis.calorie_change === 0) {
    return {
      tone: 'neutral',
      label: 'Sin ajuste (peso estable)',
      detail: analysis.adjustment_reason,
      appliedChange: 0,
    }
  }

  if (analysis.progress_status === 'needs_attention') {
    return {
      tone: 'muted',
      label: 'Ajuste no aplicado (datos insuficientes)',
      detail: analysis.adjustment_reason,
      appliedChange: analysis.calorie_change,
    }
  }

  return {
    tone: 'neutral',
    label: 'Ajuste pendiente de sincronizacion',
    detail: analysis.adjustment_reason,
    appliedChange: analysis.calorie_change,
  }
}

function resolveAdjustmentOutcomeLabel(adjustmentStatus, adjustmentEntry) {
  if (adjustmentEntry?.adjustment_applied) {
    return formatSignedCalories(adjustmentEntry.calorie_change)
  }
  if (adjustmentEntry && adjustmentEntry.calorie_change === 0) {
    return 'Sin cambios'
  }
  if (adjustmentEntry && adjustmentEntry.calorie_change !== 0) {
    return 'No aplicado'
  }
  if (adjustmentStatus.appliedChange === null || adjustmentStatus.appliedChange === undefined) {
    return 'Pendiente'
  }
  if (adjustmentStatus.appliedChange === 0) {
    return 'Sin cambios'
  }
  return formatSignedCalories(adjustmentStatus.appliedChange)
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
  const [weeklyAdjustmentStatus, setWeeklyAdjustmentStatus] = useState(buildWeeklyAdjustmentStatus(null, null))
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [isSummaryLoading, setIsSummaryLoading] = useState(false)
  const [isWeeklyAveragesLoading, setIsWeeklyAveragesLoading] = useState(false)
  const [isWeeklyAnalysisLoading, setIsWeeklyAnalysisLoading] = useState(false)
  const [isWeeklyAdherenceLoading, setIsWeeklyAdherenceLoading] = useState(false)
  const [isDashboardLoading, setIsDashboardLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isApplyingAdjustment, setIsApplyingAdjustment] = useState(false)
  const [deletingEntryId, setDeletingEntryId] = useState('')
  const [editingEntryId, setEditingEntryId] = useState('')

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
    const [weightEntries, progressSummary, analysis, averages, adjustmentEntries, snapshot] = await Promise.all([
      loadWeightHistory(activeToken),
      loadProgressSummary(activeToken),
      loadWeeklyAnalysis(activeToken),
      loadWeeklyAverages(activeToken),
      loadAdjustmentHistory(activeToken),
      loadDashboardSnapshot(activeToken),
    ])
    const adherence = await loadWeeklyAdherenceSummary(activeToken, analysis?.current_week_label ?? null)
    return {
      weightEntries,
      progressSummary,
      analysis,
      averages,
      adjustmentEntries,
      snapshot,
      adherence,
    }
  }

  async function syncWeeklyAdjustment(activeToken = token) {
    if (!activeToken) return null
    setIsApplyingAdjustment(true)
    setApplyError('')

    try {
      const response = await progressApi.applyWeeklyAdjustment(activeToken)
      if (response.adjustment?.adjustment_applied) {
        await refreshUser(activeToken)
      }

      const refreshedData = await reloadAll(activeToken)
      const matchingAdjustment = refreshedData.adjustmentEntries.find((entry) => isSameAdjustmentWeek(entry, refreshedData.analysis)) ?? response.adjustment ?? null
      setWeeklyAdjustmentStatus(buildWeeklyAdjustmentStatus(refreshedData.analysis ?? response.analysis, matchingAdjustment))
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      return {
        analysis: refreshedData.analysis ?? response.analysis,
        adjustment: matchingAdjustment,
      }
    } catch (error) {
      setApplyError(error.message)
      setWeeklyAdjustmentStatus({
        tone: 'error',
        label: 'Error al guardar',
        detail: error.message,
        appliedChange: null,
      })
      return null
    } finally {
      setIsApplyingAdjustment(false)
    }
  }

  async function syncWeeklyAdjustmentIfNeeded(activeToken = token, analysis = weeklyAnalysis, adjustmentEntries = adjustmentHistory) {
    const matchingAdjustment = adjustmentEntries.find((entry) => isSameAdjustmentWeek(entry, analysis)) ?? null

    if (!analysis?.can_analyze) {
      setWeeklyAdjustmentStatus(buildWeeklyAdjustmentStatus(analysis, matchingAdjustment))
      return { analysis, adjustment: matchingAdjustment }
    }

    if (matchingAdjustment) {
      setWeeklyAdjustmentStatus(buildWeeklyAdjustmentStatus(analysis, matchingAdjustment))
      return { analysis, adjustment: matchingAdjustment }
    }

    return syncWeeklyAdjustment(activeToken)
  }

  useEffect(() => {
    if (!token) return undefined

    let isActive = true

    async function initializeProgress() {
      const data = await reloadAll(token)
      if (!isActive) return
      await syncWeeklyAdjustmentIfNeeded(token, data.analysis, data.adjustmentEntries)
    }

    initializeProgress()

    return () => {
      isActive = false
    }
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
      const payload = {
        weight: Number(weightForm.weight),
        date: weightForm.date,
      }
      if (editingEntryId) {
        await weightApi.updateWeightEntry(token, editingEntryId, payload)
      } else {
        await weightApi.createWeightEntry(token, payload)
      }
      const data = await reloadAll(token)
      await syncWeeklyAdjustmentIfNeeded(token, data.analysis, data.adjustmentEntries)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      setSaveMessage(editingEntryId ? 'Peso actualizado correctamente.' : 'Registro de peso guardado correctamente.')
      setEditingEntryId('')
      setWeightForm({
        weight: '',
        date: getTodayDateInputValue(),
      })
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
      if (editingEntryId === entryId) {
        setEditingEntryId('')
        setWeightForm({
          weight: '',
          date: getTodayDateInputValue(),
        })
      }
      const data = await reloadAll(token)
      await syncWeeklyAdjustmentIfNeeded(token, data.analysis, data.adjustmentEntries)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
    } catch (error) {
      setHistoryError(error.message)
    } finally {
      setDeletingEntryId('')
    }
  }

  const chartSeries = buildTrendSeries(
    dashboardSnapshot?.weight_progress?.entries,
    dashboardSnapshot?.weight_progress?.expected_trend,
    weeklyAverages,
  )
  const dashboardAdherence = dashboardSnapshot?.adherence ?? null
  const referenceWeekLabel = (
    weeklyAdherenceSummary?.week_label
    ?? weeklyAnalysis?.current_week_label
    ?? dashboardAdherence?.week_label
    ?? null
  )
  const confidenceScore = resolveConfidencePercentage(weeklyAdherenceSummary)
  const adherencePercentage = resolveRegisteredAdherencePercentage(
    weeklyAdherenceSummary ?? dashboardAdherence,
  )
  const coveragePercentage = (
    weeklyAdherenceSummary?.tracking_coverage_percentage
    ?? dashboardAdherence?.tracking_coverage_percentage
    ?? 0
  )
  const canRenderSharedDailyBreakdown = (
    !weeklyAdherenceSummary?.week_label
    || !dashboardAdherence?.week_label
    || weeklyAdherenceSummary.week_label === dashboardAdherence.week_label
  )
  const dailyBreakdown = canRenderSharedDailyBreakdown
    ? (dashboardAdherence?.daily_breakdown ?? [])
    : []
  const weeklyRegisteredMealsSeries = buildWeeklyRegisteredMealsSeries(dailyBreakdown)
  const weeklyBreakdownDescription = canRenderSharedDailyBreakdown && dashboardAdherence?.start_date && dashboardAdherence?.end_date
    ? `Comidas registradas por dia en la misma semana de referencia: ${formatDateLabel(dashboardAdherence.start_date, { month: 'short', day: '2-digit' })} a ${formatDateLabel(dashboardAdherence.end_date, { month: 'short', day: '2-digit', year: 'numeric' })}.`
    : 'Comidas registradas por dia en la misma semana de referencia.'
  const recentEntries = [...entries].slice(-3).reverse()
  const todayEntry = entries.find((entry) => entry.date === getTodayDateInputValue())
  const currentAdjustment = adjustmentHistory.find((entry) => isSameAdjustmentWeek(entry, weeklyAnalysis)) ?? null
  const adjustmentOutcomeLabel = resolveAdjustmentOutcomeLabel(weeklyAdjustmentStatus, currentAdjustment)

  function handleEditTodayEntry() {
    if (!todayEntry) return
    setEditingEntryId(todayEntry.id)
    setSaveError('')
    setSaveMessage('')
    setWeightForm({
      weight: String(todayEntry.weight),
      date: todayEntry.date,
    })
  }

  function handleCancelEdit() {
    setEditingEntryId('')
    setSaveError('')
    setWeightForm({
      weight: '',
      date: getTodayDateInputValue(),
    })
  }

  return (
    <div className="progress-page">
      {(isHistoryLoading || isSummaryLoading || isWeeklyAveragesLoading || isWeeklyAnalysisLoading || isWeeklyAdherenceLoading || isDashboardLoading)
        ? <p className="page-status">Cargando progreso...</p>
        : null}
      {(historyError || summaryError || weeklyAveragesError || weeklyAnalysisError || weeklyAdherenceError || dashboardError || saveError || applyError)
        ? <p className="page-status page-status-error">{historyError || summaryError || weeklyAveragesError || weeklyAnalysisError || weeklyAdherenceError || dashboardError || saveError || applyError}</p>
        : null}

      <div className="progress-hero-grid">
        <SectionPanel eyebrow="Registro diario" title="Registrar peso" className="progress-hero-card progress-weight-card">
          <form className="progress-log-form progress-weight-form" onSubmit={handleSave}>
            <label><span>Peso (kg)</span><input type="number" step="0.1" min="0" value={weightForm.weight} onChange={(event) => setWeightForm((current) => ({ ...current, weight: event.target.value }))} required /></label>
            <label><span>Fecha</span><input type="date" value={weightForm.date} onChange={(event) => setWeightForm((current) => ({ ...current, date: event.target.value }))} disabled={Boolean(editingEntryId)} required /></label>
            <button type="submit" className="panel-cta-button progress-weight-submit" disabled={isSaving}>{isSaving ? 'Guardando...' : editingEntryId ? 'Actualizar peso' : 'Registrar peso'}</button>
          </form>

          <div className="progress-weight-meta">
            <div><small>Ultimo peso</small><strong>{summary?.latest_weight ? formatMass(summary.latest_weight) : 'Sin registros'}</strong></div>
            <div><small>Historial</small><strong>{summary?.number_of_entries ? `${summary.number_of_entries} registros` : 'Empieza esta semana'}</strong></div>
          </div>

          <div className="progress-weight-actions">
            {todayEntry && !editingEntryId ? <button type="button" className="protocol-chip-button" onClick={handleEditTodayEntry}>Modificar peso de hoy</button> : null}
            {editingEntryId ? <button type="button" className="protocol-chip-button" onClick={handleCancelEdit}>Cancelar edicion</button> : null}
          </div>
        </SectionPanel>

        <SectionPanel eyebrow="Resumen semanal" className="progress-hero-card progress-summary-card">
          <div className="progress-summary-layout">
            <div className="progress-summary-left">
              <CircularGauge
                value={confidenceScore}
                label="Fiabilidad"
                caption={referenceWeekLabel ? `Semana ${referenceWeekLabel}` : undefined}
              />
            </div>

            <div className="progress-summary-right progress-summary-meta">
              <div className="progress-summary-stat">
                <small>Cobertura</small>
                <strong>{formatPercent(coveragePercentage, 0)}</strong>
              </div>
              <div className="progress-summary-stat">
                <small>Adherencia</small>
                <strong>{formatPercent(adherencePercentage, 0)}</strong>
              </div>
              <div className="progress-summary-stat">
                <small>Cambio semanal</small>
                <strong>{formatSignedMass(weeklyAnalysis?.weekly_change, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}</strong>
              </div>
              <div className="progress-summary-stat progress-summary-stat-danger">
                <small>Ajuste calorico</small>
                <strong>{formatSignedCalories(weeklyAnalysis?.calorie_change)}</strong>
              </div>
            </div>
          </div>

          <div className={`progress-summary-status progress-summary-status-${weeklyAdjustmentStatus.tone}`.trim()}>
            <div className="progress-summary-status-head">
              <strong>{weeklyAdjustmentStatus.label}</strong>
              <span>{weeklyAnalysis?.current_week_label ?? 'Pendiente'} - {adjustmentOutcomeLabel}</span>
            </div>
            <p>
              {isApplyingAdjustment
                ? 'Sincronizando el ajuste semanal automatico...'
                : weeklyAdjustmentStatus.detail}
            </p>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="Tendencia del peso"
        description="Comparacion entre la evolucion real y la tendencia esperada."
        actions={<div className="legend-group"><span><i className="legend-dot legend-dot-primary" />Actual</span><span><i className="legend-dot legend-dot-muted" />Esperado</span></div>}
      >
        <div className="dashboard-chart-wrap">
          {chartSeries.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartSeries}>
                <CartesianGrid stroke="rgba(118, 117, 118, 0.18)" strokeDasharray="4 6" vertical={false} />
                <XAxis dataKey="axisLabel" axisLine={false} tickLine={false} tick={{ fill: '#adacab', fontSize: 10, fontWeight: 700 }} />
                <YAxis hide domain={['auto', 'auto']} />
                <Tooltip content={<TrendTooltip />} />
                <Line type="monotone" dataKey="expectedWeight" stroke="#484849" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="actualWeight" stroke="#daf900" strokeWidth={4} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : <p className="panel-placeholder">Los datos de peso apareceran aqui tras los primeros registros.</p>}
        </div>
      </SectionPanel>

      <div className="progress-bottom-layout">
        <SectionPanel
          title={referenceWeekLabel ? `Adherencia semanal - ${referenceWeekLabel}` : 'Adherencia semanal'}
          description={weeklyBreakdownDescription}
          actions={<div className="legend-group"><span><i className="legend-dot legend-dot-primary" />Cuenta 1</span><span><i className="legend-dot legend-dot-info" />Cuenta 0.5</span><span><i className="legend-dot legend-dot-muted" />Cuenta 0</span></div>}
        >
          <div className="dashboard-chart-wrap">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={weeklyRegisteredMealsSeries} margin={{ top: 8, right: 8, bottom: 8, left: -10 }}>
                <CartesianGrid stroke="rgba(118, 117, 118, 0.18)" strokeDasharray="4 6" vertical={false} />
                <XAxis
                  dataKey="dayLabel"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#adacab', fontSize: 10, fontWeight: 700 }}
                />
                <YAxis
                  allowDecimals={false}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#adacab', fontSize: 10, fontWeight: 700 }}
                />
                <Tooltip content={<WeeklyRegisteredMealsTooltip />} />
                <Bar dataKey="completedMeals" stackId="registeredMeals" fill="#daf900" radius={[6, 6, 0, 0]} />
                <Bar dataKey="modifiedMeals" stackId="registeredMeals" fill="#00d4ff" />
                <Bar dataKey="omittedMeals" stackId="registeredMeals" fill="#484849" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionPanel>

        <div className="progress-side-stack">
          <SectionPanel title="Registros recientes">
            {recentEntries.length > 0 ? (
              <div className="recent-log-list">
                {recentEntries.map((entry) => (
                  <article key={entry.id} className="recent-log-item">
                    <div className="recent-log-copy">
                      <strong>{formatMass(entry.weight)}</strong>
                      <small>{formatDayLabel(entry.date)} - {formatDateLabel(entry.date, { month: 'short', day: '2-digit', year: 'numeric' })}</small>
                    </div>
                    <button type="button" className="protocol-chip-button" disabled={deletingEntryId === entry.id} onClick={() => handleDelete(entry.id)}>
                      {deletingEntryId === entry.id ? 'Borrando...' : 'Borrar'}
                    </button>
                  </article>
                ))}
              </div>
            ) : <p className="panel-placeholder">Los registros de peso recientes apareceran aqui.</p>}
          </SectionPanel>
        </div>
      </div>

      <AdjustmentHistory entries={adjustmentHistory} isLoading={false} error="" />

      {saveMessage ? <p className="page-status page-status-success">{saveMessage}</p> : null}
    </div>
  )
}

export default ProgressPage
