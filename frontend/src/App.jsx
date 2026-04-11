import { useState } from 'react'
import DietsPage from './pages/DietsPage'
import ProfilePage from './pages/ProfilePage'
import ProgressPage from './pages/ProgressPage'
import SidebarMenu from './components/SidebarMenu'
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
      <div className="dashboard-layout">
        <SidebarMenu onLogout={logout} />

        <section className="card dashboard-card">
          <div className="dashboard-header">
            <div>
              <span className="eyebrow">Sesion activa</span>
              <h1>Perfil de {user.name}</h1>
              <p className="profile-email">{user.email}</p>
              <p className="profile-email">Planifica nutricion, progreso y dieta diaria por alimentos en un mismo panel.</p>
            </div>
          </div>

          <section id="panel-perfil" className="dashboard-scroll-section">
            <ProfilePage />
          </section>

          <ProgressPage />

          <section id="panel-generar-dietas" className="dashboard-scroll-section">
            <DietsPage />
          </section>
        </section>
      </div>
    </main>
  )
}

export default App

