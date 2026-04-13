import { Fragment, useMemo, useState } from 'react'

import FoodReplacementModal from './FoodReplacementModal'
import MealAdherenceControls from './MealAdherenceControls'

function formatNumber(value, decimals = 1) {
  return Number(value ?? 0).toFixed(decimals)
}

function formatFoodQuantity(food) {
  const quantity = Number(food.quantity ?? 0)
  const quantityLabel = Number.isInteger(quantity)
    ? quantity.toFixed(0)
    : quantity.toFixed(quantity < 1 ? 2 : 1)
  const unit = food.unit === 'unidad' ? (quantity === 1 ? 'unidad' : 'unidades') : food.unit
  const baseLabel = `${quantityLabel} ${unit}`

  if (!food.grams || food.unit === 'g') {
    return baseLabel
  }

  return `${baseLabel} (${formatNumber(food.grams, 1)} g aprox.)`
}

function formatFoodSource(value) {
  if (value === 'internal_catalog' || value === 'internal') {
    return 'Catalogo interno'
  }

  if (value === 'local_cache' || value === 'cache') {
    return 'Cache local'
  }

  if (value === 'spoonacular') {
    return 'Spoonacular'
  }

  return value || 'No indicado'
}

function formatFoodLineage(food) {
  const source = food.source
  const originSource = food.origin_source

  if ((source === 'local_cache' || source === 'cache') && originSource === 'spoonacular') {
    return 'Cache local reutilizada desde Spoonacular'
  }

  if (source === 'spoonacular') {
    return 'Spoonacular en vivo'
  }

  return formatFoodSource(source)
}

function MealCard({
  adherence,
  busyFoodCode,
  isAdherenceSaving,
  isBusy,
  isRegenerating,
  meal,
  onLoadReplacementOptions,
  onRegenerate,
  onSaveAdherence,
  onReplaceFood,
}) {
  const [replacementTarget, setReplacementTarget] = useState(null)

  const replacementTargetKey = useMemo(
    () => replacementTarget?.food_code ?? replacementTarget?.name ?? '',
    [replacementTarget],
  )

  async function handleSubmitReplacement(payload) {
    const wasSuccessful = await onReplaceFood(meal.meal_number, payload)
    if (wasSuccessful) {
      setReplacementTarget(null)
    }
  }

  function handleToggleReplacement(food) {
    const foodKey = food.food_code ?? food.name
    if (replacementTargetKey === foodKey) {
      setReplacementTarget(null)
      return
    }

    setReplacementTarget(food)
  }

  return (
    <article className="meal-card">
      <div className="meal-card-header meal-card-header-actions">
        <div>
          <strong>Comida {meal.meal_number}</strong>
          <span>{meal.distribution_percentage ?? 'Sin dato'}%</span>
        </div>

        <button
          className="secondary-button meal-action-button"
          disabled={isBusy}
          type="button"
          onClick={() => onRegenerate(meal.meal_number)}
        >
          {isRegenerating ? 'Regenerando...' : 'Regenerar comida'}
        </button>
      </div>

      <div className="meal-summary-grid">
        <div className="meal-summary-item">
          <span>Calorias</span>
          <strong>{formatNumber(meal.actual_calories)} / {formatNumber(meal.target_calories)} kcal</strong>
        </div>
        <div className="meal-summary-item">
          <span>Proteina</span>
          <strong>{formatNumber(meal.actual_protein_grams)} / {formatNumber(meal.target_protein_grams)} g</strong>
        </div>
        <div className="meal-summary-item">
          <span>Grasas</span>
          <strong>{formatNumber(meal.actual_fat_grams)} / {formatNumber(meal.target_fat_grams)} g</strong>
        </div>
        <div className="meal-summary-item">
          <span>Carbohidratos</span>
          <strong>{formatNumber(meal.actual_carb_grams)} / {formatNumber(meal.target_carb_grams)} g</strong>
        </div>
      </div>

      {onSaveAdherence ? (
        <MealAdherenceControls
          adherence={adherence}
          isSaving={isAdherenceSaving}
          mealNumber={meal.meal_number}
          onSave={onSaveAdherence}
        />
      ) : null}

      {meal.foods?.length ? (
        <div className="food-list food-list-grid">
          {meal.foods.map((food) => {
            const foodKey = food.food_code ?? food.name
            const isReplacing = busyFoodCode === foodKey
            const isReplacementOpen = replacementTargetKey === foodKey

            return (
              <Fragment key={`${meal.meal_number}-${foodKey}`}>
                <article className={`food-row ${isReplacementOpen ? 'food-row-active' : ''}`}>
                  <div className="food-row-header">
                    <div className="food-row-title">
                      <strong>{food.name}</strong>
                      <span>{formatFoodQuantity(food)}</span>
                    </div>

                    <button
                      className="secondary-button food-action-button"
                      disabled={isBusy}
                      type="button"
                      onClick={() => handleToggleReplacement(food)}
                    >
                      {isReplacing ? 'Sustituyendo...' : isReplacementOpen ? 'Cerrar sustitucion' : 'Sustituir'}
                    </button>
                  </div>

                  <p className="food-row-meta">
                    {formatNumber(food.calories, 2)} kcal | P {formatNumber(food.protein_grams, 2)} g | G {formatNumber(food.fat_grams, 2)} g | C {formatNumber(food.carb_grams, 2)} g
                  </p>
                  <p className="food-row-source">
                    {formatFoodLineage(food)}{food.spoonacular_id ? ` | Spoonacular ID ${food.spoonacular_id}` : ''}
                  </p>
                </article>

                {isReplacementOpen ? (
                  <div className="food-replacement-slot">
                    <FoodReplacementModal
                      food={replacementTarget}
                      isOpen={Boolean(replacementTarget)}
                      isSubmitting={busyFoodCode === replacementTargetKey && isBusy}
                      mealNumber={meal.meal_number}
                      onCancel={() => setReplacementTarget(null)}
                      onLoadOptions={onLoadReplacementOptions}
                      onSubmit={handleSubmitReplacement}
                    />
                  </div>
                ) : null}
              </Fragment>
            )
          })}
        </div>
      ) : (
        <p className="info-note">Esta dieta no tiene alimentos concretos guardados.</p>
      )}
    </article>
  )
}

export default MealCard
