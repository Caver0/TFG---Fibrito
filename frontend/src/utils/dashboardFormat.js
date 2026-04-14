export function formatWeight(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  return `${Number(value).toFixed(2)} kg`
}

export function formatSignedWeight(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  const numericValue = Number(value)
  const prefix = numericValue > 0 ? '+' : ''
  return `${prefix}${numericValue.toFixed(2)} kg`
}

export function formatCalories(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  return `${Math.round(Number(value))} kcal`
}

export function formatSignedCalories(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  const numericValue = Math.round(Number(value))
  const prefix = numericValue > 0 ? '+' : ''
  return `${prefix}${numericValue} kcal`
}

export function formatMacro(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  return `${Number(value).toFixed(1)} g`
}

export function formatPercentage(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  return `${Number(value).toFixed(1)}%`
}

export function formatFactor(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  return Number(value).toFixed(2)
}

export function formatGoal(goal) {
  if (goal === 'perder_grasa') {
    return 'Perder grasa'
  }
  if (goal === 'ganar_masa') {
    return 'Ganar masa'
  }
  if (goal === 'mantener_peso') {
    return 'Mantener peso'
  }
  return 'Sin objetivo'
}

export function formatShortDate(value) {
  if (!value) {
    return 'Sin fecha'
  }

  const parsedDate = new Date(value)
  if (Number.isNaN(parsedDate.getTime())) {
    return 'Sin fecha'
  }

  return new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: 'short',
  }).format(parsedDate)
}

export function formatLongDate(value) {
  if (!value) {
    return 'Sin fecha'
  }

  const parsedDate = new Date(value)
  if (Number.isNaN(parsedDate.getTime())) {
    return 'Sin fecha'
  }

  return new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  }).format(parsedDate)
}
