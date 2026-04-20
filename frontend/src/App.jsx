import { useEffect, useState } from 'react'
import './App.css'
import AppShell from './components/AppShell'
import { useAuth } from './context/AuthContext'
import DashboardPage from './pages/DashboardPage'
import DietsPage from './pages/DietsPage'
import LoginPage from './pages/LoginPage'
import OnboardingPage from './pages/OnboardingPage'
import ProfilePage from './pages/ProfilePage'
import ProgressPage from './pages/ProgressPage'
import RegisterPage from './pages/RegisterPage'
import { formatDateLabel, formatGoalPhase } from './utils/stitch'

const APP_VIEWS = [
  {
    id: 'dashboard',
    sidebarLabel: 'Panel',
    icon: 'dashboard',
    topbarTitle: 'PANEL',
    getTopbarContext: (user) => formatGoalPhase(user?.goal),
  },
  {
    id: 'diets',
    sidebarLabel: 'Dietas',
    icon: 'restaurant',
    topbarTitle: 'GESTIÓN DE DIETAS',
    getTopbarContext: () => formatDateLabel(new Date(), { month: 'long' }).toUpperCase(),
  },
  {
    id: 'progress',
    sidebarLabel: 'Progreso',
    icon: 'insights',
    topbarTitle: 'ANÁLISIS DE ADHERENCIA',
    getTopbarContext: () => 'FIABILIDAD DEL SISTEMA Y TENDENCIA DE PESO',
  },
  {
    id: 'profile',
    sidebarLabel: 'Perfil',
    icon: 'person',
    topbarTitle: 'PREFERENCIAS DE USUARIO',
    getTopbarContext: () => 'ESTADO ACTUAL',
  },
]

function getInitialView() {
  if (typeof window === 'undefined') {
    return APP_VIEWS[0].id
  }

  const currentHash = window.location.hash.replace('#', '')
  const knownView = APP_VIEWS.find((view) => view.id === currentHash)
  return knownView?.id ?? APP_VIEWS[0].id
}

function App() {
  const { isAuthenticated, isReady, logout, user } = useAuth()
  const [authView, setAuthView] = useState('login')
  const [activeView, setActiveView] = useState(getInitialView)

  useEffect(() => {
    function handleHashChange() {
      const currentHash = window.location.hash.replace('#', '')
      const knownView = APP_VIEWS.find((view) => view.id === currentHash)
      setActiveView(knownView?.id ?? APP_VIEWS[0].id)
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

  const currentView = APP_VIEWS.find((view) => view.id === activeView) ?? APP_VIEWS[0]
  const viewMeta = {
    ...currentView,
    topbarContext: currentView.getTopbarContext(user),
    phaseLabel: formatGoalPhase(user?.goal),
  }

  if (!isReady) {
    return (
      <main className="app-loading-screen">
        <div className="lab-frame auth-lab-frame app-loading-frame">
          <p>Inicializando FIBRIT0...</p>
        </div>
      </main>
    )
  }

  if (!isAuthenticated) {
    return authView === 'login' ? (
      <LoginPage onSwitch={() => setAuthView('register')} />
    ) : (
      <RegisterPage onSwitch={() => setAuthView('login')} />
    )
  }

  if (!user?.goal) {
    return <OnboardingPage />
  }

  return (
    <AppShell
      activeView={activeView}
      onNavigate={handleNavigate}
      onLogout={logout}
      user={user}
      views={APP_VIEWS}
      viewMeta={viewMeta}
    >
      <section hidden={activeView !== 'dashboard'}>
        <DashboardPage />
      </section>

      <section hidden={activeView !== 'diets'}>
        <DietsPage />
      </section>

      <section hidden={activeView !== 'progress'}>
        <ProgressPage />
      </section>

      <section hidden={activeView !== 'profile'}>
        <ProfilePage />
      </section>
    </AppShell>
  )
}

export default App
