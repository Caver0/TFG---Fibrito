import { useEffect, useState } from 'react'
import * as adherenceApi from '../api/adherenceApi'
import * as dietsApi from '../api/dietsApi'
import AdherencePanel from '../components/AdherencePanel'
import DietCard from '../components/DietCard'
import DietGeneratorForm from '../components/DietGeneratorForm'
import DietHistory from '../components/DietHistory'
import WeeklyAdherenceSummary from '../components/WeeklyAdherenceSummary'
import { useAuth } from '../context/AuthContext'

function getTodayDateInputValue() {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatAdherenceStatusLabel(status) {
  if (status === 'completed') {
    return 'completada'
  }
  if (status === 'omitted') {
    return 'omitida'
  }
  if (status === 'modified') {
    return 'modificada'
  }
  return 'pendiente'
}

function buildAdherenceActionMessage(mealNumber, status) {
  if (status === 'pending') {
    return `La comida ${mealNumber} ha vuelto a estado pendiente.`
  }

  return `La comida ${mealNumber} ha quedado marcada como ${formatAdherenceStatusLabel(status)}.`
}

function DietsPage() {
  const { token } = useAuth()
  const [latestDiet, setLatestDiet] = useState(null)
  const [selectedDiet, setSelectedDiet] = useState(null)
  const [dietHistory, setDietHistory] = useState([])
  const [selectedAdherenceDate, setSelectedAdherenceDate] = useState(getTodayDateInputValue)
  const [dietAdherence, setDietAdherence] = useState(null)
  const [weeklyAdherenceSummary, setWeeklyAdherenceSummary] = useState(null)
  const [latestDietError, setLatestDietError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [generateError, setGenerateError] = useState('')
  const [generateMessage, setGenerateMessage] = useState('')
  const [selectedDietError, setSelectedDietError] = useState('')
  const [dietActionError, setDietActionError] = useState('')
  const [dietActionMessage, setDietActionMessage] = useState('')
  const [dietActionSummary, setDietActionSummary] = useState(null)
  const [adherenceError, setAdherenceError] = useState('')
  const [adherenceMessage, setAdherenceMessage] = useState('')
  const [weeklyAdherenceError, setWeeklyAdherenceError] = useState('')
  const [isLatestDietLoading, setIsLatestDietLoading] = useState(false)
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isMealActionLoading, setIsMealActionLoading] = useState(false)
  const [isDietAdherenceLoading, setIsDietAdherenceLoading] = useState(false)
  const [isWeeklyAdherenceLoading, setIsWeeklyAdherenceLoading] = useState(false)
  const [isSavingMealAdherence, setIsSavingMealAdherence] = useState(false)
  const [viewingDietId, setViewingDietId] = useState('')
  const [activeMealNumber, setActiveMealNumber] = useState(null)
  const [activeFoodCode, setActiveFoodCode] = useState('')
  const [activeAdherenceMealNumber, setActiveAdherenceMealNumber] = useState(null)
  const currentDietId = selectedDiet?.id ?? latestDiet?.id ?? ''
  const adherenceRecordsByMeal = Object.fromEntries(
    (dietAdherence?.meals ?? []).map((mealEntry) => [mealEntry.meal_number, mealEntry]),
  )

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

  async function loadDietAdherence(
    dietId = currentDietId,
    dateValue = selectedAdherenceDate,
    activeToken = token,
  ) {
    if (!activeToken || !dietId) {
      setDietAdherence(null)
      return null
    }

    setIsDietAdherenceLoading(true)
    setAdherenceError('')

    try {
      const response = await adherenceApi.getDietAdherence(activeToken, dietId, dateValue)
      setDietAdherence(response)
      return response
    } catch (error) {
      setDietAdherence(null)
      setAdherenceError(error.message)
      return null
    } finally {
      setIsDietAdherenceLoading(false)
    }
  }

  async function loadWeeklyAdherence(
    dateValue = selectedAdherenceDate,
    activeToken = token,
  ) {
    if (!activeToken) {
      setWeeklyAdherenceSummary(null)
      return null
    }

    setIsWeeklyAdherenceLoading(true)
    setWeeklyAdherenceError('')

    try {
      const response = await adherenceApi.getWeeklyAdherenceSummary(activeToken, {
        reference_date: dateValue,
      })
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

  useEffect(() => {
    if (!token) {
      return
    }

    reloadAll(token)
  }, [token])

  useEffect(() => {
    if (!token) {
      return
    }

    if (currentDietId) {
      loadDietAdherence(currentDietId, selectedAdherenceDate, token)
    } else {
      setDietAdherence(null)
    }

    loadWeeklyAdherence(selectedAdherenceDate, token)
  }, [token, currentDietId, selectedAdherenceDate])

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
    setAdherenceError('')
    setAdherenceMessage('')

    try {
      const createdDiet = await dietsApi.generateDiet(token, payload)
      setLatestDiet(createdDiet)
      setSelectedDiet(createdDiet)
      await loadDietHistory(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
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
    setAdherenceMessage('')
    setAdherenceError('')

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
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
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
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
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

  async function handleSaveMealAdherence(dietId, mealNumber, payload) {
    if (!token) {
      return false
    }

    setIsSavingMealAdherence(true)
    setActiveAdherenceMealNumber(mealNumber)
    setAdherenceError('')
    setAdherenceMessage('')

    try {
      const response = await adherenceApi.saveMealAdherence(token, {
        diet_id: dietId,
        meal_number: mealNumber,
        date: selectedAdherenceDate,
        ...payload,
      })
      await Promise.all([
        loadDietAdherence(dietId, selectedAdherenceDate, token),
        loadWeeklyAdherence(selectedAdherenceDate, token),
      ])
      setAdherenceMessage(buildAdherenceActionMessage(mealNumber, response.status))
      window.dispatchEvent(new CustomEvent('adherence:updated', {
        detail: {
          date: selectedAdherenceDate,
          dietId,
        },
      }))
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      return true
    } catch (error) {
      setAdherenceError(error.message)
      return false
    } finally {
      setIsSavingMealAdherence(false)
      setActiveAdherenceMealNumber(null)
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
            activeAdherenceMealNumber={activeAdherenceMealNumber}
            activeFoodCode={activeFoodCode}
            activeMealNumber={activeMealNumber}
            adherenceRecordsByMeal={adherenceRecordsByMeal}
            title="Ultima dieta disponible"
            description="Mostramos la ultima dieta generada o la que selecciones desde el historial, ya convertida en alimentos y cantidades."
            diet={selectedDiet ?? latestDiet}
            error={selectedDietError || latestDietError}
            isAdherenceSaving={isSavingMealAdherence}
            isLoading={isLatestDietLoading || Boolean(viewingDietId)}
            isMealActionLoading={isMealActionLoading}
            onLoadReplacementOptions={handleLoadReplacementOptions}
            onRegenerateMeal={handleRegenerateMeal}
            onSaveMealAdherence={handleSaveMealAdherence}
            onReplaceFood={handleReplaceFood}
          />

          {(selectedDiet ?? latestDiet) ? (
            <>
              <AdherencePanel
                error={adherenceError}
                isLoading={isDietAdherenceLoading}
                message={adherenceMessage}
                onDateChange={setSelectedAdherenceDate}
                selectedDate={selectedAdherenceDate}
                summary={dietAdherence?.daily_summary ?? null}
              />

              <WeeklyAdherenceSummary
                description="Esta lectura semanal resume cuanto se ha seguido el plan durante la semana de la fecha seleccionada y cuanta confianza aporta al interpretar la evolucion del peso."
                error={weeklyAdherenceError}
                isLoading={isWeeklyAdherenceLoading}
                summary={weeklyAdherenceSummary}
                title="Interpretacion semanal de adherencia"
              />
            </>
          ) : null}
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
