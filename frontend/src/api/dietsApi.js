import { apiRequest } from './client'

const DIETS_BASE_PATH = '/diets'

export function generateDiet(token, payload) {
  return apiRequest(`${DIETS_BASE_PATH}/generate`, {
    method: 'POST',
    token,
    body: payload,
  })
}

export function getDietHistory(token) {
  return apiRequest(DIETS_BASE_PATH, {
    method: 'GET',
    token,
  })
}

export function getLatestDiet(token) {
  return apiRequest(`${DIETS_BASE_PATH}/latest`, {
    method: 'GET',
    token,
  })
}

export function getDietById(token, dietId) {
  return apiRequest(`${DIETS_BASE_PATH}/${dietId}`, {
    method: 'GET',
    token,
  })
}
