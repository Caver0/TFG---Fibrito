const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

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
    const message = data?.detail ?? 'Unexpected API error'
    throw new Error(message)
  }

  return data
}
