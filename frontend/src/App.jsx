import { useState } from 'react'
import ProfilePage from './pages/ProfilePage'
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
          <p>Cargando sesion...</p>
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
    <main className="app-shell app-shell-wide">
      <section className="card dashboard-card">
        <div className="dashboard-header">
          <div>
            <span className="eyebrow">Sesion activa</span>
            <h1>Perfil de {user.name}</h1>
            <p className="profile-email">{user.email}</p>
          </div>

          <button type="button" className="secondary-button" onClick={logout}>
            Cerrar sesion
          </button>
        </div>

        <ProfilePage />
      </section>
    </main>
  )
}

export default App
