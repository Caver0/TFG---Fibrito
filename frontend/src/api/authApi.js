import { apiRequest } from './client'

export function register(payload) {
  return apiRequest('/auth/register', {
    method: 'POST',
    body: payload,
  })
}

export function login(payload) {
  return apiRequest('/auth/login', {
    method: 'POST',
    body: payload,
  })
}

export function getCurrentUser(token) {
  return apiRequest('/users/me', {
    method: 'GET',
    token,
  })
}
