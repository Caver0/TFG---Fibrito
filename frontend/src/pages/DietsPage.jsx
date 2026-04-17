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
  formatDataSource,
  formatDateLabel,
  formatMacro,
  formatPercent,
  getMealVisual,
} from '../utils/stitch'

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

  const currentDiet = selectedDiet ?? latestDiet
  const currentDietId = currentDiet?.id ?? ''
  const adherenceRecordsByMeal = Object.fromEntries(
    (dietAdherence?.meals ?? []).map((mealEntry) => [mealEntry.meal_number, mealEntry]),
  )

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

  // Localiza la función syncUpdatedDiet (alrededor de la línea 158) y reemplázala:
  function syncUpdatedDiet(updatedDiet) {
    // 1. Actualizamos la dieta que se está viendo actualmente
    setSelectedDiet(updatedDiet);
    
    // 2. Actualizamos la referencia de 'latestDiet' si es la misma dieta
    setLatestDiet((currentLatest) => {
      if (!currentLatest || currentLatest.id === updatedDiet.id) {
        return updatedDiet;
      }
      return currentLatest;
    });

    // 3. CRITICO: Actualizamos el historial para que la lista de la derecha refleje los cambios
    setDietHistory((currentHistory) =>
      currentHistory.map((d) => (d.id === updatedDiet.id ? updatedDiet : d))
    );
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
    if (!token) return

    setIsGenerating(true)
    setGenerateError('')
    setGenerateMessage('')
    setSelectedDietError('')
    setDietActionError('')
    setDietActionMessage('')
    setAdherenceError('')
    setReplacementError('')

    try {
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

      const createdDiet = await dietsApi.generateDiet(token, payload)
      setLatestDiet(createdDiet)
      setSelectedDiet(createdDiet)
      await loadDietHistory(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      setGenerateMessage('Protocolo basado en alimentos generado y guardado correctamente.')
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
    setReplacementLab(null)
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
    setReplacementLab({ mealNumber, food, options: [] })
    setSelectedReplacementCode('')
    setIsReplacementLoading(true)

    try {
      const response = await dietsApi.getFoodReplacementOptions(token, currentDietId, mealNumber, {
        current_food_name: food.name,
        current_food_code: food.food_code,
      })
      setReplacementLab({ mealNumber, food, options: response.options })
      setSelectedReplacementCode(response.options[0]?.food_code ?? '')
    } catch (error) {
      setReplacementError(error.message)
    } finally {
      setIsReplacementLoading(false)
    }
  }

  async function handleApplyReplacement() {
    if (!token || !currentDietId || !replacementLab?.food || !selectedReplacementCode) return

    const selectedOption = replacementLab.options.find((option) => option.food_code === selectedReplacementCode)
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
      setReplacementLab(null)
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
    { label: 'Protein', value: currentDiet?.actual_protein_grams, target: currentDiet?.protein_grams },
    { label: 'Carbs', value: currentDiet?.actual_carb_grams, target: currentDiet?.carb_grams },
    { label: 'Fats', value: currentDiet?.actual_fat_grams, target: currentDiet?.fat_grams },
  ]

  return (
    <div className="diets-page">
      {(isLatestDietLoading || isHistoryLoading) ? <p className="page-status">Loading diet protocol...</p> : null}
      {(latestDietError || selectedDietError || historyError || dietActionError || adherenceError || weeklyAdherenceError) ? (
        <p className="page-status page-status-error">
          {latestDietError || selectedDietError || historyError || dietActionError || adherenceError || weeklyAdherenceError}
        </p>
      ) : null}

      <div className="diets-hero-layout">
        <SectionPanel eyebrow="Índice de Rendimiento Diario" className="diet-performance-panel">
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

          <div className="diet-performance-meta">
            <span>Pila de fuentes: {(currentDiet?.food_data_sources ?? []).map(formatDataSource).join(' / ') || 'Interno'}</span>
            <span>Alimentos resueltos: {currentDiet?.resolved_foods_count ?? 0}</span>
          </div>
        </SectionPanel>

        <SectionPanel
          eyebrow="Generador de Protocolo"
          title="Genera una dieta diaria calibrada"
          description="Este panel se comunica directamente con el endpoint de dietas basado en alimentos."
        >
          <form className="protocol-generator-form" onSubmit={handleGenerate}>
            <label>
              <span>Número de comidas</span>
              <select name="mealsCount" value={generatorForm.mealsCount} onChange={handleGeneratorBaseChange}>
                {[3, 4, 5, 6].map((value) => (
                  <option key={value} value={value}>
                    {value} meals
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Hora de entrenamiento</span>
              <select name="trainingTimeOfDay" value={generatorForm.trainingTimeOfDay} onChange={handleGeneratorBaseChange}>
                <option value="">No especificado</option>
                {TRAINING_TIME_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="protocol-generator-toggle">
              <input checked={generatorForm.useCustomDistribution} name="useCustomDistribution" type="checkbox" onChange={handleGeneratorBaseChange} />
              <span>Usar distribución calórica personalizada</span>
            </label>

            {generatorForm.useCustomDistribution ? (
              <div className="protocol-generator-percentages">
                {generatorForm.customPercentages.map((value, index) => (
                  <label key={`distribution-${index}`}>
                    <span>{`Meal ${index + 1}`}</span>
                    <input type="number" min="1" max="100" value={value} onChange={(event) => handleDistributionChange(index, event.target.value)} />
                  </label>
                ))}
              </div>
            ) : null}

            {generateError ? <p className="page-status page-status-error">{generateError}</p> : null}
            {generateMessage ? <p className="page-status page-status-success">{generateMessage}</p> : null}

            <button type="submit" className="panel-cta-button" disabled={isGenerating}>
              {isGenerating ? 'Generando protocolo...' : 'Generar Dieta'}
            </button>
          </form>
        </SectionPanel>
      </div>

      {currentDiet ? (
        <>
          <SectionPanel
            eyebrow="Ventana de Seguimiento"
            className="diet-tracking-strip"
            actions={(
              <label className="inline-date-field">
                <span>Fecha de seguimiento</span>
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
                            <small>{formatDataSource(food.source)} // {food.category}</small>
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
                          <small>Carbos</small>
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
                        {isSavingMealAdherence && activeAdherenceMealNumber === meal.meal_number ? 'Guardando...' : 'Confirmar Ingesta'}
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
        <SectionPanel title="Sin protocolo de dieta activo">
          <p className="panel-placeholder">Genera tu primera dieta basada en alimentos para desbloquear la cuadrícula de comidas.</p>
        </SectionPanel>
      )}

      {replacementLab ? (
        <SectionPanel
          eyebrow={`Laboratorio de Cambio // Comida ${String(replacementLab.mealNumber).padStart(2, '0')}`}
          title={replacementLab.food.name}
          description="Las opciones de reemplazo son generadas por el backend basado en el alimento seleccionado."
          actions={<button type="button" className="protocol-secondary-button" onClick={() => setReplacementLab(null)}>Cerrar</button>}
        >
          {isReplacementLoading ? <p className="page-status">Cargando opciones de reemplazo...</p> : null}
          {replacementError ? <p className="page-status page-status-error">{replacementError}</p> : null}

          {!isReplacementLoading && replacementLab.options.length > 0 ? (
            <div className="replacement-lab-layout">
              <label>
                <span>Candidato de reemplazo</span>
                <select value={selectedReplacementCode} onChange={(event) => setSelectedReplacementCode(event.target.value)}>
                  {replacementLab.options.map((option) => (
                    <option key={option.food_code} value={option.food_code}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="replacement-lab-grid">
                {replacementLab.options.map((option) => (
                  <article
                    key={option.food_code}
                    className={`replacement-option-card ${selectedReplacementCode === option.food_code ? 'replacement-option-card-active' : ''}`.trim()}
                  >
                    <div>
                      <strong>{option.name}</strong>
                      <small>{formatDataSource(option.source)} // {option.category}</small>
                    </div>
                    <span>{formatMacro(option.recommended_grams ?? option.recommended_quantity)}</span>
                    <span>{formatCalories(option.calories)}</span>
                  </article>
                ))}
              </div>

              <button type="button" className="panel-cta-button" disabled={isMealActionLoading || !selectedReplacementCode} onClick={handleApplyReplacement}>
                {isMealActionLoading ? 'Aplicando reemplazo...' : 'Aplicar Reemplazo'}
              </button>
            </div>
          ) : null}
        </SectionPanel>
      ) : null}

      <div className="diets-support-layout">
        <SectionPanel eyebrow="Resumen de Adherencia Diaria">
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

        <SectionPanel eyebrow="Interpretación Semanal">
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

      <SectionPanel eyebrow="Archivo de Protocolos" title="Generaciones de dietas recientes">
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
                  <small>{diet.meals_count} comidas // {formatDataSource(diet.food_data_source)}</small>
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
