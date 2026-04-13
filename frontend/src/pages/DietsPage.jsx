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
  const [dietActionError, setDietActionError] = useState('')
  const [dietActionMessage, setDietActionMessage] = useState('')
  const [dietActionSummary, setDietActionSummary] = useState(null)
  const [isLatestDietLoading, setIsLatestDietLoading] = useState(false)
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isMealActionLoading, setIsMealActionLoading] = useState(false)
  const [viewingDietId, setViewingDietId] = useState('')
  const [activeMealNumber, setActiveMealNumber] = useState(null)
  const [activeFoodCode, setActiveFoodCode] = useState('')

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
    setDietActionError('')
    setDietActionMessage('')
    setDietActionSummary(null)

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
    setDietActionMessage('')
    setDietActionSummary(null)
    setDietActionError('')

    try {
      const diet = await dietsApi.getDietById(token, dietId)
      setSelectedDiet(diet)
      setDietActionError('')
    } catch (error) {
      setSelectedDietError(error.message)
    } finally {
      setViewingDietId('')
    }
  }

  function syncUpdatedDiet(updatedDiet) {
    setSelectedDiet(updatedDiet)
    setLatestDiet((currentDiet) => {
      if (!currentDiet || currentDiet.id === updatedDiet.id) {
        return updatedDiet
      }

      return currentDiet
    })
  }

  async function handleRegenerateMeal(dietId, mealNumber) {
    if (!token) {
      return false
    }

    setIsMealActionLoading(true)
    setActiveMealNumber(mealNumber)
    setActiveFoodCode('')
    setDietActionError('')
    setDietActionMessage('')

    try {
      const response = await dietsApi.regenerateMeal(token, dietId, mealNumber)
      syncUpdatedDiet(response.diet)
      setDietActionMessage(response.summary.message)
      setDietActionSummary(response.summary)
      await loadDietHistory(token)
      return true
    } catch (error) {
      setDietActionError(error.message)
      return false
    } finally {
      setIsMealActionLoading(false)
      setActiveMealNumber(null)
    }
  }

  async function handleReplaceFood(dietId, mealNumber, payload) {
    if (!token) {
      return false
    }

    setIsMealActionLoading(true)
    setActiveMealNumber(mealNumber)
    setActiveFoodCode(payload.current_food_code ?? '')
    setDietActionError('')
    setDietActionMessage('')

    try {
      const response = await dietsApi.replaceFoodInMeal(token, dietId, mealNumber, payload)
      syncUpdatedDiet(response.diet)
      setDietActionMessage(response.summary.message)
      setDietActionSummary(response.summary)
      await loadDietHistory(token)
      return true
    } catch (error) {
      setDietActionError(error.message)
      return false
    } finally {
      setIsMealActionLoading(false)
      setActiveMealNumber(null)
      setActiveFoodCode('')
    }
  }

  async function handleLoadReplacementOptions(mealNumber, food) {
    if (!token) {
      return { options: [] }
    }

    return dietsApi.getFoodReplacementOptions(token, (selectedDiet ?? latestDiet).id, mealNumber, {
      current_food_name: food.name,
      current_food_code: food.food_code,
    })
  }

  return (
    <div className="diets-page">
      <div className="diets-workspace">
        <aside className="diets-sidebar">
          <DietGeneratorForm
            error={generateError}
            isGenerating={isGenerating}
            message={generateMessage}
            onGenerate={handleGenerate}
          />
        </aside>

        <div className="diets-main">
          <DietCard
            actionError={dietActionError}
            actionMessage={dietActionMessage}
            actionSummary={dietActionSummary}
            activeFoodCode={activeFoodCode}
            activeMealNumber={activeMealNumber}
            title="Ultima dieta disponible"
            description="Mostramos la ultima dieta generada o la que selecciones desde el historial, ya convertida en alimentos y cantidades."
            diet={selectedDiet ?? latestDiet}
            error={selectedDietError || latestDietError}
            isLoading={isLatestDietLoading || Boolean(viewingDietId)}
            isMealActionLoading={isMealActionLoading}
            onLoadReplacementOptions={handleLoadReplacementOptions}
            onRegenerateMeal={handleRegenerateMeal}
            onReplaceFood={handleReplaceFood}
          />
        </div>
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
