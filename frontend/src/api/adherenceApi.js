import { apiRequest } from './client'

const ADHERENCE_BASE_PATH = '/adherence'

function buildQueryString(params) {
  const searchParams = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, value)
    }
  })

  const queryString = searchParams.toString()
  return queryString ? `?${queryString}` : ''
}

export function saveMealAdherence(token, payload) {
  return apiRequest(`${ADHERENCE_BASE_PATH}/meals`, {
    method: 'POST',
    token,
    body: payload,
  })
}

export function getDietAdherence(token, dietId, dateValue) {
  return apiRequest(
    `${ADHERENCE_BASE_PATH}/diets/${dietId}${buildQueryString({ date: dateValue })}`,
    {
      method: 'GET',
      token,
    },
  )
}

export function getDailyAdherenceSummary(token, params = {}) {
  return apiRequest(`${ADHERENCE_BASE_PATH}/daily-summary${buildQueryString(params)}`, {
    method: 'GET',
    token,
  })
}

export function getWeeklyAdherenceSummary(token, params = {}) {
  return apiRequest(`${ADHERENCE_BASE_PATH}/weekly-summary${buildQueryString(params)}`, {
    method: 'GET',
    token,
  })
}
