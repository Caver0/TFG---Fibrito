import { apiRequest } from './client'

const FOODS_BASE_PATH = '/foods'

export function searchFoods(token, query, options = {}) {
  const searchParams = new URLSearchParams({
    q: query,
    ...(options.limit ? { limit: String(options.limit) } : {}),
    ...(options.includeExternal ? { include_external: 'true' } : {}),
  })

  return apiRequest(`${FOODS_BASE_PATH}/search?${searchParams.toString()}`, {
    method: 'GET',
    token,
  })
}

export function getFoodCatalogStatus(token) {
  return apiRequest(`${FOODS_BASE_PATH}/catalog/status`, {
    method: 'GET',
    token,
  })
}
