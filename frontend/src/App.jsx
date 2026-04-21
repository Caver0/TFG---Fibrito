import { useEffect, useState } from 'react'
import './App.css'
import AppShell from './components/AppShell'
import { useAuth } from './context/AuthContext'
import DashboardPage from './pages/DashboardPage'
import DietsPage from './pages/DietsPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import LoginPage from './pages/LoginPage'
import OnboardingPage from './pages/OnboardingPage'
import ProfilePage from './pages/ProfilePage'
import ProgressPage from './pages/ProgressPage'
import RegisterPage from './pages/RegisterPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import { replacePublicAuthState, getPublicAuthState } from './utils/authLocation'
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
    topbarTitle: 'GESTION DE DIETAS',
    getTopbarContext: () => formatDateLabel(new Date(), { month: 'long' }).toUpperCase(),
  },
  {
    id: 'progress',
    sidebarLabel: 'Progreso',
    icon: 'insights',
    topbarTitle: 'PROGRESO Y ADHERENCIA',
    getTopbarContext: () => 'FIABILIDAD Y TENDENCIA DEL PESO',
  },
  {
    id: 'profile',
    sidebarLabel: 'Perfil',
    icon: 'person',
    topbarTitle: 'PREFERENCIAS DE USUARIO',
    getTopbarContext: () => 'ESTADO ACTUAL',
  },
]

function resolveActiveViewFromHash() {
  if (typeof window === 'undefined') {
    return APP_VIEWS[0].id
  }

  const currentHash = window.location.hash.replace('#', '')
  const knownView = APP_VIEWS.find((view) => view.id === currentHash)
  return knownView?.id ?? APP_VIEWS[0].id
}

function App() {
  const { isAuthenticated, isReady, logout, user } = useAuth()
  const [publicAuthState, setPublicAuthState] = useState(getPublicAuthState)
  const [activeView, setActiveView] = useState(resolveActiveViewFromHash)

  useEffect(() => {
    function handleLocationChange() {
      setPublicAuthState(getPublicAuthState())
      setActiveView(resolveActiveViewFromHash())
    }

    window.addEventListener('hashchange', handleLocationChange)
    window.addEventListener('popstate', handleLocationChange)
    handleLocationChange()

    return () => {
      window.removeEventListener('hashchange', handleLocationChange)
      window.removeEventListener('popstate', handleLocationChange)
    }
  }, [])

  useEffect(() => {
    if (!isAuthenticated || publicAuthState.view === 'reset-password') {
      return
    }

    replacePublicAuthState('login')
    setPublicAuthState({
      view: 'login',
      resetToken: '',
    })
  }, [isAuthenticated, publicAuthState.view])

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

  function handleAuthViewChange(view, options = {}) {
    const nextState = {
      view,
      resetToken: options.resetToken ?? '',
    }

    setPublicAuthState(nextState)
    replacePublicAuthState(view, nextState.resetToken)

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

  if (publicAuthState.view === 'reset-password') {
    return (
      <ResetPasswordPage
        token={publicAuthState.resetToken}
        onBackToLogin={() => handleAuthViewChange('login')}
      />
    )
  }

  if (!isAuthenticated) {
    if (publicAuthState.view === 'register') {
      return <RegisterPage onSwitch={() => handleAuthViewChange('login')} />
    }

    if (publicAuthState.view === 'forgot-password') {
      return <ForgotPasswordPage onBackToLogin={() => handleAuthViewChange('login')} />
    }

    return (
      <LoginPage
        onRecoverPassword={() => handleAuthViewChange('forgot-password')}
        onSwitch={() => handleAuthViewChange('register')}
      />
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
