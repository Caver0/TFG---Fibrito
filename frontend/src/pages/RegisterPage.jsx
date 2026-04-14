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
        title="Recruitment Protocol"
        subtitle="Create a live operative profile connected to the FIBRIT0 backend."
        footer={(
          <p className="auth-switch-line">
            <span>Already authorized?</span>{' '}
            <button type="button" className="auth-inline-link" onClick={onSwitch}>
              Return To Access Gate
            </button>
          </p>
        )}
      >
        <form className="auth-command-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Operative Name</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                badge
              </i>
              <input
                name="name"
                type="text"
                placeholder="Athlete designation"
                autoComplete="name"
                value={form.name}
                onChange={handleChange}
                required
              />
            </div>
          </label>

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
            <span>Secure Access Key</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                lock
              </i>
              <input
                name="password"
                type="password"
                placeholder="Minimum 8 characters"
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
            <span>{isSubmitting ? 'Recruiting Operative...' : 'Initiate Recruitment'}</span>
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
