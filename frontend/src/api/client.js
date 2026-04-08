const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function getErrorMessage(data) {
  if (!data?.detail) {
    return 'Unexpected API error'
  }

  if (typeof data.detail === 'string') {
    return data.detail
  }

  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => item.msg).join('. ')
  }

  if (typeof data.detail === 'object') {
    return data.detail.message ?? JSON.stringify(data.detail)
  }

  return 'Unexpected API error'
}

export async function apiRequest(path, options = {}) {
  const { body, headers, token, ...rest } = options

  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = getErrorMessage(data)
    throw new Error(message)
  }

  return data
}
