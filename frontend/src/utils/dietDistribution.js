export const DEFAULT_DISTRIBUTION_TEMPLATES = {
  3: [30, 40, 30],
  4: [25, 15, 35, 25],
  5: [20, 10, 30, 15, 25],
  6: [20, 10, 25, 10, 15, 20],
}

export const TRAINING_TIME_OPTIONS = [
  { value: 'manana', label: 'Manana' },
  { value: 'mediodia', label: 'Mediodia' },
  { value: 'tarde', label: 'Tarde' },
  { value: 'noche', label: 'Noche' },
]

export function getDefaultDistributionTemplate(mealsCount) {
  return [...(DEFAULT_DISTRIBUTION_TEMPLATES[Number(mealsCount)] ?? [])]
}

export function getDistributionSum(percentages) {
  return percentages.reduce((sum, value) => {
    const parsedValue = Number(value)
    if (!Number.isFinite(parsedValue)) {
      return sum
    }

    return sum + parsedValue
  }, 0)
}

export function validateDistribution(percentages, mealsCount) {
  if (percentages.length !== Number(mealsCount)) {
    return {
      isValid: false,
      message: 'La distribucion debe tener exactamente una entrada por comida.',
      sum: getDistributionSum(percentages),
    }
  }

  if (percentages.some((value) => value === '' || !Number.isFinite(Number(value)) || Number(value) <= 0)) {
    return {
      isValid: false,
      message: 'Todos los porcentajes deben ser mayores que 0.',
      sum: getDistributionSum(percentages),
    }
  }

  const sum = getDistributionSum(percentages)
  if (Math.abs(sum - 100) > 0.001) {
    return {
      isValid: false,
      message: 'La suma de porcentajes debe ser exactamente 100.',
      sum,
    }
  }

  return {
    isValid: true,
    message: '',
    sum,
  }
}

export function formatTrainingTimeOfDay(value) {
  const option = TRAINING_TIME_OPTIONS.find((item) => item.value === value)
  return option?.label ?? 'No indicado'
}
