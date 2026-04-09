import { useEffect, useState } from 'react'
import * as dietsApi from '../api/dietsApi'
import DietCard from '../components/DietCard'
import DietGeneratorForm from '../components/DietGeneratorForm'
import DietHistory from '../components/DietHistory'
import { useAuth } from '../context/AuthContext'

function DietsPage() {
  const { token } = useAuth()
  const [latestDiet, setLatestDiet] = useState(null)
  const [selectedDiet, setSelectedDiet] = useState(null)
  const [dietHistory, setDietHistory] = useState([])
  const [latestDietError, setLatestDietError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [generateError, setGenerateError] = useState('')
  const [generateMessage, setGenerateMessage] = useState('')
  const [selectedDietError, setSelectedDietError] = useState('')
  const [isLatestDietLoading, setIsLatestDietLoading] = useState(false)
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [viewingDietId, setViewingDietId] = useState('')

  async function loadLatestDiet(activeToken = token) {
    if (!activeToken) {
      return null
    }

    setIsLatestDietLoading(true)
    setLatestDietError('')

    try {
      const diet = await dietsApi.getLatestDiet(activeToken)
      setLatestDiet(diet)
      setSelectedDiet((currentDiet) => currentDiet ?? diet)
      return diet
    } catch (error) {
      setLatestDiet(null)
      setLatestDietError(error.message)
      return null
    } finally {
      setIsLatestDietLoading(false)
    }
  }

  async function loadDietHistory(activeToken = token) {
    if (!activeToken) {
      return []
    }

    setIsHistoryLoading(true)
    setHistoryError('')

    try {
      const response = await dietsApi.getDietHistory(activeToken)
      setDietHistory(response.diets)
      return response.diets
    } catch (error) {
      setDietHistory([])
      setHistoryError(error.message)
      return []
    } finally {
      setIsHistoryLoading(false)
    }
  }

  async function reloadAll(activeToken = token) {
    await Promise.all([
      loadLatestDiet(activeToken),
      loadDietHistory(activeToken),
    ])
  }

  useEffect(() => {
    if (!token) {
      return
    }

    reloadAll(token)
  }, [token])

  async function handleGenerate(payload) {
    if (!token) {
      return false
    }

    setIsGenerating(true)
    setGenerateError('')
    setGenerateMessage('')
    setSelectedDietError('')

    try {
      const createdDiet = await dietsApi.generateDiet(token, payload)
      setLatestDiet(createdDiet)
      setSelectedDiet(createdDiet)
      await loadDietHistory(token)
      setGenerateMessage('Dieta diaria por alimentos generada y guardada correctamente.')
      return true
    } catch (error) {
      setGenerateError(error.message)
      return false
    } finally {
      setIsGenerating(false)
    }
  }

  async function handleSelectDiet(dietId) {
    if (!token) {
      return
    }

    setViewingDietId(dietId)
    setSelectedDietError('')

    try {
      const diet = await dietsApi.getDietById(token, dietId)
      setSelectedDiet(diet)
    } catch (error) {
      setSelectedDietError(error.message)
    } finally {
      setViewingDietId('')
    }
  }

  return (
    <div className="diets-page">
      <div className="progress-grid">
        <DietGeneratorForm
          error={generateError}
          isGenerating={isGenerating}
          message={generateMessage}
          onGenerate={handleGenerate}
        />
        <DietCard
          title="Ultima dieta disponible"
          description="Mostramos la ultima dieta generada o la que selecciones desde el historial, ya convertida en alimentos y cantidades."
          diet={selectedDiet ?? latestDiet}
          error={selectedDietError || latestDietError}
          isLoading={isLatestDietLoading || Boolean(viewingDietId)}
        />
      </div>

      <DietHistory
        diets={dietHistory}
        error={historyError}
        isLoading={isHistoryLoading}
        onSelect={handleSelectDiet}
        selectedDietId={selectedDiet?.id ?? latestDiet?.id ?? ''}
        viewingDietId={viewingDietId}
      />
    </div>
  )
}

export default DietsPage
