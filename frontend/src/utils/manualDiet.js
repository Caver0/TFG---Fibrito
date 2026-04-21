export const MANUAL_DIET_MIN_MEALS = 3
export const MANUAL_DIET_MAX_MEALS = 6
export const MANUAL_DIET_DEFAULT_MEALS = 4

function roundValue(value, digits = 1) {
  const numericValue = Number(value ?? 0)
  if (!Number.isFinite(numericValue)) {
    return 0
  }

  const factor = 10 ** digits
  return Math.round(numericValue * factor) / factor
}

function resolveStepByUnit(unit) {
  if (unit === 'ml') return 25
  if (unit === 'unidad') return 0.5
  return 5
}

export function createEmptyManualMeal(mealNumber) {
  return {
    meal_number: mealNumber,
    foods: [],
  }
}

export function createInitialManualMeals(mealsCount = MANUAL_DIET_DEFAULT_MEALS) {
  return Array.from({ length: Number(mealsCount) }, (_, index) => createEmptyManualMeal(index + 1))
}

export function syncManualMealsCount(currentMeals, nextMealsCount) {
  const normalizedCount = Math.min(
    MANUAL_DIET_MAX_MEALS,
    Math.max(MANUAL_DIET_MIN_MEALS, Number(nextMealsCount) || MANUAL_DIET_DEFAULT_MEALS),
  )
  const normalizedMeals = (currentMeals ?? []).slice(0, normalizedCount)
  const nextMeals = Array.from({ length: normalizedCount }, (_, index) => {
    const currentMeal = normalizedMeals[index]
    return {
      meal_number: index + 1,
      foods: currentMeal?.foods ?? [],
    }
  })

  return nextMeals
}

export function buildManualFoodFromCatalog(food) {
  return {
    food_code: food.code,
    name: food.display_name || food.name || food.original_name || food.normalized_name || 'Alimento',
    category: food.category || 'otros',
    quantity: Number(food.default_quantity ?? food.reference_amount ?? 100),
    unit: food.reference_unit || 'g',
    reference_amount: Number(food.reference_amount ?? 100),
    grams_per_reference: Number(food.grams_per_reference ?? food.reference_amount ?? 100),
    calories: Number(food.calories ?? 0),
    protein_grams: Number(food.protein_grams ?? 0),
    fat_grams: Number(food.fat_grams ?? 0),
    carb_grams: Number(food.carb_grams ?? 0),
    source: food.source || 'internal_catalog',
    origin_source: food.origin_source || food.source || 'internal_catalog',
    spoonacular_id: food.spoonacular_id ?? null,
    min_quantity: Number(food.min_quantity ?? food.default_quantity ?? food.reference_amount ?? 1),
    max_quantity: Number(food.max_quantity ?? Math.max((food.default_quantity ?? 100) * 3, 100)),
    step: Number(food.step ?? resolveStepByUnit(food.reference_unit)),
  }
}

export function buildManualFoodFromDietFood(food) {
  const quantity = Number(food.quantity ?? food.grams ?? 100)
  const unit = food.unit || 'g'
  return {
    food_code: food.food_code,
    name: food.name || 'Alimento',
    category: food.category || 'otros',
    quantity,
    unit,
    reference_amount: quantity || 1,
    grams_per_reference: Number(food.grams ?? quantity ?? 0),
    calories: Number(food.calories ?? 0),
    protein_grams: Number(food.protein_grams ?? 0),
    fat_grams: Number(food.fat_grams ?? 0),
    carb_grams: Number(food.carb_grams ?? 0),
    source: food.source || 'internal',
    origin_source: food.origin_source || food.source || 'internal',
    spoonacular_id: food.spoonacular_id ?? null,
    min_quantity: Number(food.quantity ?? 1),
    max_quantity: Math.max(Number(food.quantity ?? 1) * 3, Number(food.quantity ?? 1) + resolveStepByUnit(unit)),
    step: resolveStepByUnit(unit),
  }
}

export function buildManualMealsFromDiet(diet) {
  return (diet?.meals ?? []).map((meal, index) => ({
    meal_number: meal.meal_number ?? index + 1,
    foods: (meal.foods ?? []).map(buildManualFoodFromDietFood),
  }))
}

export function calculateManualFoodTotals(food) {
  const referenceAmount = Number(food?.reference_amount ?? 0)
  const quantity = Number(food?.quantity ?? 0)
  const scaleRatio = referenceAmount > 0 ? quantity / referenceAmount : 0

  return {
    calories: roundValue((Number(food?.calories ?? 0) * scaleRatio), 2),
    protein_grams: roundValue((Number(food?.protein_grams ?? 0) * scaleRatio), 2),
    fat_grams: roundValue((Number(food?.fat_grams ?? 0) * scaleRatio), 2),
    carb_grams: roundValue((Number(food?.carb_grams ?? 0) * scaleRatio), 2),
    grams: roundValue((Number(food?.grams_per_reference ?? 0) * scaleRatio), 2),
  }
}

export function calculateManualMealTotals(meal) {
  return (meal?.foods ?? []).reduce((totals, food) => {
    const foodTotals = calculateManualFoodTotals(food)
    return {
      calories: roundValue(totals.calories + foodTotals.calories, 1),
      protein_grams: roundValue(totals.protein_grams + foodTotals.protein_grams, 1),
      fat_grams: roundValue(totals.fat_grams + foodTotals.fat_grams, 1),
      carb_grams: roundValue(totals.carb_grams + foodTotals.carb_grams, 1),
    }
  }, {
    calories: 0,
    protein_grams: 0,
    fat_grams: 0,
    carb_grams: 0,
  })
}

export function calculateManualDailyTotals(meals) {
  return (meals ?? []).reduce((totals, meal) => {
    const mealTotals = calculateManualMealTotals(meal)
    return {
      calories: roundValue(totals.calories + mealTotals.calories, 1),
      protein_grams: roundValue(totals.protein_grams + mealTotals.protein_grams, 1),
      fat_grams: roundValue(totals.fat_grams + mealTotals.fat_grams, 1),
      carb_grams: roundValue(totals.carb_grams + mealTotals.carb_grams, 1),
    }
  }, {
    calories: 0,
    protein_grams: 0,
    fat_grams: 0,
    carb_grams: 0,
  })
}

export function calculateManualRemaining(targets, totals) {
  return {
    calories: roundValue(Number(targets?.target_calories ?? 0) - Number(totals?.calories ?? 0), 1),
    protein_grams: roundValue(Number(targets?.protein_grams ?? 0) - Number(totals?.protein_grams ?? 0), 1),
    fat_grams: roundValue(Number(targets?.fat_grams ?? 0) - Number(totals?.fat_grams ?? 0), 1),
    carb_grams: roundValue(Number(targets?.carb_grams ?? 0) - Number(totals?.carb_grams ?? 0), 1),
  }
}

function calculateRemainingRatio(targetValue, remainingValue) {
  const normalizedTarget = Number(targetValue ?? 0)
  if (normalizedTarget <= 0) {
    return 0
  }

  return Math.max(0, Math.min(1, Number(remainingValue ?? 0) / normalizedTarget))
}

export function buildManualRemainingMetrics(targets, remainingTotals) {
  return [
    {
      key: 'calories',
      label: 'Calorías restantes',
      remaining: Number(remainingTotals?.calories ?? 0),
      target: Number(targets?.target_calories ?? 0),
      progress: calculateRemainingRatio(targets?.target_calories, remainingTotals?.calories),
      isOverTarget: Number(remainingTotals?.calories ?? 0) < 0,
    },
    {
      key: 'protein_grams',
      label: 'Proteínas restantes',
      remaining: Number(remainingTotals?.protein_grams ?? 0),
      target: Number(targets?.protein_grams ?? 0),
      progress: calculateRemainingRatio(targets?.protein_grams, remainingTotals?.protein_grams),
      isOverTarget: Number(remainingTotals?.protein_grams ?? 0) < 0,
    },
    {
      key: 'fat_grams',
      label: 'Grasas restantes',
      remaining: Number(remainingTotals?.fat_grams ?? 0),
      target: Number(targets?.fat_grams ?? 0),
      progress: calculateRemainingRatio(targets?.fat_grams, remainingTotals?.fat_grams),
      isOverTarget: Number(remainingTotals?.fat_grams ?? 0) < 0,
    },
    {
      key: 'carb_grams',
      label: 'Carbohidratos restantes',
      remaining: Number(remainingTotals?.carb_grams ?? 0),
      target: Number(targets?.carb_grams ?? 0),
      progress: calculateRemainingRatio(targets?.carb_grams, remainingTotals?.carb_grams),
      isOverTarget: Number(remainingTotals?.carb_grams ?? 0) < 0,
    },
  ]
}

export function buildManualDietPayload({ baseDietId = null, meals }) {
  return {
    meals_count: Number(meals?.length ?? 0),
    base_diet_id: baseDietId || undefined,
    meals: (meals ?? []).map((meal, index) => ({
      meal_number: meal.meal_number ?? index + 1,
      foods: (meal.foods ?? []).map((food) => ({
        food_code: food.food_code,
        quantity: Number(food.quantity ?? 0),
      })),
    })),
  }
}

export function getManualDietAlignment(targets, totals) {
  const checks = [
    Number(targets?.target_calories ?? 0) > 0
      ? (Number(totals?.calories ?? 0) / Number(targets.target_calories))
      : 1,
    Number(targets?.protein_grams ?? 0) > 0
      ? (Number(totals?.protein_grams ?? 0) / Number(targets.protein_grams))
      : 1,
    Number(targets?.fat_grams ?? 0) > 0
      ? (Number(totals?.fat_grams ?? 0) / Number(targets.fat_grams))
      : 1,
    Number(targets?.carb_grams ?? 0) > 0
      ? (Number(totals?.carb_grams ?? 0) / Number(targets.carb_grams))
      : 1,
  ]
  const minCoverage = Math.min(...checks)
  const maxCoverage = Math.max(...checks)

  return {
    minCoverage,
    maxCoverage,
    needsAttention: minCoverage < 0.85 || maxCoverage > 1.15,
  }
}
