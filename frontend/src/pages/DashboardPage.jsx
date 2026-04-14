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
    <section id="panel-dashboard" className="dashboard-scroll-section dashboard-page">
      <div className="section-heading">
        <span className="eyebrow">Dashboard principal</span>
        <h2>Resumen de progreso, adherencia y dieta</h2>
        <p>Esta vista centraliza el estado actual del atleta para entender rapido que esta pasando y que decisiones se han ido tomando.</p>
      </div>

      {isLoading ? <p className="info-note">Construyendo dashboard principal...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}

      {!isLoading && !error ? (
        <div className="dashboard-page-grid">
          <DashboardStats summary={overview?.summary ?? null} />
          <WeightProgressChart weightProgress={overview?.weight_progress ?? null} />
          <div className="dashboard-secondary-grid">
            <AdherenceSummaryChart adherence={overview?.adherence ?? null} />
            <ActiveDietOverview activeDiet={overview?.active_diet ?? null} />
          </div>
        </div>
      ) : null}
    </section>
  )
}

export default DashboardPage
