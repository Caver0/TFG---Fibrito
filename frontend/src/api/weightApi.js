import { apiRequest } from './client'

export function createWeightEntry(token, payload) {
  return apiRequest('/weight', {
    method: 'POST',
    token,
    body: payload,
  })
}

export function getWeightHistory(token) {
  return apiRequest('/weight', {
    method: 'GET',
    token,
  })
}

export function updateWeightEntry(token, entryId, payload) {
  return apiRequest(`/weight/${entryId}`, {
    method: 'PUT',
    token,
    body: payload,
  })
}

export function deleteWeightEntry(token, entryId) {
  return apiRequest(`/weight/${entryId}`, {
    method: 'DELETE',
    token,
  })
}

export function getProgressSummary(token) {
  return apiRequest('/weight/summary', {
    method: 'GET',
    token,
  })
}
