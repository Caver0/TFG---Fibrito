import { useEffect, useState } from 'react'
import * as progressApi from '../api/progressApi'
import * as weightApi from '../api/weightApi'
import AdjustmentHistory from '../components/AdjustmentHistory'
import ProgressSummary from '../components/ProgressSummary'
import WeeklyAnalysisCard from '../components/WeeklyAnalysisCard'
import WeeklyAveragesCard from '../components/WeeklyAveragesCard'
import WeightForm from '../components/WeightForm'
import WeightHistory from '../components/WeightHistory'
import { useAuth } from '../context/AuthContext'

function ProgressPage() {
  const { refreshUser, token } = useAuth()
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [weeklyAverages, setWeeklyAverages] = useState([])
  const [weeklyAnalysis, setWeeklyAnalysis] = useState(null)
  const [adjustmentHistory, setAdjustmentHistory] = useState([])
  const [historyError, setHistoryError] = useState('')
  const [summaryError, setSummaryError] = useState('')
  const [weeklyAveragesError, setWeeklyAveragesError] = useState('')
  const [weeklyAnalysisError, setWeeklyAnalysisError] = useState('')
  const [adjustmentHistoryError, setAdjustmentHistoryError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [applyError, setApplyError] = useState('')
  const [applyMessage, setApplyMessage] = useState('')
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [isSummaryLoading, setIsSummaryLoading] = useState(false)
  const [isWeeklyAveragesLoading, setIsWeeklyAveragesLoading] = useState(false)
  const [isWeeklyAnalysisLoading, setIsWeeklyAnalysisLoading] = useState(false)
  const [isAdjustmentHistoryLoading, setIsAdjustmentHistoryLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isApplyingAdjustment, setIsApplyingAdjustment] = useState(false)
  const [deletingEntryId, setDeletingEntryId] = useState('')

  async function loadWeightHistory(activeToken = token) {
    if (!activeToken) {
      return []
    }

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
    if (!activeToken) {
      return null
    }

    setIsSummaryLoading(true)
    setSummaryError('')

    try {
      const nextSummary = await weightApi.getProgressSummary(activeToken)
      setSummary(nextSummary)
      return nextSummary
    } catch (error) {
      setSummary(null)
      setSummaryError(error.message)
      return null
    } finally {
      setIsSummaryLoading(false)
    }
  }

  async function loadWeeklyAverages(activeToken = token) {
    if (!activeToken) {
      return []
    }

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
    if (!activeToken) {
      return null
    }

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

  async function loadAdjustmentHistory(activeToken = token) {
    if (!activeToken) {
      return []
    }

    setIsAdjustmentHistoryLoading(true)
    setAdjustmentHistoryError('')

    try {
      const response = await progressApi.getAdjustmentHistory(activeToken)
      setAdjustmentHistory(response.entries)
      return response.entries
    } catch (error) {
      setAdjustmentHistory([])
      setAdjustmentHistoryError(error.message)
      return []
    } finally {
      setIsAdjustmentHistoryLoading(false)
    }
  }

  async function reloadWeightData(activeToken = token) {
    await Promise.all([
      loadWeightHistory(activeToken),
      loadProgressSummary(activeToken),
    ])
  }

  async function reloadWeeklyData(activeToken = token) {
    await Promise.all([
      loadWeeklyAverages(activeToken),
      loadWeeklyAnalysis(activeToken),
      loadAdjustmentHistory(activeToken),
    ])
  }

  async function reloadAll(activeToken = token) {
    await Promise.all([
      reloadWeightData(activeToken),
      reloadWeeklyData(activeToken),
    ])
  }

  useEffect(() => {
    if (!token) {
      return
    }

    reloadAll(token)
  }, [token])

  async function handleSave(payload) {
    if (!token) {
      return false
    }

    setIsSaving(true)
    setSaveError('')
    setSaveMessage('')

    try {
      await weightApi.createWeightEntry(token, payload)
      await reloadAll(token)
      setSaveMessage('Registro de peso guardado correctamente.')
      return true
    } catch (error) {
      setSaveError(error.message)
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDelete(entryId) {
    if (!token) {
      return
    }

    setDeletingEntryId(entryId)
    setHistoryError('')
    setSummaryError('')

    try {
      await weightApi.deleteWeightEntry(token, entryId)
      await reloadAll(token)
    } catch (error) {
      setHistoryError(error.message)
    } finally {
      setDeletingEntryId('')
    }
  }

  async function handleApplyAdjustment() {
    if (!token) {
      return
    }

    setIsApplyingAdjustment(true)
    setApplyError('')
    setApplyMessage('')

    try {
      const response = await progressApi.applyWeeklyAdjustment(token)
      setWeeklyAnalysis(response.analysis)
      await refreshUser(token)
      await reloadWeeklyData(token)
      if (response.analysis.adjustment_reason.startsWith('Ya existe un analisis guardado')) {
        setApplyMessage(response.analysis.adjustment_reason)
      } else if (response.adjustment?.adjustment_applied) {
        setApplyMessage('Ajuste semanal aplicado y guardado correctamente.')
      } else if (response.adjustment) {
        setApplyMessage('Analisis semanal guardado sin cambios de calorias.')
      } else {
        setApplyMessage(response.analysis.adjustment_reason)
      }
    } catch (error) {
      setApplyError(error.message)
    } finally {
      setIsApplyingAdjustment(false)
    }
  }

  return (
    <div className="progress-page">
      <section id="panel-registro-peso" className="dashboard-scroll-section progress-section">
        <div className="progress-grid">
          <WeightForm
            error={saveError}
            isSaving={isSaving}
            message={saveMessage}
            onSave={handleSave}
          />
          <ProgressSummary
            error={summaryError}
            isLoading={isSummaryLoading}
            summary={summary}
          />
        </div>

        <WeightHistory
          entries={entries}
          error={historyError}
          isLoading={isHistoryLoading}
          onDelete={handleDelete}
          deletingEntryId={deletingEntryId}
        />
      </section>

      <section id="panel-analisis-progreso" className="dashboard-scroll-section progress-section">
        <div className="progress-grid">
          <WeeklyAveragesCard
            averages={weeklyAverages}
            error={weeklyAveragesError}
            isLoading={isWeeklyAveragesLoading}
          />
          <WeeklyAnalysisCard
            analysis={weeklyAnalysis}
            applyError={applyError}
            applyMessage={applyMessage}
            error={weeklyAnalysisError}
            isApplying={isApplyingAdjustment}
            isLoading={isWeeklyAnalysisLoading}
            onApply={handleApplyAdjustment}
          />
        </div>

        <AdjustmentHistory
          entries={adjustmentHistory}
          error={adjustmentHistoryError}
          isLoading={isAdjustmentHistoryLoading}
        />
      </section>
    </div>
  )
}

export default ProgressPage
