import { useState } from 'react'
import * as userApi from '../api/userApi'
import AuthCard from '../components/AuthCard'
import AuthShell from '../components/AuthShell'
import { useAuth } from '../context/AuthContext'

const sexOptions = [
  { value: 'Masculino', label: 'Masculino' },
  { value: 'Femenino', label: 'Femenino' },
]

const goalOptions = [
  { value: 'perder_grasa', label: 'Perder grasa' },
  { value: 'mantener_peso', label: 'Mantener peso' },
  { value: 'ganar_masa', label: 'Ganar masa' },
]

const initialForm = {
  age: '',
  sex: '',
  height: '',
  current_weight: '',
  training_days_per_week: '',
  goal: '',
}

function OnboardingPage() {
  const { token, refreshUser } = useAuth()
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
      await userApi.updateNutritionProfile(token, {
        age: Number.parseInt(form.age, 10),
        sex: form.sex,
        height: Number(form.height),
        current_weight: Number(form.current_weight),
        training_days_per_week: Number.parseInt(form.training_days_per_week, 10),
        goal: form.goal,
      })
      await refreshUser()
    } catch (submitError) {
      setError(submitError.message)
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell>
      <AuthCard
        mode="register"
        title="Calibración Inicial"
        subtitle="Introduce tus datos para calcular tus calorías base y objetivos nutricionales."
      >
        <form className="auth-command-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Edad</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">cake</i>
              <input
                name="age"
                type="number"
                placeholder="Años"
                min="1"
                max="120"
                value={form.age}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span>Sexo</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">person</i>
              <select name="sex" value={form.sex} onChange={handleChange} required>
                <option value="">Selecciona una opción</option>
                {sexOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </label>

          <label className="auth-field">
            <span>Altura (cm)</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">height</i>
              <input
                name="height"
                type="number"
                placeholder="cm"
                min="1"
                step="0.1"
                value={form.height}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span>Peso actual (kg)</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">monitor_weight</i>
              <input
                name="current_weight"
                type="number"
                placeholder="kg"
                min="1"
                step="0.1"
                value={form.current_weight}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span>Días de entreno por semana</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">fitness_center</i>
              <input
                name="training_days_per_week"
                type="number"
                placeholder="0 – 7"
                min="0"
                max="7"
                value={form.training_days_per_week}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <label className="auth-field">
            <span>Objetivo</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">flag</i>
              <select name="goal" value={form.goal} onChange={handleChange} required>
                <option value="">Selecciona una opción</option>
                {goalOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </label>

          {error ? <p className="auth-feedback auth-feedback-error">{error}</p> : null}

          <button type="submit" className="auth-primary-button" disabled={isSubmitting}>
            <span>{isSubmitting ? 'Calibrando sistema...' : 'Activar perfil nutricional'}</span>
            <i className="material-symbols-outlined" aria-hidden="true">arrow_forward</i>
          </button>
        </form>
      </AuthCard>
    </AuthShell>
  )
}

export default OnboardingPage
