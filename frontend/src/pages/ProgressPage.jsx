import { useEffect, useState } from 'react'
import * as weightApi from '../api/weightApi'
import WeightForm from '../components/WeightForm'
import WeightHistory from '../components/WeightHistory'
import ProgressSummary from '../components/ProgressSummary'
import { useAuth } from '../context/AuthContext'

function ProgressPage() {
  const { token } = useAuth()
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [historyError, setHistoryError] = useState('')
  const [summaryError, setSummaryError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [isSummaryLoading, setIsSummaryLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
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

  async function reloadProgress(activeToken = token) {
    await Promise.all([
      loadWeightHistory(activeToken),
      loadProgressSummary(activeToken),
    ])
  }

  useEffect(() => {
    if (!token) {
      return
    }

    reloadProgress(token)
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
      await reloadProgress(token)
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
      await reloadProgress(token)
    } catch (error) {
      setHistoryError(error.message)
    } finally {
      setDeletingEntryId('')
    }
  }

  return (
    <div className="progress-page">
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
    </div>
  )
}

export default ProgressPage
