import { createContext, useContext, useEffect, useState } from 'react'
import * as authApi from '../api/authApi'
import * as userApi from '../api/userApi'

const AUTH_STORAGE_KEY = 'fibrito-auth'
const AuthContext = createContext(null)

function readStoredSession() {
  const rawSession = window.localStorage.getItem(AUTH_STORAGE_KEY)
  if (!rawSession) {
    return { token: '', user: null }
  }

  try {
    return JSON.parse(rawSession)
  } catch {
    window.localStorage.removeItem(AUTH_STORAGE_KEY)
    return { token: '', user: null }
  }
}

export function AuthProvider({ children }) {
  const storedSession = readStoredSession()
  const [token, setToken] = useState(storedSession.token ?? '')
  const [user, setUser] = useState(storedSession.user ?? null)
  const [isReady, setIsReady] = useState(false)

  function clearSession() {
    setToken('')
    setUser(null)
    window.localStorage.removeItem(AUTH_STORAGE_KEY)
  }

  async function refreshUser(activeToken = token) {
    if (!activeToken) {
      return null
    }

    const currentUser = await userApi.getCurrentUser(activeToken)
    setUser(currentUser)
    return currentUser
  }

  function replaceUser(nextUser) {
    setUser(nextUser)
    return nextUser
  }

  useEffect(() => {
    if (!token) {
      setIsReady(true)
      return
    }

    let isMounted = true

    refreshUser(token)
      .catch(() => {
        if (!isMounted) {
          return
        }

        clearSession()
      })
      .finally(() => {
        if (isMounted) {
          setIsReady(true)
        }
      })

    return () => {
      isMounted = false
    }
  }, [token])

  useEffect(() => {
    if (!token || !user) {
      window.localStorage.removeItem(AUTH_STORAGE_KEY)
      return
    }

    window.localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ token, user }),
    )
  }, [token, user])

  async function handleLogin(credentials) {
    const session = await authApi.login(credentials)
    setToken(session.access_token)
    setUser(session.user)
    return session.user
  }

  async function handleRegister(payload) {
    await authApi.register(payload)
    return handleLogin({
      email: payload.email,
      password: payload.password,
    })
  }

  function handleLogout() {
    clearSession()
  }

  const value = {
    token,
    user,
    isAuthenticated: Boolean(token && user),
    isReady,
    login: handleLogin,
    register: handleRegister,
    logout: handleLogout,
    refreshUser,
    replaceUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  return context
}
