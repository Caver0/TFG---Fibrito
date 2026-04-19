const MACRO_CALORIE_FACTORS = {
  protein: 4,
  fat: 9,
  carb: 4,
}

const CATEGORY_MACRO_HINTS = {
  proteinas: 'protein',
  carbohidratos: 'carb',
  cereales: 'carb',
  frutas: 'carb',
  grasas: 'fat',
}

function normalizeText(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLowerCase()
}

function getMacroEnergy(food) {
  return {
    protein: Number(food?.protein_grams ?? 0) * MACRO_CALORIE_FACTORS.protein,
    fat: Number(food?.fat_grams ?? 0) * MACRO_CALORIE_FACTORS.fat,
    carb: Number(food?.carb_grams ?? 0) * MACRO_CALORIE_FACTORS.carb,
  }
}

function getMacroHintFromFood(food) {
  const categoryHint = CATEGORY_MACRO_HINTS[normalizeText(food?.category)]
  if (categoryHint) {
    return categoryHint
  }

  const foodText = normalizeText([food?.name, food?.food_code].filter(Boolean).join(' '))
  if (/(aceite|oil|olive oil|aguacate|avocado|nueces|nuts|almendra|almond|peanut|cacahuete|seed|chia|lino)/.test(foodText)) {
    return 'fat'
  }
  if (/(yogur|yogurt|skyr|quark|cottage|queso batido|pollo|chicken|pavo|turkey|atun|tuna|egg|huevo|claras|tofu|protein)/.test(foodText)) {
    return 'protein'
  }
  if (/(banana|platano|manzana|apple|mango|fruta|fruit|arroz|rice|avena|oats|pasta|patata|potato|pan|bread|cereal)/.test(foodText)) {
    return 'carb'
  }

  return null
}

export function inferDominantMacroFromFood(food) {
  const macroEnergy = getMacroEnergy(food)
  const ranked = ['protein', 'fat', 'carb'].sort((left, right) => {
    if (macroEnergy[right] === macroEnergy[left]) {
      return 0
    }
    return macroEnergy[right] - macroEnergy[left]
  })
  const primaryMacro = ranked[0]
  const secondaryMacro = ranked[1]
  const hint = getMacroHintFromFood(food)

  if (macroEnergy[primaryMacro] <= 0) {
    return hint ?? 'carb'
  }
  if (macroEnergy[primaryMacro] >= (macroEnergy[secondaryMacro] * 1.08) || (macroEnergy[primaryMacro] - macroEnergy[secondaryMacro]) >= 4) {
    return primaryMacro
  }
  return hint ?? primaryMacro
}

export function resolveCurrentMacroDominante(food, apiMacro) {
  return apiMacro || inferDominantMacroFromFood(food)
}

export function mergeReplacementOptions(...optionGroups) {
  const mergedOptions = []
  const seenCodes = new Set()

  optionGroups.flat().forEach((option) => {
    if (!option?.food_code || seenCodes.has(option.food_code)) {
      return
    }

    mergedOptions.push(option)
    seenCodes.add(option.food_code)
  })

  return mergedOptions
}

export function getReplacementOptionsForDisplay(replacementLab) {
  if (!replacementLab) {
    return []
  }

  return mergeReplacementOptions(replacementLab.manualOptions ?? [], replacementLab.options ?? [])
}
