import { useEffect, useState } from 'react'
import AuthCard from '../components/AuthCard'
import AuthShell from '../components/AuthShell'
import { useAuth } from '../context/AuthContext'

const initialForm = {
  newPassword: '',
  confirmPassword: '',
}

const INVALID_LINK_MESSAGE = 'Enlace invalido o expirado.'

function ResetPasswordPage({ token, onBackToLogin }) {
  const { resetPassword, validatePasswordResetToken } = useAuth()
  const [form, setForm] = useState(initialForm)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isValidating, setIsValidating] = useState(true)
  const [isTokenValid, setIsTokenValid] = useState(false)
  const [hasCompletedReset, setHasCompletedReset] = useState(false)

  const isTokenMissing = !token
  const isFormBlocked = isTokenMissing || isValidating || !isTokenValid || hasCompletedReset

  useEffect(() => {
    let isMounted = true

    setForm(initialForm)
    setSuccessMessage('')
    setHasCompletedReset(false)

    if (isTokenMissing) {
      setError(INVALID_LINK_MESSAGE)
      setIsTokenValid(false)
      setIsValidating(false)
      return () => {
        isMounted = false
      }
    }

    setError('')
    setIsValidating(true)
    setIsTokenValid(false)

    validatePasswordResetToken({ token })
      .then(() => {
        if (!isMounted) {
          return
        }

        setError('')
        setIsTokenValid(true)
      })
      .catch(() => {
        if (!isMounted) {
          return
        }

        setError(INVALID_LINK_MESSAGE)
        setIsTokenValid(false)
      })
      .finally(() => {
        if (isMounted) {
          setIsValidating(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [isTokenMissing, token, validatePasswordResetToken])

  function handleChange(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSuccessMessage('')

    if (isTokenMissing || !isTokenValid) {
      setError(INVALID_LINK_MESSAGE)
      return
    }

    if (form.newPassword !== form.confirmPassword) {
      setError('Las contrasenas no coinciden.')
      return
    }

    setIsSubmitting(true)

    try {
      const response = await resetPassword({
        token,
        new_password: form.newPassword,
        confirm_password: form.confirmPassword,
      })
      setSuccessMessage(response.message)
      setForm(initialForm)
      setHasCompletedReset(true)
      setIsTokenValid(false)
    } catch (submitError) {
      if (submitError.message === INVALID_LINK_MESSAGE) {
        setError(INVALID_LINK_MESSAGE)
        setIsTokenValid(false)
      } else {
        setError(submitError.message)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell>
      <AuthCard
        mode="login"
        title="Restablecer contrasena"
        subtitle="Define una nueva contrasena para volver a entrar con normalidad."
        footer={(
          <p className="auth-switch-line">
            <span>Ya tienes una contrasena nueva?</span>{' '}
            <button type="button" className="auth-inline-link" onClick={onBackToLogin}>
              Volver al acceso
            </button>
          </p>
        )}
      >
        <form className="auth-command-form" onSubmit={handleSubmit}>
          <p className="auth-note">
            Este enlace es temporal y deja de servir en cuanto se completa el cambio de contrasena.
          </p>

          {isValidating ? <p className="auth-feedback auth-feedback-info">Verificando enlace...</p> : null}

          <label className="auth-field">
            <span>Nueva contrasena</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                lock
              </i>
              <input
                name="newPassword"
                type="password"
                placeholder="Minimo 8 caracteres"
                autoComplete="new-password"
                value={form.newPassword}
                onChange={handleChange}
                minLength={8}
                disabled={isFormBlocked}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span>Confirmar contrasena</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">
                lock_reset
              </i>
              <input
                name="confirmPassword"
                type="password"
                placeholder="Repite la nueva contrasena"
                autoComplete="new-password"
                value={form.confirmPassword}
                onChange={handleChange}
                minLength={8}
                disabled={isFormBlocked}
                required
              />
            </div>
          </label>

          {error ? <p className="auth-feedback auth-feedback-error">{error}</p> : null}
          {successMessage ? <p className="auth-feedback auth-feedback-info">{successMessage}</p> : null}

          <button
            type="submit"
            className="auth-primary-button"
            disabled={isSubmitting || isFormBlocked}
          >
            <span>{isSubmitting ? 'Actualizando contrasena...' : 'Guardar nueva contrasena'}</span>
            <i className="material-symbols-outlined" aria-hidden="true">
              verified
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

export default ResetPasswordPage
