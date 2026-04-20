import { useMemo } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import MealCard from './MealCard'
import { formatTrainingTimeOfDay } from '../utils/dietDistribution'
import { buildMacroEnergyBreakdown } from '../utils/macroEnergy'

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

function formatPercentage(value) {
  return `${formatNumber(value ?? 0)}%`
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
      label: 'Proteína',
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
      label: 'Entrenamiento',
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
      label: 'Comidas',
      value: String(diet.meals_count ?? 0),
    },
    {
      label: 'Preferencias',
      value: diet.food_preferences_applied ? 'Aplicadas' : 'No aplicadas',
    },
  ]
}

function MacroTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null
  }

  const macro = payload[0]?.payload
  if (!macro) {
    return null
  }

  return (
    <div className="chart-tooltip">
      <strong>{macro.label}</strong>
      <p>{formatNumber(macro.calories)} kcal</p>
      <p>{formatNumber(macro.grams)} g</p>
      <p>{formatPercentage(macro.percentage)}</p>
    </div>
  )
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
  const macroBreakdown = useMemo(
    () => (diet ? buildMacroEnergyBreakdown(diet) : { totalCalories: 0, items: [] }),
    [diet],
  )

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
          <strong>Último cambio aplicado</strong>
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
        <p className="info-note">Todavía no hay una dieta generada para mostrar.</p>
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
                  <h3>Calorías y macros del plan</h3>
                </div>
                <p>Mostramos el reparto calórico de los macros actuales y el peso relativo de cada comida.</p>
              </div>

              <div className="diet-macro-summary">
                <div className="diet-macro-chart">
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie
                        data={macroBreakdown.items}
                        dataKey="calories"
                        nameKey="label"
                        innerRadius={58}
                        outerRadius={84}
                        paddingAngle={2}
                        stroke="none"
                      >
                        {macroBreakdown.items.map((item) => (
                          <Cell key={item.key} fill={item.color} />
                        ))}
                      </Pie>
                      <Tooltip content={<MacroTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="diet-macro-chart-center">
                    <strong>{formatNumber(macroBreakdown.totalCalories)} kcal</strong>
                    <span>Kcal totales</span>
                  </div>
                </div>

                <div className="diet-macro-legend">
                  {macroBreakdown.items.map((item) => (
                    <article key={item.key} className="diet-macro-legend-item">
                      <div className="diet-macro-legend-heading">
                        <span
                          className="diet-macro-color"
                          aria-hidden="true"
                          style={{ backgroundColor: item.color }}
                        />
                        <strong>{item.label}</strong>
                      </div>
                      <p>{formatNumber(item.grams)} g</p>
                      <p>{formatNumber(item.calories)} kcal</p>
                      <p>{formatPercentage(item.percentage)} del total</p>
                    </article>
                  ))}
                </div>
              </div>

              <div className="diet-distribution-grid">
                {diet.meals.map((meal) => (
                  <article key={`distribution-${meal.meal_number}`} className="diet-distribution-card">
                    <div className="diet-distribution-card-header">
                      <strong>Comida {meal.meal_number}</strong>
                      <span>
                        {meal.meal_label || 'Comida'}
                        {meal.distribution_percentage ? ` · ${formatNumber(meal.distribution_percentage)}%` : ''}
                      </span>
                    </div>
                    <p>{formatNumber(meal.actual_calories)} / {formatNumber(meal.target_calories)} kcal</p>
                    <MealCard meal={meal} showCompactMacroBar />
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
                  <span className="eyebrow">Resumen</span>
                  <h3>Información general</h3>
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
                <strong>Notas</strong>
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
                showMacroBar
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}

export default DietCard
