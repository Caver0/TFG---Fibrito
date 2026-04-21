import { useMemo, useState } from 'react'

import { useEffect } from 'react'
import * as foodsApi from '../api/foodsApi'
import SectionPanel from './SectionPanel'
import {
  buildManualRemainingMetrics,
  buildManualDietPayload,
  buildManualFoodFromCatalog,
  buildManualMealsFromDiet,
  calculateManualDailyTotals,
  calculateManualFoodTotals,
  calculateManualMealTotals,
  calculateManualRemaining,
  createInitialManualMeals,
  getManualDietAlignment,
  MANUAL_DIET_DEFAULT_MEALS,
  MANUAL_DIET_MAX_MEALS,
  MANUAL_DIET_MIN_MEALS,
  syncManualMealsCount,
} from '../utils/manualDiet'
import {
  formatCalories,
  formatCompactNumber,
  formatMacro,
  formatSignedCalories,
  formatSignedMass,
  getMealVisual,
} from '../utils/stitch'

function getFoodKey(food) {
  return food.food_code ?? food.name
}

function formatQuantityValue(food) {
  const quantity = Number(food.quantity ?? 0)
  return formatCompactNumber(quantity, {
    maximumFractionDigits: quantity < 1 ? 2 : 1,
    minimumFractionDigits: Number.isInteger(quantity) ? 0 : 1,
  })
}

function getFoodSearchEmptyMessage(response) {
  const reason = String(response?.meta?.empty_reason ?? '').trim()
  return reason || 'No hemos encontrado alimentos para esa búsqueda.'
}

function formatRemainingMetricValue(metric) {
  if (metric.key === 'calories') {
    return formatSignedCalories(metric.remaining)
  }

  return formatSignedMass(metric.remaining, { unit: 'g' })
}

function ManualDietBuilder({
  currentDiet,
  draftRequest = null,
  error,
  hidden = false,
  isSaving,
  message,
  nutrition,
  onCancelEdit,
  onSave,
  token,
}) {
  const [meals, setMeals] = useState(() => createInitialManualMeals(MANUAL_DIET_DEFAULT_MEALS))
  const [baseDietId, setBaseDietId] = useState(null)
  const [localError, setLocalError] = useState('')
  const [searchDrafts, setSearchDrafts] = useState({})
  const [searchResults, setSearchResults] = useState({})
  const [searchErrors, setSearchErrors] = useState({})
  const [searchingMealNumber, setSearchingMealNumber] = useState(null)

  const mealsCount = meals.length
  const mealTotalsByNumber = useMemo(
    () => Object.fromEntries(
      meals.map((meal) => [meal.meal_number, calculateManualMealTotals(meal)]),
    ),
    [meals],
  )
  const dailyTotals = useMemo(() => calculateManualDailyTotals(meals), [meals])
  const remainingTotals = useMemo(
    () => calculateManualRemaining(nutrition, dailyTotals),
    [nutrition, dailyTotals],
  )
  const remainingMetrics = useMemo(
    () => buildManualRemainingMetrics(nutrition, remainingTotals),
    [nutrition, remainingTotals],
  )
  const alignment = useMemo(
    () => getManualDietAlignment(nutrition, dailyTotals),
    [nutrition, dailyTotals],
  )
  const emptyMeals = meals.filter((meal) => !(meal.foods ?? []).length)
  const canSave = Boolean(nutrition && emptyMeals.length === 0 && !isSaving)

  useEffect(() => {
    if (!draftRequest?.diet) {
      return
    }

    const nextMeals = buildManualMealsFromDiet(draftRequest.diet)
    replaceMeals(nextMeals.length ? nextMeals : createInitialManualMeals(MANUAL_DIET_DEFAULT_MEALS))
    setBaseDietId(draftRequest.diet.id ?? null)
  }, [draftRequest])

  function resetSearchState() {
    setSearchDrafts({})
    setSearchResults({})
    setSearchErrors({})
    setSearchingMealNumber(null)
  }

  function replaceMeals(nextMeals) {
    setMeals(nextMeals)
    resetSearchState()
    setLocalError('')
  }

  function handleMealsCountChange(nextMealsCount) {
    replaceMeals(syncManualMealsCount(meals, nextMealsCount))
  }

  function handleAddMeal() {
    handleMealsCountChange(mealsCount + 1)
  }

  function handleRemoveMeal(mealNumber) {
    if (mealsCount <= MANUAL_DIET_MIN_MEALS) {
      return
    }

    replaceMeals(
      syncManualMealsCount(
        meals.filter((meal) => meal.meal_number !== mealNumber),
        mealsCount - 1,
      ),
    )
  }

  function handleSearchDraftChange(mealNumber, value) {
    setSearchDrafts((current) => ({
      ...current,
      [mealNumber]: value,
    }))
    setSearchErrors((current) => ({
      ...current,
      [mealNumber]: '',
    }))
  }

  async function handleSearch(event, mealNumber) {
    event.preventDefault()
    if (!token) return

    const query = String(searchDrafts[mealNumber] ?? '').trim()
    if (query.length < 2) {
      setSearchErrors((current) => ({
        ...current,
        [mealNumber]: 'Escribe al menos 2 caracteres para buscar un alimento.',
      }))
      setSearchResults((current) => ({
        ...current,
        [mealNumber]: [],
      }))
      return
    }

    setSearchingMealNumber(mealNumber)
    setSearchErrors((current) => ({
      ...current,
      [mealNumber]: '',
    }))

    try {
      const localResponse = await foodsApi.searchFoods(token, query, { limit: 6 })
      const localFoods = localResponse.foods ?? []
      let foods = localFoods
      let emptyMessage = getFoodSearchEmptyMessage(localResponse)

      if (!foods.length) {
        const externalResponse = await foodsApi.searchFoods(token, query, {
          limit: 6,
          includeExternal: true,
        })
        foods = externalResponse.foods ?? []
        emptyMessage = getFoodSearchEmptyMessage(externalResponse)
      }

      setSearchResults((current) => ({
        ...current,
        [mealNumber]: foods,
      }))

      if (!foods.length) {
        setSearchErrors((current) => ({
          ...current,
          [mealNumber]: emptyMessage,
        }))
      }
    } catch (searchError) {
      setSearchResults((current) => ({
        ...current,
        [mealNumber]: [],
      }))
      setSearchErrors((current) => ({
        ...current,
        [mealNumber]: searchError.message,
      }))
    } finally {
      setSearchingMealNumber(null)
    }
  }

  function handleAddFood(mealNumber, food) {
    const nextFood = buildManualFoodFromCatalog(food)

    setMeals((currentMeals) => currentMeals.map((meal) => {
      if (meal.meal_number !== mealNumber) {
        return meal
      }

      const existingFoodIndex = meal.foods.findIndex((item) => item.food_code === nextFood.food_code)
      if (existingFoodIndex === -1) {
        return {
          ...meal,
          foods: [...meal.foods, nextFood],
        }
      }

      return {
        ...meal,
        foods: meal.foods.map((item, index) => {
          if (index !== existingFoodIndex) {
            return item
          }

          return {
            ...item,
            quantity: Number(item.quantity ?? 0) + Number(nextFood.quantity ?? 0),
          }
        }),
      }
    }))

    setLocalError('')
  }

  function handleQuantityChange(mealNumber, foodCode, value) {
    const parsedValue = Number(value)
    if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
      return
    }

    setMeals((currentMeals) => currentMeals.map((meal) => {
      if (meal.meal_number !== mealNumber) {
        return meal
      }

      return {
        ...meal,
        foods: meal.foods.map((food) => (
          food.food_code === foodCode
            ? { ...food, quantity: parsedValue }
            : food
        )),
      }
    }))
  }

  function handleRemoveFood(mealNumber, foodCode) {
    setMeals((currentMeals) => currentMeals.map((meal) => {
      if (meal.meal_number !== mealNumber) {
        return meal
      }

      return {
        ...meal,
        foods: meal.foods.filter((food) => food.food_code !== foodCode),
      }
    }))
  }

  function handleResetBuilder() {
    replaceMeals(createInitialManualMeals(MANUAL_DIET_DEFAULT_MEALS))
    setBaseDietId(null)
  }

  function handleCancelEdit() {
    handleResetBuilder()
    onCancelEdit?.()
  }

  function handleUseVisibleManualDiet() {
    if (currentDiet?.diet_mode !== 'manual') {
      return
    }

    const nextMeals = buildManualMealsFromDiet(currentDiet)
    replaceMeals(nextMeals.length ? nextMeals : createInitialManualMeals(MANUAL_DIET_DEFAULT_MEALS))
    setBaseDietId(currentDiet.id ?? null)
  }

  async function handleSave(event) {
    event?.preventDefault?.()

    if (!nutrition) {
      setLocalError('Completa tu perfil nutricional para poder construir una dieta manual.')
      return
    }

    if (emptyMeals.length > 0) {
      setLocalError('Añade al menos un alimento en cada comida antes de guardar.')
      return
    }

    setLocalError('')
    const savedDiet = await onSave(buildManualDietPayload({ baseDietId, meals }))
    if (savedDiet?.diet_mode === 'manual') {
      replaceMeals(buildManualMealsFromDiet(savedDiet))
      setBaseDietId(savedDiet.id ?? null)
    }
  }

  return (
    <div hidden={hidden}>
      <SectionPanel
        eyebrow="Dieta manual"
        title="Construye tu dieta"
        description="Reparte tus alimentos con los objetivos diarios de tu perfil. Al guardarla, entrará en historial, adherencia y dashboard como una dieta normal."
        className="manual-diet-builder-panel"
        actions={(
          <div className="manual-diet-panel-actions">
            <button type="button" className="protocol-secondary-button" onClick={handleCancelEdit}>
              {baseDietId ? 'Cancelar edición' : 'Cancelar'}
            </button>
            {currentDiet?.diet_mode === 'manual' ? (
              <button type="button" className="protocol-secondary-button" onClick={handleUseVisibleManualDiet}>
                Usar dieta activa
              </button>
            ) : null}
            <button type="button" className="protocol-secondary-button" onClick={handleResetBuilder}>
              Nueva manual
            </button>
          </div>
        )}
      >
        {!nutrition ? (
          <p className="page-status page-status-error">
            Necesitas completar el perfil nutricional para crear una dieta manual.
          </p>
        ) : (
          <>
            <div className="manual-diet-hero">
              <div className="manual-diet-hero-copy">
                <div className="manual-diet-hero-tags">
                  <span className="panel-tag panel-tag-manual">Manual</span>
                  <span className="panel-tag panel-tag-neutral">
                    {baseDietId ? 'Base cargada desde una dieta previa' : 'Nueva construcción'}
                  </span>
                </div>
                <p className="panel-placeholder">
                  Ajusta cada comida con feedback en tiempo real y guarda un plan que seguirá el mismo ciclo de la dieta activa de Fibrito.
                </p>
              </div>
            </div>

            <div className="manual-diet-summary-grid">
              <article className="metric-card metric-card-highlight manual-diet-summary-card">
                <span>Objetivo diario</span>
                <strong>{formatCalories(nutrition.target_calories)}</strong>
                <small>
                  P {formatMacro(nutrition.protein_grams)} / C {formatMacro(nutrition.carb_grams)} / G {formatMacro(nutrition.fat_grams)}
                </small>
              </article>

              <article className="metric-card manual-diet-summary-card">
                <span>Acumulado</span>
                <strong>{formatCalories(dailyTotals.calories)}</strong>
                <small>
                  P {formatMacro(dailyTotals.protein_grams)} / C {formatMacro(dailyTotals.carb_grams)} / G {formatMacro(dailyTotals.fat_grams)}
                </small>
              </article>

              <article className="metric-card manual-diet-summary-card">
                <span>Restante</span>
                <strong>{formatSignedCalories(remainingTotals.calories)}</strong>
                <small>
                  P {formatSignedMass(remainingTotals.protein_grams, { unit: 'g' })} / C {formatSignedMass(remainingTotals.carb_grams, { unit: 'g' })} / G {formatSignedMass(remainingTotals.fat_grams, { unit: 'g' })}
                </small>
              </article>
            </div>

            {alignment.needsAttention ? (
              <p className="page-status manual-diet-guidance">
                Intenta acercarte un poco más a tus objetivos diarios. Si la dieta manual se queda lejos de lo asignado, el seguimiento posterior puede ser menos representativo.
              </p>
            ) : null}

            <div className="manual-diet-toolbar">
              <div className="manual-diet-toolbar-copy">
                <span>Comidas del día</span>
                <strong>{mealsCount}</strong>
              </div>

              <div className="manual-diet-stepper">
                <button
                  type="button"
                  className="protocol-chip-button"
                  disabled={mealsCount <= MANUAL_DIET_MIN_MEALS}
                  onClick={() => handleMealsCountChange(mealsCount - 1)}
                >
                  Menos
                </button>
                <button
                  type="button"
                  className="protocol-chip-button"
                  disabled={mealsCount >= MANUAL_DIET_MAX_MEALS}
                  onClick={handleAddMeal}
                >
                  Más
                </button>
              </div>
            </div>

            <div className="manual-diet-builder-form">
              <div className="manual-diet-remaining-grid">
                {remainingMetrics.map((metric) => (
                  <article
                    key={metric.key}
                    className={`metric-card manual-diet-remaining-card ${metric.isOverTarget ? 'manual-diet-remaining-card-danger' : ''}`.trim()}
                  >
                    <div className="manual-diet-remaining-head">
                      <span>{metric.label}</span>
                      <strong>{formatRemainingMetricValue(metric)}</strong>
                    </div>
                    <div className="macro-line-track">
                      <div
                        className={`macro-line-fill ${metric.isOverTarget ? 'manual-diet-remaining-fill-danger' : ''}`.trim()}
                        style={{ width: `${metric.progress * 100}%` }}
                      />
                    </div>
                    <small className="manual-diet-remaining-target">
                      Objetivo: {metric.key === 'calories' ? formatCalories(metric.target) : `${formatMacro(metric.target)} g`}
                    </small>
                  </article>
                ))}
              </div>

              <div className="meal-protocol-grid">
                {meals.map((meal) => {
                  const visual = getMealVisual(meal.meal_number, 'meal', `Comida ${meal.meal_number}`)
                  const mealTotals = mealTotalsByNumber[meal.meal_number] ?? calculateManualMealTotals(meal)

                  return (
                    <article key={meal.meal_number} className="protocol-meal-card manual-diet-meal-card">
                      <div className={`protocol-meal-hero ${visual.heroClassName}`.trim()}>
                        <div className="protocol-meal-overlay" />
                        <div className="protocol-meal-copy">
                          <span>{visual.phase}</span>
                          <h3>{visual.label}</h3>
                        </div>
                        <div className="protocol-meal-kcal">{formatCalories(mealTotals.calories)}</div>
                      </div>

                      <div className="protocol-meal-body">
                        <div className="manual-diet-meal-head">
                          <div className="protocol-meal-summary">
                            <span>Alimentos</span>
                            <strong>{meal.foods.length}</strong>
                          </div>

                          {mealsCount > MANUAL_DIET_MIN_MEALS ? (
                            <button
                              type="button"
                              className="protocol-secondary-button manual-diet-remove-meal"
                              onClick={() => handleRemoveMeal(meal.meal_number)}
                            >
                              Eliminar comida
                            </button>
                          ) : null}
                        </div>

                        {meal.foods.length ? (
                          <div className="protocol-food-list">
                            {meal.foods.map((food) => {
                              const foodTotals = calculateManualFoodTotals(food)
                              return (
                                <div key={`${meal.meal_number}-${getFoodKey(food)}`} className="protocol-food-row manual-diet-food-row">
                                  <div className="protocol-food-copy">
                                    <strong>{food.name}</strong>
                                    <small>{food.category}</small>
                                  </div>

                                  <div className="manual-diet-food-controls">
                                    <label className="manual-diet-quantity-field">
                                      <span>Cantidad</span>
                                      <div className="manual-diet-quantity-input">
                                        <input
                                          type="number"
                                          min={food.min_quantity}
                                          max={food.max_quantity}
                                          step={food.step}
                                          value={food.quantity}
                                          onChange={(event) => handleQuantityChange(meal.meal_number, food.food_code, event.target.value)}
                                        />
                                        <small>{food.unit}</small>
                                      </div>
                                    </label>

                                    <div className="protocol-food-inline-metrics">
                                      <div className="protocol-food-breakdown">
                                        <span>{formatCompactNumber(foodTotals.grams, { maximumFractionDigits: 0 })} g</span>
                                        <span>{formatCalories(foodTotals.calories)}</span>
                                      </div>
                                      <div className="protocol-food-macros">
                                        <span>P {formatMacro(foodTotals.protein_grams)}</span>
                                        <span>C {formatMacro(foodTotals.carb_grams)}</span>
                                        <span>G {formatMacro(foodTotals.fat_grams)}</span>
                                      </div>
                                    </div>
                                  </div>

                                  <div className="protocol-food-meta">
                                    <button type="button" onClick={() => handleRemoveFood(meal.meal_number, food.food_code)}>
                                      Quitar
                                    </button>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <p className="panel-placeholder">Añade alimentos a esta comida para empezar a repartir tus macros.</p>
                        )}

                        <div className="protocol-meal-macros">
                          <div className="protocol-meal-macros-kcal">
                            <span>{formatCalories(mealTotals.calories)}</span>
                          </div>
                          <div className="protocol-meal-macros-grid">
                            <div className="protocol-meal-macro-item">
                              <strong>{formatMacro(mealTotals.protein_grams)}</strong>
                              <small>Proteínas</small>
                            </div>
                            <div className="protocol-meal-macro-item">
                              <strong>{formatMacro(mealTotals.carb_grams)}</strong>
                              <small>Carbohidratos</small>
                            </div>
                            <div className="protocol-meal-macro-item">
                              <strong>{formatMacro(mealTotals.fat_grams)}</strong>
                              <small>Grasas</small>
                            </div>
                          </div>
                        </div>

                        <form className="replacement-search-panel manual-diet-search-panel" onSubmit={(event) => handleSearch(event, meal.meal_number)}>
                          <div className="replacement-search-head">
                            <strong>Buscar alimento</strong>
                            <small>Usa el mismo catálogo de alimentos del sistema para construir esta comida.</small>
                          </div>

                          <div className="replacement-search-row">
                            <input
                              type="text"
                              value={searchDrafts[meal.meal_number] ?? ''}
                              placeholder="Ej. arroz, yogur, salmón..."
                              onChange={(event) => handleSearchDraftChange(meal.meal_number, event.target.value)}
                            />
                            <button
                              type="submit"
                              className="protocol-secondary-button"
                              disabled={searchingMealNumber === meal.meal_number}
                            >
                              {searchingMealNumber === meal.meal_number ? 'Buscando...' : 'Buscar'}
                            </button>
                          </div>

                          {searchErrors[meal.meal_number] ? (
                            <p className="page-status page-status-error">{searchErrors[meal.meal_number]}</p>
                          ) : null}

                          {(searchResults[meal.meal_number] ?? []).length ? (
                            <div className="replacement-search-results">
                              {searchResults[meal.meal_number].map((food) => (
                                <article key={food.code} className="replacement-search-card replacement-search-card-valid">
                                  <div className="replacement-search-card-head">
                                    <div>
                                      <strong>{food.display_name || food.name}</strong>
                                      <small>
                                        {food.category} / {formatQuantityValue({
                                          quantity: food.default_quantity ?? food.reference_amount,
                                        })} {food.reference_unit}
                                      </small>
                                    </div>
                                    <div className="replacement-search-card-meta">
                                      <span>{formatCalories(food.calories)}</span>
                                    </div>
                                  </div>

                                  <div className="replacement-search-card-macros">
                                    <span>P {formatMacro(food.protein_grams)}</span>
                                    <span>C {formatMacro(food.carb_grams)}</span>
                                    <span>G {formatMacro(food.fat_grams)}</span>
                                  </div>

                                  <button
                                    type="button"
                                    className="protocol-secondary-button replacement-search-action"
                                    onClick={() => handleAddFood(meal.meal_number, food)}
                                  >
                                    Añadir
                                  </button>
                                </article>
                              ))}
                            </div>
                          ) : null}
                        </form>
                      </div>
                    </article>
                  )
                })}
              </div>

              {localError ? <p className="page-status page-status-error">{localError}</p> : null}
              {error ? <p className="page-status page-status-error">{error}</p> : null}
              {message ? <p className="page-status page-status-success">{message}</p> : null}

              <div className="manual-diet-footer">
                <div className="manual-diet-footer-copy">
                  <strong>{baseDietId ? 'Guardar nueva versión manual' : 'Guardar dieta manual'}</strong>
                  <span>
                    {baseDietId
                      ? 'Se guardará como una nueva dieta activa sin perder la dieta base del historial.'
                      : 'La dieta manual quedará disponible igual que una dieta generada automáticamente.'}
                  </span>
                </div>

                <button type="button" className="panel-cta-button" disabled={!canSave} onClick={handleSave}>
                  {isSaving
                    ? 'Guardando dieta manual...'
                    : baseDietId
                      ? 'Guardar nueva versión'
                      : 'Guardar dieta manual'}
                </button>
              </div>
            </div>
          </>
        )}
      </SectionPanel>
    </div>
  )
}

export default ManualDietBuilder

