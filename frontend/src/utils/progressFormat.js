export function formatProgressMetric(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Sin datos'
  }

  return Number(value).toFixed(2)
}

export function formatDirectionStatus(value) {
  if (value === null || value === undefined) {
    return 'Sin datos'
  }

  return value ? 'Correcta' : 'No correcta'
}

export function formatRateStatus(value) {
  if (value === null || value === undefined) {
    return 'Sin datos'
  }

  return value ? 'Dentro del rango' : 'Fuera de rango'
}
