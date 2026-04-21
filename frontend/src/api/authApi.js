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

export function forgotPassword(payload) {
  return apiRequest('/auth/forgot-password', {
    method: 'POST',
    body: payload,
  })
}

export function validateResetPasswordToken(payload) {
  return apiRequest('/auth/reset-password/validate', {
    method: 'POST',
    body: payload,
  })
}

export function resetPassword(payload) {
  return apiRequest('/auth/reset-password', {
    method: 'POST',
    body: payload,
  })
}
