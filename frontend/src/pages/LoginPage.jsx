import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

const initialForm = {
  email: '',
  password: '',
}

function LoginPage({ onSwitch }) {
  const { login } = useAuth()
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
      await login(form)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="auth-panel">
      <div className="auth-copy">
        <span className="eyebrow">Fibrito</span>
        <h1>Inicia sesión</h1>
        <p>Accede a tu perfil base para continuar construyendo tu planificación nutricional.</p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          <span>Email</span>
          <input
            name="email"
            type="email"
            placeholder="tu@email.com"
            value={form.email}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          <span>Contraseña</span>
          <input
            name="password"
            type="password"
            placeholder="********"
            value={form.password}
            onChange={handleChange}
            minLength={8}
            required
          />
        </label>

        {error ? <p className="form-error">{error}</p> : null}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Entrando...' : 'Entrar'}
        </button>
      </form>

      <p className="auth-switch">
        ¿No tienes cuenta?{' '}
        <button type="button" className="link-button" onClick={onSwitch}>
          Crear cuenta
        </button>
      </p>
    </section>
  )
}

export default LoginPage
