import { apiRequest } from './client'

export function generateDiet(token, payload) {
  return apiRequest('/diets/generate', {
    method: 'POST',
    token,
    body: payload,
  })
}

export function getDietHistory(token) {
  return apiRequest('/diets', {
    method: 'GET',
    token,
  })
}

export function getLatestDiet(token) {
  return apiRequest('/diets/latest', {
    method: 'GET',
    token,
  })
}

export function getDietById(token, dietId) {
  return apiRequest(`/diets/${dietId}`, {
    method: 'GET',
    token,
  })
}
