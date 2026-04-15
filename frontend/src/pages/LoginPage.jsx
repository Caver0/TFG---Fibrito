import { useState } from 'react'
import AuthCard from '../components/AuthCard'
import AuthShell from '../components/AuthShell'
import { useAuth } from '../context/AuthContext'

const initialForm = {
  email: '',
  password: '',
}

function LoginPage({ onSwitch }) {
  const { login } = useAuth()
  const [form, setForm] = useState(initialForm)
  const [error, setError] = useState('')
  const [infoMessage, setInfoMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  function handleChange(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setInfoMessage('')
    setIsSubmitting(true)

    try {
      await login(form)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleRecoverKey() {
    setError('')
    setInfoMessage('La recuperación de clave aún no está disponible en el servidor actual.')
  }

  return (
    <AuthShell>
      <AuthCard
        mode="login"
        title="Autorización Requerida"
        subtitle="Inicializa tu perfil de rendimiento para entrar al laboratorio."
        footer={(
          <p className="auth-switch-line">
            <span>¿Nuevo operativo?</span>{' '}
            <button type="button" className="auth-inline-link" onClick={onSwitch}>
              Comenzar Reclutamiento
            </button>
          </p>
        )}
      >
        <form className="auth-command-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>ID de Laboratorio (Email)</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                alternate_email
              </i>
              <input
                name="email"
                type="email"
                placeholder="usuario@laboratoriocinetico.io"
                autoComplete="email"
                value={form.email}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span className="auth-field-row">
              <span>Clave de Acceso Segura</span>
              <button type="button" className="auth-inline-link auth-inline-link-utility" onClick={handleRecoverKey}>
                Recuperar Clave
              </button>
            </span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                lock
              </i>
              <input
                name="password"
                type="password"
                placeholder="••••••••••••"
                autoComplete="current-password"
                value={form.password}
                onChange={handleChange}
                minLength={8}
                required
              />
            </div>
          </label>

          {error ? <p className="auth-feedback auth-feedback-error">{error}</p> : null}
          {infoMessage ? <p className="auth-feedback auth-feedback-info">{infoMessage}</p> : null}

          <button type="submit" className="auth-primary-button" disabled={isSubmitting}>
            <span>{isSubmitting ? 'Entrando al Laboratorio...' : 'Entrar al Laboratorio Cinético'}</span>
            <i className="material-symbols-outlined" aria-hidden="true">
              arrow_forward
            </i>
          </button>
        </form>
      </AuthCard>
    </AuthShell>
  )
}

export default LoginPage
