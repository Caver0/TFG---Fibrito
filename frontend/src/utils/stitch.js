export const STITCH_DIET_VISUALS = {
  breakfast: {
    label: 'Desayuno',
    heroClassName: 'protocol-meal-hero--breakfast',
  },
  pre_workout: {
    label: 'Pre-entrenamiento',
    heroClassName: 'protocol-meal-hero--pre-workout',
  },
  post_workout: {
    label: 'Post-entrenamiento',
    heroClassName: 'protocol-meal-hero--post-workout',
  },
  dinner: {
    label: 'Cena',
    heroClassName: 'protocol-meal-hero--dinner',
  },
  training_focus: {
    label: 'Comida de entreno',
    heroClassName: 'protocol-meal-hero--training-focus',
  },
  meal: {
    label: 'Comida',
    heroClassName: 'protocol-meal-hero--meal',
  },
}

export const STITCH_PROFILE_TARGET_BACKGROUND =
  'https://lh3.googleusercontent.com/aida-public/AB6AXuCGw2brtsYaK1cZJ19rRoGmAxDqXPCbCAkHlUyN4frBetqb2gwaW65Y0ATxjctW4YjFQn3okOA1URUiCKcOt9gcb_v_zDgSMegWYsZ4KdbaWm0oTo16rLsIfUxvNu1fTauzFAr01nRoFVZaWNZpe43bsFylNp8zpKqb28AqBLnCTAiFR_efZb_LdaGRFAuSD43cdhUdDP5Oye530msf1P4Zsog_jNcIaFtTeVmdzlFuaIYcaQf77nbBwfD0xnF7U20fd88dLqnbNZ0'

function toFiniteNumber(value) {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

export function formatCompactNumber(value, options = {}) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: options.maximumFractionDigits ?? 1,
    minimumFractionDigits: options.minimumFractionDigits ?? 0,
  }).format(numericValue)
}

export function formatMass(value, options = {}) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(numericValue, {
    maximumFractionDigits: options.maximumFractionDigits ?? 1,
    minimumFractionDigits: options.minimumFractionDigits ?? 0,
  })} ${options.unit ?? 'kg'}`
}

export function formatSignedMass(value, options = {}) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  const prefix = numericValue > 0 ? '+' : ''
  return `${prefix}${formatMass(numericValue, options)}`
}

export function formatCalories(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(Math.round(numericValue), {
    maximumFractionDigits: 0,
  })} kcal`
}

export function formatSignedCalories(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  const roundedValue = Math.round(numericValue)
  const prefix = roundedValue > 0 ? '+' : ''
  return `${prefix}${formatCompactNumber(roundedValue, { maximumFractionDigits: 0 })} kcal`
}

export function formatMacro(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(numericValue, {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  })}g`
}

export function formatPercent(value, digits = 1) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(numericValue, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })}%`
}

export function formatDateLabel(value, options = {}) {
  if (!value) {
    return 'Sin fecha'
  }

  const parsedDate = new Date(value)
  if (Number.isNaN(parsedDate.getTime())) {
    return 'Sin fecha'
  }

  return new Intl.DateTimeFormat('en-GB', {
    day: options.day ?? '2-digit',
    month: options.month ?? 'short',
    year: options.year ?? undefined,
  }).format(parsedDate)
}

export function formatDayLabel(value) {
  if (!value) {
    return 'DÍA'
  }

  const parsedDate = new Date(value)
  if (Number.isNaN(parsedDate.getTime())) {
    return 'DÍA'
  }

  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
  })
    .format(parsedDate)
    .toUpperCase()
}

export function formatGoalLabel(goal) {
  if (goal === 'perder_grasa') {
    return 'Definición / Pérdida'
  }
  if (goal === 'mantener_peso') {
    return 'Mantenimiento'
  }
  if (goal === 'ganar_masa') {
    return 'Hipertrofia / Volumen'
  }
  return 'Configuración de perfil'
}

export function formatGoalPhase(goal) {
  if (goal === 'perder_grasa') {
    return 'FASE: RECOMPOSICIÓN'
  }
  if (goal === 'ganar_masa') {
    return 'FASE: CRECIMIENTO'
  }
  if (goal === 'mantener_peso') {
    return 'FASE: MANTENIMIENTO'
  }
  return 'FASE: CONFIGURACIÓN'
}

export function formatGoalDescription(goal) {
  if (goal === 'perder_grasa') {
    return 'Déficit calórico calibrado para reducir grasa corporal.'
  }
  if (goal === 'ganar_masa') {
    return 'Aporte superior centrado en ganar masa muscular.'
  }
  if (goal === 'mantener_peso') {
    return 'Consumo estable para preservar el estado de tu cuerpo.'
  }
  return 'Completa tu perfil nutricional para calibrar las metas.'
}

export function formatSexLabel(value) {
  if (value === 'Masculino') {
    return 'Hombre'
  }
  if (value === 'Femenino') {
    return 'Mujer'
  }
  return 'No especificado'
}

export function formatTrainingFrequency(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'No especificado'
  }

  if (numericValue === 0) {
    return 'Mayormente descanso'
  }
  if (numericValue === 1) {
    return '1 día / semana'
  }

  return `${numericValue} días / semana`
}

export function formatAdherenceLevel(level) {
  if (level === 'alta') {
    return 'Óptimo'
  }
  if (level === 'media') {
    return 'Moderado'
  }
  if (level === 'baja') {
    return 'Bajo'
  }
  return 'Pendiente'
}

export function formatDataSource(source) {
  if (source === 'spoonacular') {
    return 'Spoonacular'
  }
  if (source === 'cache') {
    return 'Caché'
  }
  if (source === 'mixed') {
    return 'Híbrida'
  }
  return 'Interno'
}

export function formatMealRoleLabel(role) {
  return STITCH_DIET_VISUALS[role]?.label ?? 'Comida'
}

export function getMealVisual(mealNumber, mealRole, mealLabel) {
  const visual = STITCH_DIET_VISUALS[mealRole] ?? STITCH_DIET_VISUALS.meal
  return {
    phase: `COMIDA ${mealNumber}`,
    label: mealLabel || visual.label || `Comida ${mealNumber}`,
    heroClassName: visual.heroClassName || STITCH_DIET_VISUALS.meal.heroClassName,
  }
}

export function getInitials(name) {
  return String(name || 'Fibrito')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

export function clampPercentage(value, fallback = 0) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return fallback
  }

  return Math.min(100, Math.max(0, numericValue))
}

export function toConfidenceScore(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 0
  }

  if (numericValue <= 1) {
    return clampPercentage(numericValue * 100)
  }

  return clampPercentage(numericValue)
}

export function resolveRegisteredAdherencePercentage(summary) {
  if (!summary || typeof summary !== 'object') {
    return 0
  }

  const weeklyAdherenceFactor = toFiniteNumber(summary.weekly_adherence_factor)
  if (weeklyAdherenceFactor !== null) {
    return toConfidenceScore(weeklyAdherenceFactor)
  }

  const adherencePercentage = toFiniteNumber(summary.adherence_percentage)
  if (adherencePercentage === null) {
    return 0
  }

  const trackingCoverageFactor = toFiniteNumber(summary.tracking_coverage_factor)
  if (trackingCoverageFactor !== null && trackingCoverageFactor > 0) {
    return clampPercentage(adherencePercentage / trackingCoverageFactor)
  }

  const trackingCoveragePercentage = toFiniteNumber(summary.tracking_coverage_percentage)
  if (trackingCoveragePercentage !== null && trackingCoveragePercentage > 0) {
    return clampPercentage(adherencePercentage / (trackingCoveragePercentage / 100))
  }

  return clampPercentage(adherencePercentage)
}

export function resolveConfidencePercentage(summary) {
  if (!summary || typeof summary !== 'object') {
    return 0
  }

  const confidenceFactor = toFiniteNumber(summary.confidence_factor)
  if (confidenceFactor !== null) {
    return toConfidenceScore(confidenceFactor)
  }

  const weeklyAdherenceFactor = toFiniteNumber(summary.weekly_adherence_factor)
  const trackingCoverageFactor = toFiniteNumber(summary.tracking_coverage_factor)
  if (weeklyAdherenceFactor !== null && trackingCoverageFactor !== null) {
    return toConfidenceScore(weeklyAdherenceFactor * trackingCoverageFactor)
  }

  const confidencePercentage = toFiniteNumber(summary.confidence_percentage)
  if (confidencePercentage !== null) {
    return clampPercentage(confidencePercentage)
  }

  const adherencePercentage = toFiniteNumber(summary.adherence_percentage)
  if (adherencePercentage !== null) {
    return clampPercentage(adherencePercentage)
  }

  return 0
}
