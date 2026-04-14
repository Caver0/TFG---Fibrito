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
    setInfoMessage('Recover Key is not available in the current backend yet.')
  }

  return (
    <AuthShell>
      <AuthCard
        mode="login"
        title="Authorization Required"
        subtitle="Initialize your performance profile to enter the lab."
        footer={(
          <p className="auth-switch-line">
            <span>New operative?</span>{' '}
            <button type="button" className="auth-inline-link" onClick={onSwitch}>
              Begin Recruitment
            </button>
          </p>
        )}
      >
        <form className="auth-command-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Laboratory ID (Email)</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                alternate_email
              </i>
              <input
                name="email"
                type="email"
                placeholder="user@kineticlab.io"
                autoComplete="email"
                value={form.email}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span className="auth-field-row">
              <span>Secure Access Key</span>
              <button type="button" className="auth-inline-link auth-inline-link-utility" onClick={handleRecoverKey}>
                Recover Key
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
            <span>{isSubmitting ? 'Entering The Lab...' : 'Enter The Kinetic Lab'}</span>
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
