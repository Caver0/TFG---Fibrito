import { useEffect, useState } from 'react'
import * as adherenceApi from '../api/adherenceApi'
import * as dietsApi from '../api/dietsApi'
import SectionPanel from '../components/SectionPanel'
import { useAuth } from '../context/AuthContext'
import {
  getDefaultDistributionTemplate,
  TRAINING_TIME_OPTIONS,
  validateDistribution,
} from '../utils/dietDistribution'
import {
  formatCalories,
  formatCompactNumber,
  formatDateLabel,
  formatMacro,
  formatPercent,
  formatSignedCalories,
  formatSignedMass,
  getMealVisual,
} from '../utils/stitch'
import {
  getReplacementOptionsForDisplay,
  mergeReplacementOptions,
  resolveCurrentMacroDominante,
} from '../utils/replacementLab'

function getTodayDateInputValue() {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function buildInitialGeneratorForm() {
  const defaultMealsCount = 4
  return {
    mealsCount: String(defaultMealsCount),
    trainingTimeOfDay: '',
    useCustomDistribution: false,
    customPercentages: getDefaultDistributionTemplate(defaultMealsCount).map((value) => String(value)),
  }
}

function formatMealStatus(status) {
  if (status === 'completed') return 'Completado'
  if (status === 'modified') return 'Modificado'
  if (status === 'omitted') return 'Omitido'
  return 'Pendiente'
}

function formatFoodPortion(food) {
  if (food.grams) {
    return `${formatCompactNumber(food.grams, { maximumFractionDigits: 0 })} g`
  }

  if (food.quantity && food.unit) {
    const quantity = Number(food.quantity)
    return `${formatCompactNumber(quantity, {
      maximumFractionDigits: quantity < 1 ? 2 : 1,
      minimumFractionDigits: Number.isInteger(quantity) ? 0 : 1,
    })} ${food.unit}`
  }

  return 'Cantidad no indicada'
}

function formatMacroDominante(value) {
  if (value === 'protein') return 'Proteína'
  if (value === 'carb') return 'Carbohidrato'
  if (value === 'fat') return 'Grasa'
  return value || 'No definido'
}

const GENERATION_LOADING_STAGES = [
  { label: 'Calculando perfil', progress: 22 },
  { label: 'Distribuyendo macros', progress: 58 },
  { label: 'Generando dieta', progress: 86 },
]

function formatReplacementValidationNote(candidate) {
  const note = String(candidate?.validation_note ?? '').trim()
  if (note) {
    return note
  }

  return candidate?.valid
    ? 'Compatible con esta comida.'
    : 'No compatible con esta comida.'
}

function DietsPage() {
  const { token } = useAuth()

  const [latestDiet, setLatestDiet] = useState(null)
  const [selectedDiet, setSelectedDiet] = useState(null)
  const [dietHistory, setDietHistory] = useState([])
  const [selectedAdherenceDate, setSelectedAdherenceDate] = useState(getTodayDateInputValue)
  const [dietAdherence, setDietAdherence] = useState(null)
  const [weeklyAdherenceSummary, setWeeklyAdherenceSummary] = useState(null)
  const [generatorForm, setGeneratorForm] = useState(buildInitialGeneratorForm)
  const [latestDietError, setLatestDietError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [generateError, setGenerateError] = useState('')
  const [generateMessage, setGenerateMessage] = useState('')
  const [selectedDietError, setSelectedDietError] = useState('')
  const [dietActionError, setDietActionError] = useState('')
  const [dietActionMessage, setDietActionMessage] = useState('')
  const [adherenceError, setAdherenceError] = useState('')
  const [weeklyAdherenceError, setWeeklyAdherenceError] = useState('')
  const [replacementError, setReplacementError] = useState('')
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
  const [replacementLab, setReplacementLab] = useState(null)
  const [isReplacementLoading, setIsReplacementLoading] = useState(false)
  const [selectedReplacementCode, setSelectedReplacementCode] = useState('')
  const [replacementSearchQuery, setReplacementSearchQuery] = useState('')
  const [replacementSearchResults, setReplacementSearchResults] = useState([])
  const [replacementSearchError, setReplacementSearchError] = useState('')
  const [isReplacementSearchLoading, setIsReplacementSearchLoading] = useState(false)
  const [isReplacementPreviewLoading, setIsReplacementPreviewLoading] = useState(false)
  const [activeReplacementPreviewCode, setActiveReplacementPreviewCode] = useState('')
  const [generationStageIndex, setGenerationStageIndex] = useState(0)

  const currentDiet = selectedDiet ?? latestDiet
  const currentDietId = currentDiet?.id ?? ''
  const adherenceRecordsByMeal = Object.fromEntries(
    (dietAdherence?.meals ?? []).map((mealEntry) => [mealEntry.meal_number, mealEntry]),
  )
  const replacementOptions = getReplacementOptionsForDisplay(replacementLab)
  const activeGenerationStage = GENERATION_LOADING_STAGES[
    Math.min(generationStageIndex, GENERATION_LOADING_STAGES.length - 1)
  ]

  function resetReplacementSearchState() {
    setReplacementSearchQuery('')
    setReplacementSearchResults([])
    setReplacementSearchError('')
    setIsReplacementSearchLoading(false)
    setIsReplacementPreviewLoading(false)
    setActiveReplacementPreviewCode('')
  }

  function closeReplacementLab() {
    setReplacementLab(null)
    setSelectedReplacementCode('')
    setReplacementError('')
    resetReplacementSearchState()
  }

  async function loadLatestDiet(activeToken = token) {
    if (!activeToken) return null

    setIsLatestDietLoading(true)
    setLatestDietError('')

    try {
      const diet = await dietsApi.getLatestDiet(activeToken)
      setLatestDiet(diet)
      setSelectedDiet((currentSelectedDiet) => currentSelectedDiet ?? diet)
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
    if (!activeToken) return []

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
    await Promise.all([loadLatestDiet(activeToken), loadDietHistory(activeToken)])
  }

  async function loadDietAdherence(dietId = currentDietId, dateValue = selectedAdherenceDate, activeToken = token) {
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

  async function loadWeeklyAdherence(dateValue = selectedAdherenceDate, activeToken = token) {
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
    if (!token) return
    reloadAll(token)
  }, [token])

  useEffect(() => {
    if (!token) return

    if (currentDietId) {
      loadDietAdherence(currentDietId, selectedAdherenceDate, token)
    } else {
      setDietAdherence(null)
    }

    loadWeeklyAdherence(selectedAdherenceDate, token)
  }, [token, currentDietId, selectedAdherenceDate])

  useEffect(() => {
    if (!isGenerating) {
      setGenerationStageIndex(0)
      return undefined
    }

    setGenerationStageIndex(0)
    const timers = GENERATION_LOADING_STAGES.slice(1).map((_, stageOffset) => (
      window.setTimeout(() => {
        setGenerationStageIndex(stageOffset + 1)
      }, (stageOffset + 1) * 900)
    ))

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer))
    }
  }, [isGenerating])

  function syncUpdatedDiet(updatedDiet) {
    setSelectedDiet(updatedDiet)

    setLatestDiet((currentLatest) => {
      if (!currentLatest || currentLatest.id === updatedDiet.id) {
        return updatedDiet
      }
      return currentLatest
    })

    setDietHistory((currentHistory) =>
      currentHistory.map((d) => (d.id === updatedDiet.id ? updatedDiet : d))
    )
  }

  function handleGeneratorBaseChange(event) {
    const { name, value, checked, type } = event.target

    if (name === 'mealsCount') {
      const nextTemplate = getDefaultDistributionTemplate(Number(value)).map((entry) => String(entry))
      setGeneratorForm((current) => ({
        ...current,
        mealsCount: value,
        customPercentages: current.useCustomDistribution ? nextTemplate : current.customPercentages,
      }))
      return
    }

    setGeneratorForm((current) => ({
      ...current,
      [name]: type === 'checkbox' ? checked : value,
    }))
  }

  function handleDistributionChange(index, value) {
    setGeneratorForm((current) => ({
      ...current,
      customPercentages: current.customPercentages.map((entry, entryIndex) => (
        entryIndex === index ? value : entry
      )),
    }))
  }

  async function handleGenerate(event) {
    event.preventDefault()
    if (!token || isGenerating) return

    setGenerateError('')
    setGenerateMessage('')
    setSelectedDietError('')
    setDietActionError('')
    setDietActionMessage('')
    setAdherenceError('')
    setReplacementError('')

    const mealsCount = Number(generatorForm.mealsCount)
    const payload = {
      meals_count: mealsCount,
      training_time_of_day: generatorForm.trainingTimeOfDay || undefined,
    }

    if (generatorForm.useCustomDistribution) {
      const validation = validateDistribution(
        generatorForm.customPercentages.map((value) => Number(value)),
        mealsCount,
      )

      if (!validation.isValid) {
        setGenerateError(validation.message)
        return
      }

      payload.custom_percentages = generatorForm.customPercentages.map((value) => Number(value))
    }

    setIsGenerating(true)

    try {
      const createdDiet = await dietsApi.generateDiet(token, payload)
      setLatestDiet(createdDiet)
      setSelectedDiet(createdDiet)
      await loadDietHistory(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      setGenerateMessage('Dieta generada y guardada correctamente.')
    } catch (error) {
      setGenerateError(error.message)
    } finally {
      setIsGenerating(false)
    }
  }

  async function handleSelectDiet(dietId) {
    if (!token) return

    setViewingDietId(dietId)
    setSelectedDietError('')
    setDietActionMessage('')
    setDietActionError('')
    closeReplacementLab()
    setReplacementError('')

    try {
      const diet = await dietsApi.getDietById(token, dietId)
      setSelectedDiet(diet)
    } catch (error) {
      setSelectedDietError(error.message)
    } finally {
      setViewingDietId('')
    }
  }

  async function handleRegenerateMeal(mealNumber) {
    if (!token || !currentDietId) return

    setIsMealActionLoading(true)
    setActiveMealNumber(mealNumber)
    setDietActionError('')
    setDietActionMessage('')

    try {
      const response = await dietsApi.regenerateMeal(token, currentDietId, mealNumber)
      syncUpdatedDiet(response.diet)
      setDietActionMessage(response.summary.message)
      await loadDietHistory(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
    } catch (error) {
      setDietActionError(error.message)
    } finally {
      setIsMealActionLoading(false)
      setActiveMealNumber(null)
    }
  }

  async function openReplacementLab(mealNumber, food) {
    if (!token || !currentDietId) return

    setReplacementError('')
    resetReplacementSearchState()
    setReplacementLab({
      mealNumber,
      food,
      options: [],
      manualOptions: [],
      currentMacroDominante: resolveCurrentMacroDominante(food),
    })
    setSelectedReplacementCode('')
    setIsReplacementLoading(true)

    try {
      const response = await dietsApi.getFoodReplacementOptions(token, currentDietId, mealNumber, {
        current_food_name: food.name,
        current_food_code: food.food_code,
      })
      setReplacementLab({
        mealNumber,
        food,
        options: response.options ?? [],
        manualOptions: [],
        currentMacroDominante: resolveCurrentMacroDominante(food, response.current_macro_dominante),
      })
      setSelectedReplacementCode(response.options[0]?.food_code ?? '')
    } catch (error) {
      setReplacementError(error.message)
    } finally {
      setIsReplacementLoading(false)
    }
  }

  async function handleSearchReplacementFood(event) {
    event.preventDefault()
    if (!token || !currentDietId || !replacementLab?.food) return

    const query = replacementSearchQuery.trim()
    if (!query) {
      setReplacementSearchResults([])
      setReplacementSearchError('Escribe un alimento para buscar un sustituto.')
      return
    }

    setIsReplacementSearchLoading(true)
    setReplacementSearchError('')
    setReplacementError('')

    try {
      const response = await dietsApi.searchReplacementFood(token, currentDietId, replacementLab.mealNumber, {
        current_food_name: replacementLab.food.name,
        current_food_code: replacementLab.food.food_code,
        query,
      })
      setReplacementSearchResults(response.candidates ?? [])
      if (!(response.candidates ?? []).length) {
        setReplacementSearchError('No hemos encontrado candidatos para esa búsqueda.')
      }
    } catch (error) {
      setReplacementSearchResults([])
      setReplacementSearchError(error.message)
    } finally {
      setIsReplacementSearchLoading(false)
    }
  }

  async function handlePreviewManualReplacement(candidate) {
    if (!token || !currentDietId || !replacementLab?.food || !candidate?.valid) return

    setIsReplacementPreviewLoading(true)
    setActiveReplacementPreviewCode(candidate.food_code)
    setReplacementSearchError('')
    setReplacementError('')

    try {
      const response = await dietsApi.getFoodReplacementOptions(token, currentDietId, replacementLab.mealNumber, {
        current_food_name: replacementLab.food.name,
        current_food_code: replacementLab.food.food_code,
        replacement_food_name: candidate.name,
        replacement_food_code: candidate.food_code,
      })
      const previewOption = response.options?.[0]
      if (!previewOption) {
        throw new Error('No se pudo calcular una previsualización válida para ese alimento.')
      }

      setReplacementLab((current) => {
        if (!current) return current
        return {
          ...current,
          currentMacroDominante: resolveCurrentMacroDominante(current.food, response.current_macro_dominante ?? current.currentMacroDominante),
          manualOptions: mergeReplacementOptions([previewOption], current.manualOptions ?? []),
        }
      })
      setSelectedReplacementCode(previewOption.food_code)
    } catch (error) {
      setReplacementSearchError(error.message)
    } finally {
      setIsReplacementPreviewLoading(false)
      setActiveReplacementPreviewCode('')
    }
  }

  async function handleApplyReplacement() {
    if (!token || !currentDietId || !replacementLab?.food || !selectedReplacementCode) return

    const selectedOption = replacementOptions.find((option) => option.food_code === selectedReplacementCode)
    if (!selectedOption) return

    setIsMealActionLoading(true)
    setActiveMealNumber(replacementLab.mealNumber)
    setActiveFoodCode(replacementLab.food.food_code ?? replacementLab.food.name)
    setDietActionError('')
    setDietActionMessage('')
    setReplacementError('')

    try {
      const response = await dietsApi.replaceFoodInMeal(token, currentDietId, replacementLab.mealNumber, {
        current_food_name: replacementLab.food.name,
        current_food_code: replacementLab.food.food_code,
        replacement_food_name: selectedOption.name,
        replacement_food_code: selectedOption.food_code,
      })
      syncUpdatedDiet(response.diet)
      setDietActionMessage(response.summary.message)
      closeReplacementLab()
      await loadDietHistory(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
    } catch (error) {
      setDietActionError(error.message)
      setReplacementError(error.message)
    } finally {
      setIsMealActionLoading(false)
      setActiveMealNumber(null)
      setActiveFoodCode('')
    }
  }

  async function handleSaveMealAdherence(mealNumber, status) {
    if (!token || !currentDietId) return

    setIsSavingMealAdherence(true)
    setActiveAdherenceMealNumber(mealNumber)
    setAdherenceError('')

    try {
      await adherenceApi.saveMealAdherence(token, {
        diet_id: currentDietId,
        meal_number: mealNumber,
        date: selectedAdherenceDate,
        status,
      })
      await Promise.all([
        loadDietAdherence(currentDietId, selectedAdherenceDate, token),
        loadWeeklyAdherence(selectedAdherenceDate, token),
      ])
      window.dispatchEvent(new CustomEvent('adherence:updated'))
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
    } catch (error) {
      setAdherenceError(error.message)
    } finally {
      setIsSavingMealAdherence(false)
      setActiveAdherenceMealNumber(null)
    }
  }

  const macroPanels = [
    { label: 'Proteína', value: currentDiet?.actual_protein_grams, target: currentDiet?.protein_grams },
    { label: 'Carbohidratos', value: currentDiet?.actual_carb_grams, target: currentDiet?.carb_grams },
    { label: 'Grasas', value: currentDiet?.actual_fat_grams, target: currentDiet?.fat_grams },
  ]

  return (
    <div className="diets-page">
      {(isLatestDietLoading || isHistoryLoading) ? <p className="page-status">Cargando dieta...</p> : null}
      {(latestDietError || selectedDietError || historyError || dietActionError || adherenceError || weeklyAdherenceError) ? (
        <p className="page-status page-status-error">
          {latestDietError || selectedDietError || historyError || dietActionError || adherenceError || weeklyAdherenceError}
        </p>
      ) : null}

      <div className="diets-hero-layout">
        <SectionPanel eyebrow="Resumen diario" className="diet-performance-panel">
          <div className="diet-performance-kcal">
            <strong>{formatCompactNumber(currentDiet?.actual_calories, { maximumFractionDigits: 0 })}</strong>
            <span>KCAL</span>
          </div>

          <div className="diet-performance-target">
            <small>Objetivo: {formatCalories(currentDiet?.target_calories)}</small>
            <div className="diet-performance-track">
              <div
                className="diet-performance-fill"
                style={{
                  width: `${Math.min(
                    100,
                    Math.max(0, ((Number(currentDiet?.actual_calories) || 0) / (Number(currentDiet?.target_calories) || 1)) * 100),
                  )}%`,
                }}
              />
            </div>
          </div>

          <div className="diet-performance-macros">
            {macroPanels.map((macro) => {
              const currentValue = Number(macro.value ?? 0)
              const targetValue = Number((macro.target ?? currentValue) || 0)
              const progress = targetValue > 0 ? (currentValue / targetValue) * 100 : 0
              const isOverTarget = targetValue > 0 && currentValue > targetValue

              return (
                <article key={macro.label} className="diet-macro-gauge">
                  <div className="diet-macro-gauge-head">
                    <span>{macro.label}</span>
                    <strong>{formatMacro(currentValue)} / {formatMacro(targetValue)}</strong>
                  </div>
                  <div className="diet-macro-gauge-track">
                    <div
                      className={`diet-macro-gauge-fill ${isOverTarget ? 'diet-macro-gauge-fill-danger' : ''}`.trim()}
                      style={{ width: `${Math.min(100, progress)}%` }}
                    />
                  </div>
                </article>
              )
            })}
          </div>
        </SectionPanel>

        <SectionPanel
          eyebrow="Generador de dieta"
          title="Genera una dieta diaria"
          description="Configura el número de comidas y, si quieres, ajusta la distribución."
        >
          <form className="protocol-generator-form" onSubmit={handleGenerate}>
            <label>
              <span>Número de comidas</span>
              <select
                disabled={isGenerating}
                name="mealsCount"
                value={generatorForm.mealsCount}
                onChange={handleGeneratorBaseChange}
              >
                {[3, 4, 5, 6].map((value) => (
                  <option key={value} value={value}>
                    {value} comidas
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Momento del entrenamiento</span>
              <select
                disabled={isGenerating}
                name="trainingTimeOfDay"
                value={generatorForm.trainingTimeOfDay}
                onChange={handleGeneratorBaseChange}
              >
                <option value="">No especificado</option>
                {TRAINING_TIME_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="protocol-generator-toggle">
              <input
                checked={generatorForm.useCustomDistribution}
                disabled={isGenerating}
                name="useCustomDistribution"
                type="checkbox"
                onChange={handleGeneratorBaseChange}
              />
              <span>Usar distribución calórica personalizada</span>
            </label>

            {generatorForm.useCustomDistribution ? (
              <div className="protocol-generator-percentages">
                {generatorForm.customPercentages.map((value, index) => (
                  <label key={`distribution-${index}`}>
                    <span>{`Comida ${index + 1}`}</span>
                    <input
                      disabled={isGenerating}
                      type="number"
                      min="1"
                      max="100"
                      value={value}
                      onChange={(event) => handleDistributionChange(index, event.target.value)}
                    />
                  </label>
                ))}
              </div>
            ) : null}

            {generateError ? <p className="page-status page-status-error">{generateError}</p> : null}
            {generateMessage ? <p className="page-status page-status-success">{generateMessage}</p> : null}

            {isGenerating ? (
              <div className="protocol-generator-loading" aria-live="polite">
                <div className="protocol-generator-loading-head">
                  <strong>{activeGenerationStage.label}</strong>
                  <span>{activeGenerationStage.progress}%</span>
                </div>
                <div
                  aria-valuemax="100"
                  aria-valuemin="0"
                  aria-valuenow={activeGenerationStage.progress}
                  className="protocol-generator-loading-bar"
                  role="progressbar"
                >
                  <div
                    className="protocol-generator-loading-fill"
                    style={{ width: `${activeGenerationStage.progress}%` }}
                  />
                </div>
              </div>
            ) : null}

            <button type="submit" className="panel-cta-button" disabled={isGenerating}>
              {isGenerating ? 'Generando dieta...' : 'Generar dieta'}
            </button>
          </form>
        </SectionPanel>
      </div>

      {currentDiet ? (
        <>
          <SectionPanel
            eyebrow="Seguimiento"
            className="diet-tracking-strip"
            actions={(
              <label className="inline-date-field">
                <span>Fecha</span>
                <input type="date" value={selectedAdherenceDate} onChange={(event) => setSelectedAdherenceDate(event.target.value)} />
              </label>
            )}
          >
            <div className="diet-tracking-metrics">
              <div>
                <small>Adherencia diaria</small>
                <strong>{formatPercent(dietAdherence?.daily_summary?.adherence_percentage ?? 0, 0)}</strong>
              </div>
              <div>
                <small>Adherencia semanal</small>
                <strong>{formatPercent(weeklyAdherenceSummary?.adherence_percentage ?? 0, 0)}</strong>
              </div>
              <div>
                <small>Cobertura</small>
                <strong>{formatPercent(weeklyAdherenceSummary?.tracking_coverage_percentage ?? 0, 0)}</strong>
              </div>
            </div>
          </SectionPanel>

          <div className="meal-protocol-grid">
            {currentDiet.meals.map((meal) => {
              const visual = getMealVisual(meal.meal_number, meal.meal_role, meal.meal_label)
              const adherenceRecord = adherenceRecordsByMeal[meal.meal_number]
              const mealStatus = adherenceRecord?.status ?? 'pending'
              const isBusyMeal = activeMealNumber === meal.meal_number || activeAdherenceMealNumber === meal.meal_number

              return (
                <article key={meal.meal_number} className="protocol-meal-card">
                  <div className={`protocol-meal-hero ${visual.heroClassName}`.trim()}>
                    <div className="protocol-meal-overlay" />
                    <div className="protocol-meal-copy">
                      <span>{visual.phase}</span>
                      <h3>{visual.label}</h3>
                    </div>
                    <div className="protocol-meal-kcal">{formatCalories(meal.actual_calories)}</div>
                  </div>

                  <div className="protocol-meal-body">
                    <div className="protocol-meal-summary">
                      <span>Estado</span>
                      <strong className={`status-badge status-badge-${mealStatus}`}>{formatMealStatus(mealStatus)}</strong>
                    </div>

                    <div className="protocol-food-list">
                      {meal.foods.map((food) => (
                        <div
                          key={`${meal.meal_number}-${food.food_code ?? food.name}`}
                          className={`protocol-food-row ${activeFoodCode === (food.food_code ?? food.name) ? 'protocol-food-row-active' : ''}`.trim()}
                        >
                          <div className="protocol-food-copy">
                            <strong>{food.name}</strong>
                            <small>{food.category}</small>
                          </div>
                          <div className="protocol-food-inline-metrics">
                            <div className="protocol-food-breakdown">
                              <span>{formatFoodPortion(food)}</span>
                              <span>{formatCalories(food.calories)}</span>
                            </div>
                            <div className="protocol-food-macros">
                              <span>P {formatMacro(food.protein_grams)}</span>
                              <span>C {formatMacro(food.carb_grams)}</span>
                              <span>G {formatMacro(food.fat_grams)}</span>
                            </div>
                          </div>
                          <div className="protocol-food-meta">
                            <button type="button" onClick={() => openReplacementLab(meal.meal_number, food)}>
                              Cambiar
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="protocol-meal-macros">
                      <div className="protocol-meal-macros-kcal">
                        <span>{formatCalories(meal.actual_calories)}</span>
                        <span className="protocol-meal-macros-sep">/</span>
                        <span className="protocol-meal-macros-target">{formatCalories(meal.target_calories)}</span>
                      </div>
                      <div className="protocol-meal-macros-grid">
                        <div className="protocol-meal-macro-item">
                          <strong>{formatMacro(meal.actual_protein_grams)}</strong>
                          <small>Proteína</small>
                        </div>
                        <div className="protocol-meal-macro-item">
                          <strong>{formatMacro(meal.actual_carb_grams)}</strong>
                          <small>Carbohidratos</small>
                        </div>
                        <div className="protocol-meal-macro-item">
                          <strong>{formatMacro(meal.actual_fat_grams)}</strong>
                          <small>Grasas</small>
                        </div>
                      </div>
                    </div>

                    <div className="protocol-meal-actions">
                      <button
                        type="button"
                        className="protocol-secondary-button"
                        onClick={() => handleRegenerateMeal(meal.meal_number)}
                        disabled={isMealActionLoading && activeMealNumber === meal.meal_number}
                      >
                        {isMealActionLoading && activeMealNumber === meal.meal_number ? 'Regenerando...' : 'Regenerar'}
                      </button>

                      <button
                        type="button"
                        className="protocol-primary-button"
                        onClick={() => handleSaveMealAdherence(meal.meal_number, 'completed')}
                        disabled={isBusyMeal || isSavingMealAdherence}
                      >
                        {isSavingMealAdherence && activeAdherenceMealNumber === meal.meal_number ? 'Guardando...' : 'Confirmar ingesta'}
                      </button>
                    </div>

                    <div className="protocol-meal-status-actions">
                      {['modified', 'omitted', 'pending'].map((status) => (
                        <button
                          key={`${meal.meal_number}-${status}`}
                          type="button"
                          className={`protocol-chip-button ${mealStatus === status ? 'protocol-chip-button-active' : ''}`.trim()}
                          onClick={() => handleSaveMealAdherence(meal.meal_number, status)}
                          disabled={isBusyMeal}
                        >
                          {status === 'pending' ? 'Restablecer' : formatMealStatus(status)}
                        </button>
                      ))}
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        </>
      ) : (
        <SectionPanel title="Sin dieta activa">
          <p className="panel-placeholder">Genera tu primera dieta para empezar.</p>
        </SectionPanel>
      )}

      {replacementLab ? (
        <SectionPanel
          eyebrow={`Sustitución · Comida ${String(replacementLab.mealNumber).padStart(2, '0')}`}
          title={replacementLab.food.name}
          description="Sustituye este alimento por otro compatible dentro de la comida."
          actions={<button type="button" className="protocol-secondary-button" onClick={closeReplacementLab}>Cerrar</button>}
        >
          {isReplacementLoading ? <p className="page-status">Calculando opciones compatibles...</p> : null}
          {replacementError ? <p className="page-status page-status-error">{replacementError}</p> : null}

          {!isReplacementLoading ? (() => {
            const selectedOption = replacementOptions.find((o) => o.food_code === selectedReplacementCode) ?? null
            return (
              <div className="replacement-lab-layout">
                <div className="replacement-lab-summary">
                  <span>Macro dominante actual: <strong>{formatMacroDominante(replacementLab.currentMacroDominante)}</strong></span>
                  <span>Porción actual: <strong>{formatFoodPortion(replacementLab.food)}</strong></span>
                </div>

                <label className="replacement-select-label">
                  <span>Opciones disponibles</span>
                  <select value={selectedReplacementCode} onChange={(event) => setSelectedReplacementCode(event.target.value)}>
                    {replacementOptions.map((option) => (
                      <option key={option.food_code} value={option.food_code}>
                        {option.name} — {option.recommended_quantity} {option.recommended_unit} · {formatCalories(option.calories)}
                      </option>
                    ))}
                  </select>
                </label>

                <form className="replacement-search-panel" onSubmit={handleSearchReplacementFood}>
                  <div className="replacement-search-head">
                    <strong>Buscar alimento</strong>
                    <small>Solo se mostrarán alimentos compatibles con el papel nutricional de esta comida.</small>
                  </div>

                  <div className="replacement-search-row">
                    <input
                      type="text"
                      value={replacementSearchQuery}
                      onChange={(event) => setReplacementSearchQuery(event.target.value)}
                      placeholder="Ej. mango, granola, arroz inflado..."
                    />
                    <button type="submit" className="protocol-secondary-button" disabled={isReplacementSearchLoading}>
                      {isReplacementSearchLoading ? 'Buscando...' : 'Buscar'}
                    </button>
                  </div>

                  {replacementSearchError ? <p className="page-status page-status-error">{replacementSearchError}</p> : null}

                  {replacementSearchResults.length > 0 ? (
                    <div className="replacement-search-results">
                      {replacementSearchResults.map((candidate) => (
                        <article
                          key={candidate.food_code}
                          className={`replacement-search-card ${candidate.valid ? 'replacement-search-card-valid' : 'replacement-search-card-invalid'}`.trim()}
                        >
                          <div className="replacement-search-card-head">
                            <div>
                              <strong>{candidate.name}</strong>
                              <small>
                                {candidate.category} · {formatMacroDominante(candidate.macro_dominante)}
                              </small>
                            </div>
                            <div className="replacement-search-card-meta">
                              <span>Eq. {formatCompactNumber(candidate.equivalent_grams, { maximumFractionDigits: 0 })} g</span>
                              <span className={`replacement-search-status ${candidate.valid ? 'replacement-search-status-valid' : 'replacement-search-status-invalid'}`.trim()}>
                                {candidate.valid ? 'Compatible' : 'No compatible'}
                              </span>
                            </div>
                          </div>

                          <div className="replacement-search-card-macros">
                            <span>{formatCalories(candidate.calories)}</span>
                            <span>P {formatMacro(candidate.protein_grams)}</span>
                            <span>G {formatMacro(candidate.fat_grams)}</span>
                            <span>C {formatMacro(candidate.carb_grams)}</span>
                          </div>

                          <p className={`replacement-search-note ${candidate.valid ? '' : 'replacement-search-note-invalid'}`.trim()}>
                            {formatReplacementValidationNote(candidate)}
                          </p>

                          {candidate.valid ? (
                            <button
                              type="button"
                              className="protocol-secondary-button replacement-search-action"
                              disabled={isReplacementPreviewLoading && activeReplacementPreviewCode === candidate.food_code}
                              onClick={() => handlePreviewManualReplacement(candidate)}
                            >
                              {isReplacementPreviewLoading && activeReplacementPreviewCode === candidate.food_code
                                ? 'Calculando...'
                                : 'Previsualizar sustitución'}
                            </button>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  ) : null}
                </form>

                {selectedOption ? (
                  <article className="replacement-detail-card">
                    <div className="replacement-detail-header">
                      <div>
                        <strong>{selectedOption.name}</strong>
                        <small>{selectedOption.category} · {selectedOption.functional_group}</small>
                      </div>
                      <span className={`replacement-strategy replacement-strategy-${selectedOption.strategy}`}>
                        {selectedOption.strategy === 'strict' ? 'Ajuste directo' : 'Ajuste flexible'}
                      </span>
                    </div>

                    <div className="replacement-detail-macros">
                      <span>{formatCalories(selectedOption.calories)}</span>
                      <span>P {formatMacro(selectedOption.protein_grams)}</span>
                      <span>G {formatMacro(selectedOption.fat_grams)}</span>
                      <span>C {formatMacro(selectedOption.carb_grams)}</span>
                    </div>

                    {selectedOption.equivalent_grams ? (
                      <p className="replacement-detail-equivalence">
                        Equivalencia orientativa: {formatCompactNumber(selectedOption.equivalent_grams, { maximumFractionDigits: 0 })} g del nuevo alimento.
                      </p>
                    ) : null}

                    <div className="replacement-detail-deltas">
                      <span>Vs actual: {formatSignedCalories(selectedOption.calorie_delta_vs_current)}</span>
                      <span>P {formatSignedMass(selectedOption.protein_delta_vs_current)}</span>
                      <span>G {formatSignedMass(selectedOption.fat_delta_vs_current)}</span>
                      <span>C {formatSignedMass(selectedOption.carb_delta_vs_current)}</span>
                    </div>

                    <p className="replacement-detail-impact">
                      Impacto comida: {formatSignedCalories(selectedOption.meal_calorie_difference)} | P {formatSignedMass(selectedOption.meal_protein_difference)} | G {formatSignedMass(selectedOption.meal_fat_difference)} | C {formatSignedMass(selectedOption.meal_carb_difference)}
                    </p>

                    {selectedOption.note ? <p className="replacement-detail-note">{selectedOption.note}</p> : null}
                  </article>
                ) : null}

                <button type="button" className="panel-cta-button" disabled={isMealActionLoading || !selectedReplacementCode} onClick={handleApplyReplacement}>
                  {isMealActionLoading ? 'Aplicando reemplazo...' : 'Aplicar reemplazo'}
                </button>
              </div>
            )
          })() : null}
        </SectionPanel>
      ) : null}

      <div className="diets-support-layout">
        <SectionPanel eyebrow="Resumen de adherencia diaria">
          {isDietAdherenceLoading ? <p className="page-status">Cargando adherencia de comidas...</p> : null}
          {!isDietAdherenceLoading ? (
            <div className="key-value-stack">
              <div className="key-value-row"><span>Comidas completadas</span><strong>{dietAdherence?.daily_summary?.completed_meals ?? 0}</strong></div>
              <div className="key-value-row"><span>Comidas modificadas</span><strong>{dietAdherence?.daily_summary?.modified_meals ?? 0}</strong></div>
              <div className="key-value-row"><span>Comidas omitidas</span><strong>{dietAdherence?.daily_summary?.omitted_meals ?? 0}</strong></div>
              <div className="key-value-row"><span>Comidas pendientes</span><strong>{dietAdherence?.daily_summary?.pending_meals ?? 0}</strong></div>
            </div>
          ) : null}
        </SectionPanel>

        <SectionPanel eyebrow="Interpretación semanal">
          {isWeeklyAdherenceLoading ? <p className="page-status">Cargando adherencia semanal...</p> : null}
          {!isWeeklyAdherenceLoading ? (
            <>
              <div className="key-value-stack">
                <div className="key-value-row"><span>Adherencia</span><strong>{formatPercent(weeklyAdherenceSummary?.adherence_percentage ?? 0, 0)}</strong></div>
                <div className="key-value-row"><span>Cobertura</span><strong>{formatPercent(weeklyAdherenceSummary?.tracking_coverage_percentage ?? 0, 0)}</strong></div>
                <div className="key-value-row"><span>Ventana semanal</span><strong>{weeklyAdherenceSummary?.week_label ?? 'N/A'}</strong></div>
              </div>
              <p className="panel-placeholder">{weeklyAdherenceSummary?.interpretation_message || 'La interpretación de adherencia semanal aparecerá aquí tras comenzar el registro.'}</p>
            </>
          ) : null}
        </SectionPanel>
      </div>

      <SectionPanel eyebrow="Historial" title="Dietas recientes">
        {dietHistory.length > 0 ? (
          <div className="protocol-history-list">
            {dietHistory.map((diet) => (
              <button
                key={diet.id}
                type="button"
                className={`protocol-history-row ${currentDietId === diet.id ? 'protocol-history-row-active' : ''}`.trim()}
                onClick={() => handleSelectDiet(diet.id)}
                disabled={viewingDietId === diet.id}
              >
                <div>
                  <strong>{formatDateLabel(diet.created_at, { month: 'short', day: '2-digit', year: 'numeric' })}</strong>
                  <small>{diet.meals_count} comidas</small>
                </div>
                <span>{formatCalories(diet.target_calories)}</span>
                <span>{diet.food_preferences_applied ? 'Preferencias aplicadas' : 'Perfil estándar'}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="panel-placeholder">{isHistoryLoading ? 'Cargando historial...' : 'El historial de dietas aparecerá aquí tras la primera generación.'}</p>
        )}
      </SectionPanel>

      {dietActionMessage ? <p className="page-status page-status-success">{dietActionMessage}</p> : null}
    </div>
  )
}

export default DietsPage