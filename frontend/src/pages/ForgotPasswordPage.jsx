import { useState } from 'react'
import AuthCard from '../components/AuthCard'
import AuthShell from '../components/AuthShell'
import { useAuth } from '../context/AuthContext'

function ForgotPasswordPage({ onBackToLogin }) {
  const { requestPasswordReset } = useAuth()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSuccessMessage('')
    setIsSubmitting(true)

    try {
      const response = await requestPasswordReset({ email })
      setSuccessMessage(response.message)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell>
      <AuthCard
        mode="login"
        title="Recuperar contrasena"
        subtitle="Te enviaremos un enlace temporal para restablecer el acceso a tu cuenta."
        footer={(
          <p className="auth-switch-line">
            <span>Recuerdas tu clave?</span>{' '}
            <button type="button" className="auth-inline-link" onClick={onBackToLogin}>
              Volver al acceso
            </button>
          </p>
        )}
      >
        <form className="auth-command-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Email</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                alternate_email
              </i>
              <input
                name="email"
                type="email"
                placeholder="usuario@email.com"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
          </label>

          <p className="auth-note">
            Si el correo existe en Fibrito, recibiras un enlace valido solo durante unos minutos.
          </p>

          {error ? <p className="auth-feedback auth-feedback-error">{error}</p> : null}
          {successMessage ? <p className="auth-feedback auth-feedback-info">{successMessage}</p> : null}

          <button type="submit" className="auth-primary-button" disabled={isSubmitting}>
            <span>{isSubmitting ? 'Enviando enlace...' : 'Enviar enlace de recuperacion'}</span>
            <i className="material-symbols-outlined" aria-hidden="true">
              mail
            </i>
          </button>

          <button type="button" className="auth-secondary-button" onClick={onBackToLogin}>
            Volver a iniciar sesion
          </button>
        </form>
      </AuthCard>
    </AuthShell>
  )
}

export default ForgotPasswordPage
