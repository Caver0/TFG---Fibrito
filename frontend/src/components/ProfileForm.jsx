import { useEffect, useState } from 'react'

const sexOptions = [
  { value: 'Masculino', label: 'Masculino' },
  { value: 'Femenino', label: 'Femenino' },
]

const goalOptions = [
  { value: 'perder_grasa', label: 'Perder grasa' },
  { value: 'mantener_peso', label: 'Mantener peso' },
  { value: 'ganar_masa', label: 'Ganar masa' },
]

function buildFormState(user) {
  return {
    age: user?.age?.toString() ?? '',
    sex: user?.sex ?? '',
    height: user?.height?.toString() ?? '',
    current_weight: user?.current_weight?.toString() ?? '',
    training_days_per_week: user?.training_days_per_week?.toString() ?? '',
    goal: user?.goal ?? '',
  }
}

function ProfileForm({ user, isSaving, saveMessage, saveError, onSave }) {
  const [form, setForm] = useState(buildFormState(user))

  useEffect(() => {
    setForm(buildFormState(user))
  }, [user])

  function handleChange(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  function handleSubmit(event) {
    event.preventDefault()

    onSave({
      age: form.age === '' ? null : Number.parseInt(form.age, 10),
      sex: form.sex || null,
      height: form.height === '' ? null : Number(form.height),
      current_weight: form.current_weight === '' ? null : Number(form.current_weight),
      training_days_per_week:
        form.training_days_per_week === ''
          ? null
          : Number.parseInt(form.training_days_per_week, 10),
      goal: form.goal || null,
    })
  }

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Perfil nutricional</span>
        <h2>Datos base para el calculo inicial</h2>
        <p>Completa tus datos actuales y recalcularemos tus objetivos nutricionales al guardar.</p>
      </div>

      <form className="profile-form" onSubmit={handleSubmit}>
        <label>
          <span>Edad</span>
          <input
            name="age"
            type="number"
            min="1"
            value={form.age}
            onChange={handleChange}
          />
        </label>

        <label>
          <span>Sexo</span>
          <select name="sex" value={form.sex} onChange={handleChange}>
            <option value="">Selecciona una opcion</option>
            {sexOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Altura (cm)</span>
          <input
            name="height"
            type="number"
            min="1"
            step="0.1"
            value={form.height}
            onChange={handleChange}
          />
        </label>

        <label>
          <span>Peso actual (kg)</span>
          <input
            name="current_weight"
            type="number"
            min="1"
            step="0.1"
            value={form.current_weight}
            onChange={handleChange}
          />
        </label>

        <label>
          <span>Dias de entreno por semana</span>
          <input
            name="training_days_per_week"
            type="number"
            min="0"
            max="7"
            value={form.training_days_per_week}
            onChange={handleChange}
          />
        </label>

        <label>
          <span>Objetivo</span>
          <select name="goal" value={form.goal} onChange={handleChange}>
            <option value="">Selecciona una opcion</option>
            {goalOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        {saveError ? <p className="form-error">{saveError}</p> : null}
        {saveMessage ? <p className="form-success">{saveMessage}</p> : null}

        <button type="submit" disabled={isSaving}>
          {isSaving ? 'Guardando perfil...' : 'Guardar perfil nutricional'}
        </button>
      </form>
    </section>
  )
}

export default ProfileForm
