import { useEffect, useState } from 'react'
import * as dashboardApi from '../api/dashboardApi'
import ActiveDietOverview from '../components/ActiveDietOverview'
import AdherenceSummaryChart from '../components/AdherenceSummaryChart'
import DashboardStats from '../components/DashboardStats'
import WeightProgressChart from '../components/WeightProgressChart'
import { useAuth } from '../context/AuthContext'

function DashboardPage() {
  const { token } = useAuth()
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function loadOverview(activeToken = token) {
    if (!activeToken) {
      return null
    }

    setIsLoading(true)
    setError('')

    try {
      const response = await dashboardApi.getDashboardOverview(activeToken)
      setOverview(response)
      return response
    } catch (loadError) {
      setOverview(null)
      setError(loadError.message)
      return null
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!token) {
      return
    }

    loadOverview(token)
  }, [token])

  useEffect(() => {
    if (!token) {
      return undefined
    }

    function handleDashboardRefresh() {
      loadOverview(token)
    }

    window.addEventListener('dashboard:refresh', handleDashboardRefresh)
    window.addEventListener('adherence:updated', handleDashboardRefresh)

    return () => {
      window.removeEventListener('dashboard:refresh', handleDashboardRefresh)
      window.removeEventListener('adherence:updated', handleDashboardRefresh)
    }
  }, [token])

  return (
    <section className="page-shell dashboard-page">
      <header className="page-header">
        <div className="page-header-copy">
          <span className="eyebrow">Dashboard principal</span>
          <h2>Resumen de progreso, adherencia y dieta</h2>
          <p>Una vista de alto nivel para leer rapido el estado actual del atleta, detectar senales clave y entender el plan vigente.</p>
        </div>

        <div className="page-header-note">
          <strong>Vista prioritaria</strong>
          <span>Metricas clave arriba, progreso en el foco principal y bloques de apoyo a la derecha.</span>
        </div>
      </header>

      {isLoading ? <p className="info-note">Construyendo dashboard principal...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}

      {!isLoading && !error ? (
        <div className="dashboard-page-layout">
          <DashboardStats summary={overview?.summary ?? null} />

          <div className="dashboard-main-grid">
            <WeightProgressChart weightProgress={overview?.weight_progress ?? null} />

            <div className="dashboard-side-column">
              <AdherenceSummaryChart adherence={overview?.adherence ?? null} />
              <ActiveDietOverview activeDiet={overview?.active_diet ?? null} />
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

export default DashboardPage
