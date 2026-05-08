import { useEffect, useRef, useState } from 'react'
import * as userApi from '../api/userApi'
import AuthCard from '../components/AuthCard'
import AuthShell from '../components/AuthShell'
import { useAuth } from '../context/AuthContext'

const sexOptions = [
  { value: 'Masculino', submitValue: 'Masculino', label: 'Masculino' },
  { value: 'Femenino', submitValue: 'Femenino', label: 'Femenino' },
]

const goalOptions = [
  { value: 'perder_grasa', submitValue: 'perder_grasa', label: 'Pérdida de peso' },
  { value: 'mantener_peso', submitValue: 'mantener_peso', label: 'Mantenimiento' },
  { value: 'ganar_masa', submitValue: 'ganar_masa', label: 'Ganancia muscular' },
  { value: 'recomposicion', submitValue: 'mantener_peso', label: 'Recomposición' },
]

const initialForm = {
  age: '',
  sex: '',
  height: '',
  current_weight: '',
  training_days_per_week: '',
  goal: '',
}

function normalizeTrainingDays(value) {
  if (value === '') {
    return ''
  }

  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return ''
  }

  const safeValue = Math.trunc(numericValue)
  const clampedValue = Math.min(7, Math.max(0, safeValue))

  return String(clampedValue)
}

function OnboardingSelect({
  value,
  onChange,
  placeholder,
  options,
  icon,
  label,
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectRef = useRef(null)
  const selectedOption = options.find((option) => option.value === value)

  useEffect(() => {
    function handlePointerDown(event) {
      if (selectRef.current && !selectRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [])

  function handleSelect(option) {
    onChange(option)
    setIsOpen(false)
  }

  return (
    <div
      ref={selectRef}
      className={`auth-input-shell auth-input-shell-select ${isOpen ? 'auth-input-shell-select-open' : ''}`.trim()}
    >
      <i className="material-symbols-outlined" aria-hidden="true">{icon}</i>

      <button
        type="button"
        className="onboarding-select-trigger"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={label}
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className={`onboarding-select-value ${selectedOption ? '' : 'onboarding-select-value-placeholder'}`.trim()}>
          {selectedOption?.label ?? placeholder}
        </span>
        <i className="material-symbols-outlined onboarding-select-chevron" aria-hidden="true">
          expand_more
        </i>
      </button>

      {isOpen ? (
        <div className="onboarding-select-menu" role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={value === option.value}
              className={`onboarding-select-option ${value === option.value ? 'onboarding-select-option-active' : ''}`.trim()}
              onClick={() => handleSelect(option)}
            >
              <span>{option.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function OnboardingPage() {
  const { token, refreshUser } = useAuth()
  const [form, setForm] = useState(initialForm)
  const [goalSelection, setGoalSelection] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }))
  }

  function handleChange(event) {
    const { name, value } = event.target

    if (name === 'training_days_per_week') {
      updateField(name, normalizeTrainingDays(value))
      return
    }

    updateField(name, value)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')

    if (!form.sex || !form.goal) {
      setError('Selecciona sexo y objetivo para continuar.')
      return
    }

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
        mode="onboarding"
        bodyClassName="auth-card-body-onboarding"
        title="Configura tu perfil"
        subtitle="Completa tus datos para calcular tus calorías y objetivos nutricionales."
      >
        <form className="auth-command-form auth-command-form-onboarding" onSubmit={handleSubmit}>
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

          <div className="auth-field">
            <span>Sexo</span>
            <OnboardingSelect
              value={form.sex}
              onChange={(option) => updateField('sex', option.submitValue)}
              placeholder="Selecciona una opción"
              options={sexOptions}
              icon="person"
              label="Sexo"
            />
          </div>

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
            <span>Días de entrenamiento</span>
            <div className="auth-input-shell">
              <i className="material-symbols-outlined" aria-hidden="true">fitness_center</i>
              <input
                name="training_days_per_week"
                type="number"
                placeholder="0 - 7"
                min="0"
                max="7"
                step="1"
                inputMode="numeric"
                value={form.training_days_per_week}
                onChange={handleChange}
                required
              />
            </div>
          </label>

          <div className="auth-field">
            <span>Objetivo</span>
            <OnboardingSelect
              value={goalSelection}
              onChange={(option) => {
                setGoalSelection(option.value)
                updateField('goal', option.submitValue)
              }}
              placeholder="Selecciona una opción"
              options={goalOptions}
              icon="flag"
              label="Objetivo"
            />
          </div>

          {error ? <p className="auth-feedback auth-feedback-error">{error}</p> : null}

          <button type="submit" className="auth-primary-button" disabled={isSubmitting}>
            <span>{isSubmitting ? 'Guardando perfil...' : 'Guardar perfil'}</span>
            <i className="material-symbols-outlined" aria-hidden="true">arrow_forward</i>
          </button>
        </form>
      </AuthCard>
    </AuthShell>
  )
}

export default OnboardingPage
