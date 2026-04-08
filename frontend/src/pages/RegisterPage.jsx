import { useState } from 'react'
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
    <section className="auth-panel">
      <div className="auth-copy">
        <span className="eyebrow">Fibrito</span>
        <h1>Crea tu cuenta</h1>
        <p>Empezamos con tu perfil base para dejar lista la siguiente fase del proyecto.</p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          <span>Nombre</span>
          <input
            name="name"
            type="text"
            placeholder="Tu nombre"
            value={form.name}
            onChange={handleChange}
            required
          />
        </label>

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
            placeholder="Mínimo 8 caracteres"
            value={form.password}
            onChange={handleChange}
            minLength={8}
            required
          />
        </label>

        {error ? <p className="form-error">{error}</p> : null}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Creando cuenta...' : 'Registrarme'}
        </button>
      </form>

      <p className="auth-switch">
        ¿Ya tienes cuenta?{' '}
        <button type="button" className="link-button" onClick={onSwitch}>
          Ir a login
        </button>
      </p>
    </section>
  )
}

export default RegisterPage
