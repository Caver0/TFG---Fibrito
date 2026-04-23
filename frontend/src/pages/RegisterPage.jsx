import { useState } from 'react'
import AuthCard from '../components/AuthCard'
import AuthShell from '../components/AuthShell'
import { useAuth } from '../context/AuthContext'

const initialForm = {
  name: '',
  email: '',
  password: '',
}

function RegisterPage({ onSwitch }) {
  const { register } = useAuth()
  const [form, setForm] = useState(initialForm)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  function handleChange(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      await register(form)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell>
      <AuthCard
        mode="register"
        title="Protocolo de Reclutamiento"
        subtitle="Crea un perfil de operativo en vivo conectado al sistema FIBRIT0."
        footer={(
          <p className="auth-switch-line">
            <span>Ya estas autorizado?</span>{' '}
            <button type="button" className="auth-inline-link" onClick={onSwitch}>
              Volver a la Puerta de Acceso
            </button>
          </p>
        )}
      >
        <form className="auth-command-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Nombre de Operativo</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                badge
              </i>
              <input
                name="name"
                type="text"
                placeholder="Designacion de atleta"
                autoComplete="name"
                value={form.name}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span>ID de Laboratorio (Email)</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                alternate_email
              </i>
              <input
                name="email"
                type="email"
                placeholder="usuario@email.com"
                autoComplete="email"
                value={form.email}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span>Clave de Acceso Segura</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                lock
              </i>
              <input
                name="password"
                type="password"
                placeholder="Minimo 8 caracteres"
                autoComplete="new-password"
                value={form.password}
                onChange={handleChange}
                minLength={8}
                required
              />
            </div>
          </label>

          {error ? <p className="auth-feedback auth-feedback-error">{error}</p> : null}

          <button type="submit" className="auth-primary-button" disabled={isSubmitting}>
            <span>{isSubmitting ? 'Reclutando Operativo...' : 'Iniciar Reclutamiento'}</span>
            <i className="material-symbols-outlined" aria-hidden="true">
              arrow_forward
            </i>
          </button>
        </form>
      </AuthCard>
    </AuthShell>
  )
}

export default RegisterPage
