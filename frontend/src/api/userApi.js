import { apiRequest } from './client'

export function getCurrentUser(token) {
  return apiRequest('/users/me', {
    method: 'GET',
    token,
  })
}

export function updateNutritionProfile(token, payload) {
  return apiRequest('/users/me/profile', {
    method: 'PUT',
    token,
    body: payload,
  })
}

export function getFoodPreferences(token) {
  return apiRequest('/users/me/preferences', {
    method: 'GET',
    token,
  })
}

export function updateFoodPreferences(token, payload) {
  return apiRequest('/users/me/preferences', {
    method: 'PUT',
    token,
    body: payload,
  })
}

export function getNutritionSummary(token) {
  return apiRequest('/users/me/nutrition', {
    method: 'GET',
    token,
  })
}
