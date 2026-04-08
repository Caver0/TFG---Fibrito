import { apiRequest } from './client'

export function getWeeklyAverages(token) {
  return apiRequest('/progress/weekly-averages', {
    method: 'GET',
    token,
  })
}

export function getWeeklyAnalysis(token) {
  return apiRequest('/progress/weekly-analysis', {
    method: 'GET',
    token,
  })
}

export function applyWeeklyAdjustment(token) {
  return apiRequest('/progress/apply-weekly-adjustment', {
    method: 'POST',
    token,
  })
}

export function getAdjustmentHistory(token) {
  return apiRequest('/progress/adjustments', {
    method: 'GET',
    token,
  })
}
