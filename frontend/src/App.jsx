import { useEffect, useState } from 'react'
import DietsPage from './pages/DietsPage'
import DashboardPage from './pages/DashboardPage'
import ProfilePage from './pages/ProfilePage'
import ProgressPage from './pages/ProgressPage'
import SidebarMenu from './components/SidebarMenu'
import { useAuth } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import './App.css'

const APP_VIEWS = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    eyebrow: 'Centro de control',
    heading: 'Vision general del atleta',
    description: 'Concentra progreso, adherencia y dieta activa en una vista mas clara, amplia y facil de recorrer.',
    note: 'Resumen premium del estado actual',
  },
  {
    id: 'diets',
    label: 'Dietas',
    eyebrow: 'Plan diario',
    heading: 'Dietas, comidas y adherencia',
    description: 'Trabaja la generacion de dieta y el seguimiento diario en bloques independientes con mejor jerarquia visual.',
    note: 'Planificacion y ejecucion del dia',
  },
  {
    id: 'progress',
    label: 'Progreso',
    eyebrow: 'Seguimiento corporal',
    heading: 'Registros, medias y analisis semanal',
    description: 'Consulta el historial, la lectura semanal y los ajustes guardados sin perder el contexto de cada bloque.',
    note: 'Lectura de tendencia y ajustes',
  },
  {
    id: 'profile',
    label: 'Perfil',
    eyebrow: 'Base nutricional',
    heading: 'Perfil y preferencias alimentarias',
    description: 'Ordena tus datos base, objetivos y filtros de alimentos en una vista limpia y consistente.',
    note: 'Configuracion del atleta',
  },
]

function getInitialView() {
  if (typeof window === 'undefined') {
    return APP_VIEWS[0].id
  }

  const hashValue = window.location.hash.replace('#', '')
  return APP_VIEWS.some((view) => view.id === hashValue)
    ? hashValue
    : APP_VIEWS[0].id
}

function formatGoalLabel(goal) {
  if (goal === 'perder_grasa') {
    return 'Perder grasa'
  }
  if (goal === 'mantener_peso') {
    return 'Mantener peso'
  }
  if (goal === 'ganar_masa') {
    return 'Ganar masa'
  }
  return 'Completa el perfil'
}

function App() {
  const { isAuthenticated, isReady, logout, user } = useAuth()
  const [authView, setAuthView] = useState('login')
  const [activeView, setActiveView] = useState(getInitialView)

  useEffect(() => {
    function handleHashChange() {
      const hashValue = window.location.hash.replace('#', '')
      const nextView = APP_VIEWS.find((view) => view.id === hashValue)?.id ?? APP_VIEWS[0].id
      setActiveView(nextView)
    }

    window.addEventListener('hashchange', handleHashChange)
    handleHashChange()

    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  function handleNavigate(viewId) {
    if (!APP_VIEWS.some((view) => view.id === viewId)) {
      return
    }

    setActiveView(viewId)

    if (window.location.hash !== `#${viewId}`) {
      window.history.replaceState(null, '', `#${viewId}`)
    }

    window.scrollTo({
      top: 0,
      behavior: 'smooth',
    })
  }

  const activeViewMeta = APP_VIEWS.find((view) => view.id === activeView) ?? APP_VIEWS[0]

  if (!isReady) {
    return (
      <main className="app-shell app-shell-auth">
        <section className="card auth-stage">
          <p>Cargando sesion...</p>
        </section>
      </main>
    )
  }

  if (!isAuthenticated) {
    return (
      <main className="app-shell app-shell-auth">
        <section className="auth-stage">
          {authView === 'login' ? (
            <LoginPage onSwitch={() => setAuthView('register')} />
          ) : (
            <RegisterPage onSwitch={() => setAuthView('login')} />
          )}
        </section>
      </main>
    )
  }

  return (
    <main className="app-shell app-shell-wide">
      <div className="app-frame">
        <SidebarMenu
          activeView={activeView}
          onLogout={logout}
          onNavigate={handleNavigate}
          user={user}
          views={APP_VIEWS}
        />

        <section className="app-content">
          <header className="app-toolbar">
            <div className="app-toolbar-copy">
              <span className="eyebrow">{activeViewMeta.eyebrow}</span>
              <h1>{activeViewMeta.heading}</h1>
              <p>{activeViewMeta.description}</p>
            </div>

            <div className="app-toolbar-meta">
              <article className="app-toolbar-stat">
                <span>Perfil activo</span>
                <strong>{user.name}</strong>
                <small>{user.email}</small>
              </article>

              <article className="app-toolbar-stat">
                <span>Vista actual</span>
                <strong>{activeViewMeta.label}</strong>
                <small>{activeViewMeta.note}</small>
              </article>

              <article className="app-toolbar-stat">
                <span>Objetivo</span>
                <strong>{formatGoalLabel(user.goal)}</strong>
                <small>
                  {user.target_calories
                    ? `${Math.round(Number(user.target_calories))} kcal objetivo`
                    : 'Completa tu perfil nutricional'}
                </small>
              </article>
            </div>
          </header>

          <div className="page-view-stack">
            <section className="page-view" hidden={activeView !== 'dashboard'}>
              <DashboardPage />
            </section>

            <section className="page-view" hidden={activeView !== 'diets'}>
              <DietsPage />
            </section>

            <section className="page-view" hidden={activeView !== 'progress'}>
              <ProgressPage />
            </section>

            <section className="page-view" hidden={activeView !== 'profile'}>
              <ProfilePage />
            </section>
          </div>
        </section>
      </div>
    </main>
  )
}

export default App

