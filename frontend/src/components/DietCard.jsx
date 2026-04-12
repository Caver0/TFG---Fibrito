import { useState } from 'react'

import FoodReplacementModal from './FoodReplacementModal'
import MealCard from './MealCard'
import { formatTrainingTimeOfDay } from '../utils/dietDistribution'

function formatDietTimestamp(value) {
  if (!value) {
    return 'Sin fecha'
  }

  return new Date(value).toLocaleString('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatDistribution(percentages) {
  if (!percentages?.length) {
    return 'Sin distribucion guardada'
  }

  return percentages.map((value) => `${value}%`).join(' / ')
}

function formatNumber(value, decimals = 1) {
  return Number(value ?? 0).toFixed(decimals)
}

function formatFoodSource(value) {
  if (value === 'legacy_structural') {
    return 'Dieta estructural antigua'
  }

  if (value === 'mixed') {
    return 'Mixta'
  }

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

function formatFoodSources(values, fallbackValue) {
  const normalizedValues = values?.length ? values : [fallbackValue]
  return normalizedValues.map((value) => formatFoodSource(value)).join(' + ')
}

function formatCatalogSourceStrategy(value) {
  if (value === 'spoonacular_first_with_cache_fallback') {
    return 'Spoonacular primero, luego cache local y por ultimo catalogo interno'
  }

  if (value === 'internal_catalog_with_optional_spoonacular_enrichment') {
    return 'Catalogo interno con enriquecimiento opcional de Spoonacular'
  }

  return value || 'Sin estrategia registrada'
}

function formatResolutionSummary(diet) {
  const attempts = Number(diet.spoonacular_attempts ?? 0)
  if (!diet.spoonacular_attempted) {
    return 'No'
  }

  return `Si (${attempts} consultas de resolucion)`
}

function DietCard({
  actionError,
  actionMessage,
  actionSummary,
  activeFoodCode,
  activeMealNumber,
  description,
  diet,
  error,
  isLoading,
  isMealActionLoading,
  onRegenerateMeal,
  onReplaceFood,
  onSearchFoods,
  title,
}) {
  const [replacementTarget, setReplacementTarget] = useState(null)

  async function handleSubmitReplacement(payload) {
    if (!diet?.id || !replacementTarget) {
      return
    }

    const wasSuccessful = await onReplaceFood(diet.id, replacementTarget.mealNumber, payload)
    if (wasSuccessful) {
      setReplacementTarget(null)
    }
  }

  async function handleRegenerate(mealNumber) {
    if (!diet?.id) {
      return
    }

    await onRegenerateMeal(diet.id, mealNumber)
  }

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Dieta diaria</span>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>

      {isLoading ? <p className="info-note">Cargando dieta...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && actionError ? <p className="info-note info-note-warning">{actionError}</p> : null}
      {!isLoading && !error && actionMessage ? <p className="info-note">{actionMessage}</p> : null}
      {!isLoading && !error && actionSummary ? (
        <article className="diet-action-summary">
          <strong>Ultimo cambio aplicado</strong>
          <p>{actionSummary.message}</p>
          {actionSummary.strategy_notes?.length ? (
            <ul className="diet-action-list">
              {actionSummary.strategy_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </article>
      ) : null}
      {!isLoading && !error && !diet ? (
        <p className="info-note">Todavia no hay una dieta generada para mostrar.</p>
      ) : null}

      {!isLoading && diet ? (
        <>
          <div className="nutrition-grid">
            <article className="metric-card">
              <span>Creada</span>
              <strong>{formatDietTimestamp(diet.created_at)}</strong>
            </article>
            <article className="metric-card">
              <span>Comidas</span>
              <strong>{diet.meals_count}</strong>
            </article>
            <article className="metric-card">
              <span>Calorias generadas</span>
              <strong>{formatNumber(diet.actual_calories)} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Objetivo diario</span>
              <strong>{formatNumber(diet.target_calories)} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Proteina generada</span>
              <strong>{formatNumber(diet.actual_protein_grams)} g</strong>
            </article>
            <article className="metric-card">
              <span>Grasas generadas</span>
              <strong>{formatNumber(diet.actual_fat_grams)} g</strong>
            </article>
            <article className="metric-card">
              <span>Carbohidratos generados</span>
              <strong>{formatNumber(diet.actual_carb_grams)} g</strong>
            </article>
            <article className="metric-card">
              <span>Diferencia calorica</span>
              <strong>{formatNumber(diet.calorie_difference)} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Distribucion usada</span>
              <strong>{formatDistribution(diet.distribution_percentages)}</strong>
            </article>
            <article className="metric-card">
              <span>Fuente de alimentos</span>
              <strong>{formatFoodSource(diet.food_data_source)}</strong>
            </article>
            <article className="metric-card">
              <span>Fuentes usadas</span>
              <strong>{formatFoodSources(diet.food_data_sources, diet.food_data_source)}</strong>
            </article>
            <article className="metric-card">
              <span>Optimizacion por entreno</span>
              <strong>{diet.training_optimization_applied ? 'Si' : 'No'}</strong>
            </article>
            <article className="metric-card">
              <span>Momento de entreno</span>
              <strong>{formatTrainingTimeOfDay(diet.training_time_of_day)}</strong>
            </article>
            <article className="metric-card">
              <span>Version del catalogo</span>
              <strong>{diet.food_catalog_version ?? 'No aplica'}</strong>
            </article>
            <article className="metric-card">
              <span>Estrategia usada</span>
              <strong>{formatCatalogSourceStrategy(diet.catalog_source_strategy)}</strong>
            </article>
            <article className="metric-card">
              <span>Spoonacular intentado</span>
              <strong>{formatResolutionSummary(diet)}</strong>
            </article>
            <article className="metric-card">
              <span>Aciertos Spoonacular</span>
              <strong>{diet.spoonacular_hits ?? 0}</strong>
            </article>
            <article className="metric-card">
              <span>Aciertos cache</span>
              <strong>{diet.cache_hits ?? 0}</strong>
            </article>
            <article className="metric-card">
              <span>Fallback interno</span>
              <strong>{diet.internal_fallbacks ?? 0}</strong>
            </article>
            <article className="metric-card">
              <span>Alimentos resueltos</span>
              <strong>{diet.resolved_foods_count ?? 0}</strong>
            </article>
          </div>

          <div className="meal-list">
            {diet.meals.map((meal) => (
              <MealCard
                key={meal.meal_number}
                busyFoodCode={isMealActionLoading && activeMealNumber === meal.meal_number ? activeFoodCode : ''}
                isBusy={isMealActionLoading}
                isRegenerating={isMealActionLoading && activeMealNumber === meal.meal_number && !activeFoodCode}
                meal={meal}
                onOpenReplacement={(mealNumber, food) => setReplacementTarget({ mealNumber, food })}
                onRegenerate={handleRegenerate}
              />
            ))}
          </div>

          <FoodReplacementModal
            food={replacementTarget?.food}
            isOpen={Boolean(replacementTarget)}
            isSubmitting={isMealActionLoading}
            mealNumber={replacementTarget?.mealNumber}
            onClose={() => setReplacementTarget(null)}
            onSearchFoods={onSearchFoods}
            onSubmit={handleSubmitReplacement}
          />
        </>
      ) : null}
    </section>
  )
}

export default DietCard
