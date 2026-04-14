const MACRO_CONFIG = [
  {
    key: 'protein',
    label: 'Proteina',
    gramsKey: 'actual_protein_grams',
    factor: 4,
    color: '#f7c948',
  },
  {
    key: 'carbs',
    label: 'Carbohidratos',
    gramsKey: 'actual_carb_grams',
    factor: 4,
    color: '#2f6fe4',
  },
  {
    key: 'fat',
    label: 'Grasas',
    gramsKey: 'actual_fat_grams',
    factor: 9,
    color: '#8a5cf6',
  },
]

function formatSafeNumber(value) {
  const numericValue = Number(value ?? 0)
  return Number.isFinite(numericValue) ? numericValue : 0
}

export function getMacroChartConfig() {
  return MACRO_CONFIG
}

export function buildMacroEnergyBreakdown(source) {
  const totalCalories = formatSafeNumber(source?.actual_calories)
  const breakdown = MACRO_CONFIG.map((macro) => {
    const grams = formatSafeNumber(source?.[macro.gramsKey])
    const macroCalories = grams * macro.factor
    return {
      key: macro.key,
      label: macro.label,
      grams,
      calories: macroCalories,
      color: macro.color,
    }
  })
  const fallbackTotalCalories = breakdown.reduce((sum, macro) => sum + macro.calories, 0)
  const percentageBase = totalCalories > 0 ? totalCalories : fallbackTotalCalories

  return {
    totalCalories: totalCalories > 0 ? totalCalories : fallbackTotalCalories,
    items: breakdown.map((macro) => ({
      ...macro,
      percentage: percentageBase > 0 ? (macro.calories / percentageBase) * 100 : 0,
    })),
  }
}
