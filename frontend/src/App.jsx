import { useState } from 'react'
import { useAuth } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'

function App() {
  const { isAuthenticated, isReady, logout, user } = useAuth()
  const [authView, setAuthView] = useState('login')

  if (!isReady) {
    return (
      <main className="app-shell">
        <section className="card">
          <p>Cargando sesión...</p>
        </section>
      </main>
    )
  }

  if (!isAuthenticated) {
    return (
      <main className="app-shell">
        {authView === 'login' ? (
          <LoginPage onSwitch={() => setAuthView('register')} />
        ) : (
          <RegisterPage onSwitch={() => setAuthView('login')} />
        )}
      </main>
    )
  }

  return (
    <main className="app-shell">
      <section className="card profile-card">
        <span className="eyebrow">Sesión activa</span>
        <h1>Bienvenido a Fibrito</h1>
        <p className="profile-name">{user.name}</p>
        <p className="profile-email">{user.email}</p>
        <div className="profile-grid">
          <div>
            <span className="profile-label">Objetivo</span>
            <strong>{user.goal || 'Pendiente'}</strong>
          </div>
          <div>
            <span className="profile-label">Actividad</span>
            <strong>{user.activity_level || 'Pendiente'}</strong>
          </div>
        </div>
        <button type="button" onClick={logout}>
          Cerrar sesión
        </button>
      </section>
    </main>
  )
}

export default App
