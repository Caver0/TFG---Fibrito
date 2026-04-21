import { apiRequest } from './client'

const DIETS_BASE_PATH = '/diets'

export function generateDiet(token, payload) {
  return apiRequest(`${DIETS_BASE_PATH}/generate`, {
    method: 'POST',
    token,
    body: payload,
  })
}

export function createManualDiet(token, payload) {
  return apiRequest(`${DIETS_BASE_PATH}/manual`, {
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

export function activateDiet(token, dietId) {
  return apiRequest(`${DIETS_BASE_PATH}/${dietId}/activate`, {
    method: 'POST',
    token,
  })
}

export function regenerateMeal(token, dietId, mealNumber) {
  return apiRequest(`${DIETS_BASE_PATH}/${dietId}/meals/${mealNumber}/regenerate`, {
    method: 'POST',
    token,
  })
}

export function replaceFoodInMeal(token, dietId, mealNumber, payload) {
  return apiRequest(`${DIETS_BASE_PATH}/${dietId}/meals/${mealNumber}/replace-food`, {
    method: 'POST',
    token,
    body: payload,
  })
}

export function getFoodReplacementOptions(token, dietId, mealNumber, payload) {
  return apiRequest(`${DIETS_BASE_PATH}/${dietId}/meals/${mealNumber}/replacement-options`, {
    method: 'POST',
    token,
    body: payload,
  })
}

export function searchReplacementFood(token, dietId, mealNumber, payload) {
  return apiRequest(`${DIETS_BASE_PATH}/${dietId}/meals/${mealNumber}/search-replacement-food`, {
    method: 'POST',
    token,
    body: payload,
  })
}
