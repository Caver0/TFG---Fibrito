import { useMemo } from 'react'
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

function formatNumber(value, decimals = 1) {
  return Number(value ?? 0).toFixed(decimals)
}

function formatSignedValue(value, unit = '') {
  const numericValue = Number(value ?? 0)
  const prefix = numericValue > 0 ? '+' : ''
  return `${prefix}${formatNumber(numericValue)}${unit ? ` ${unit}` : ''}`
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

  return `Si (${attempts} consultas)`
}

function buildHighlightItems(diet) {
  return [
    {
      label: 'Objetivo diario',
      value: `${formatNumber(diet.target_calories)} kcal`,
      detail: `Dif. ${formatSignedValue(diet.calorie_difference, 'kcal')}`,
    },
    {
      label: 'Generado',
      value: `${formatNumber(diet.actual_calories)} kcal`,
      detail: `${diet.meals_count} comidas`,
    },
    {
      label: 'Proteina',
      value: `${formatNumber(diet.actual_protein_grams)} g`,
      detail: `Objetivo ${formatNumber(diet.protein_grams)} g`,
    },
    {
      label: 'Grasas',
      value: `${formatNumber(diet.actual_fat_grams)} g`,
      detail: `Objetivo ${formatNumber(diet.fat_grams)} g`,
    },
    {
      label: 'Carbohidratos',
      value: `${formatNumber(diet.actual_carb_grams)} g`,
      detail: `Objetivo ${formatNumber(diet.carb_grams)} g`,
    },
    {
      label: 'Entreno',
      value: diet.training_optimization_applied ? 'Optimizada' : 'Sin optimizar',
      detail: formatTrainingTimeOfDay(diet.training_time_of_day),
    },
  ]
}

function buildMetaItems(diet) {
  return [
    {
      label: 'Creada',
      value: formatDietTimestamp(diet.created_at),
    },
    {
      label: 'Fuentes',
      value: formatFoodSources(diet.food_data_sources, diet.food_data_source),
    },
    {
      label: 'Catalogo',
      value: diet.food_catalog_version ?? 'No aplica',
    },
    {
      label: 'Resolucion',
      value: formatCatalogSourceStrategy(diet.catalog_source_strategy),
    },
    {
      label: 'Spoonacular',
      value: formatResolutionSummary(diet),
    },
    {
      label: 'Compatibilidad',
      value: diet.food_preferences_applied ? 'Preferencias aplicadas' : 'Sin filtros extra',
    },
  ]
}

function DietCard({
  actionError,
  actionMessage,
  actionSummary,
  activeAdherenceMealNumber,
  activeFoodCode,
  activeMealNumber,
  adherenceRecordsByMeal,
  description,
  diet,
  error,
  isAdherenceSaving,
  isLoading,
  isMealActionLoading,
  onLoadReplacementOptions,
  onRegenerateMeal,
  onSaveMealAdherence,
  onReplaceFood,
  title,
}) {
  const highlightItems = useMemo(() => (diet ? buildHighlightItems(diet) : []), [diet])
  const metaItems = useMemo(() => (diet ? buildMetaItems(diet) : []), [diet])

  async function handleReplaceFood(mealNumber, payload) {
    if (!diet?.id) {
      return
    }

    return onReplaceFood(diet.id, mealNumber, payload)
  }

  async function handleRegenerate(mealNumber) {
    if (!diet?.id) {
      return
    }

    await onRegenerateMeal(diet.id, mealNumber)
  }

  async function handleLoadReplacementOptions(mealNumber, food) {
    if (!diet?.id) {
      return { options: [] }
    }

    return onLoadReplacementOptions(mealNumber, food)
  }

  async function handleSaveMealAdherence(mealNumber, payload) {
    if (!diet?.id || !onSaveMealAdherence) {
      return false
    }

    return onSaveMealAdherence(diet.id, mealNumber, payload)
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
          <div className="diet-overview-grid">
            <div className="diet-highlight-grid">
              {highlightItems.map((item) => (
                <article key={item.label} className="metric-card metric-card-highlight">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <small>{item.detail}</small>
                </article>
              ))}
            </div>

            <section className="diet-distribution-panel">
              <div className="diet-distribution-header">
                <div>
                  <span className="eyebrow">Distribucion del dia</span>
                  <h3>Reparto actual por comidas</h3>
                </div>
                <p>{diet.distribution_percentages?.length ? 'Resumen rapido de porcentaje, energia y macros por comida.' : 'No hay distribucion guardada para esta dieta.'}</p>
              </div>

              <div className="diet-distribution-grid">
                {diet.meals.map((meal) => (
                  <article key={`distribution-${meal.meal_number}`} className="diet-distribution-card">
                    <div className="diet-distribution-card-header">
                      <strong>Comida {meal.meal_number}</strong>
                      <span>{formatNumber(meal.distribution_percentage ?? 0)}%</span>
                    </div>
                    <p>{formatNumber(meal.actual_calories)} / {formatNumber(meal.target_calories)} kcal</p>
                    <div className="diet-distribution-card-macros">
                      <span>P {formatNumber(meal.actual_protein_grams)} g</span>
                      <span>G {formatNumber(meal.actual_fat_grams)} g</span>
                      <span>C {formatNumber(meal.actual_carb_grams)} g</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="diet-meta-panel">
              <div className="diet-meta-panel-header">
                <div>
                  <span className="eyebrow">Contexto</span>
                  <h3>Trazabilidad y resolucion</h3>
                </div>
              </div>

              <div className="diet-meta-grid">
                {metaItems.map((item) => (
                  <article key={item.label} className="diet-meta-card">
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </article>
                ))}
              </div>
            </section>

            {diet.food_filter_warnings?.length ? (
              <article className="diet-warning-panel">
                <strong>Notas de compatibilidad</strong>
                <ul className="diet-action-list">
                  {diet.food_filter_warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </article>
            ) : null}
          </div>

          <div className="meal-list meal-list-grid">
            {diet.meals.map((meal) => (
              <MealCard
                adherence={adherenceRecordsByMeal?.[meal.meal_number] ?? null}
                key={meal.meal_number}
                busyFoodCode={isMealActionLoading && activeMealNumber === meal.meal_number ? activeFoodCode : ''}
                isAdherenceSaving={Boolean(isAdherenceSaving && activeAdherenceMealNumber === meal.meal_number)}
                isBusy={isMealActionLoading}
                isRegenerating={isMealActionLoading && activeMealNumber === meal.meal_number && !activeFoodCode}
                meal={meal}
                onLoadReplacementOptions={handleLoadReplacementOptions}
                onRegenerate={handleRegenerate}
                onSaveAdherence={onSaveMealAdherence ? handleSaveMealAdherence : null}
                onReplaceFood={handleReplaceFood}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}

export default DietCard
