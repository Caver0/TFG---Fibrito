import { apiRequest } from './client'

export function getDashboardOverview(token) {
  return apiRequest('/dashboard/overview', {
    method: 'GET',
    token,
  })
}
