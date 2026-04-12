import { useEffect, useState } from 'react'

const dietaryRestrictionOptions = [
  { value: 'vegetariano', label: 'Vegetariano' },
  { value: 'vegano', label: 'Vegano' },
  { value: 'sin_lactosa', label: 'Sin lactosa' },
  { value: 'sin_gluten', label: 'Sin gluten' },
  { value: 'halal', label: 'Halal' },
  { value: 'kosher', label: 'Kosher' },
]

const allergyOptions = [
  { value: 'frutos_secos', label: 'Frutos secos' },
  { value: 'marisco', label: 'Marisco' },
  { value: 'huevo', label: 'Huevo' },
  { value: 'lacteos', label: 'Lacteos' },
  { value: 'gluten', label: 'Gluten' },
  { value: 'pescado', label: 'Pescado' },
]

function buildFormState(preferences) {
  return {
    preferredFoods: (preferences?.preferred_foods ?? []).join(', '),
    dislikedFoods: (preferences?.disliked_foods ?? []).join(', '),
    dietaryRestrictions: preferences?.dietary_restrictions ?? [],
    allergies: preferences?.allergies ?? [],
  }
}

function parseCommaSeparatedList(value) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function toggleValue(list, value) {
  if (list.includes(value)) {
    return list.filter((item) => item !== value)
  }

  return [...list, value]
}

function formatPreferenceList(values, options) {
  if (!values?.length) {
    return 'Sin configurar'
  }

  const labelMap = new Map(options.map((option) => [option.value, option.label]))
  return values.map((value) => labelMap.get(value) ?? value).join(', ')
}

function FoodPreferencesForm({
  preferences,
  isLoading,
  isSaving,
  saveError,
  saveMessage,
  onSave,
}) {
  const [form, setForm] = useState(buildFormState(preferences))

  useEffect(() => {
    setForm(buildFormState(preferences))
  }, [preferences])

  function handleTextChange(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  function handleToggle(fieldName, value) {
    setForm((current) => ({
      ...current,
      [fieldName]: toggleValue(current[fieldName], value),
    }))
  }

  function handleSubmit(event) {
    event.preventDefault()

    onSave({
      preferred_foods: parseCommaSeparatedList(form.preferredFoods),
      disliked_foods: parseCommaSeparatedList(form.dislikedFoods),
      dietary_restrictions: form.dietaryRestrictions,
      allergies: form.allergies,
    })
  }

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Preferencias alimentarias</span>
        <h2>Gustos, rechazos y exclusiones</h2>
        <p>Guardamos tus preferencias para filtrar alimentos incompatibles y dar prioridad a los que encajan mejor contigo.</p>
      </div>

      {isLoading ? <p className="info-note">Cargando preferencias alimentarias...</p> : null}

      <form className="profile-form" onSubmit={handleSubmit}>
        <label className="profile-form-full">
          <span>Alimentos preferidos</span>
          <input
            name="preferredFoods"
            type="text"
            value={form.preferredFoods}
            onChange={handleTextChange}
            placeholder="Ejemplo: pechuga de pollo, arroz, patata"
          />
        </label>

        <label className="profile-form-full">
          <span>Alimentos no deseados</span>
          <input
            name="dislikedFoods"
            type="text"
            value={form.dislikedFoods}
            onChange={handleTextChange}
            placeholder="Ejemplo: atun, avena, yogur griego"
          />
        </label>

        <div className="preference-option-group profile-form-full">
          <span>Restricciones dieteticas</span>
          <div className="preference-options-grid">
            {dietaryRestrictionOptions.map((option) => (
              <label key={option.value} className="diet-toggle preference-toggle">
                <input
                  type="checkbox"
                  checked={form.dietaryRestrictions.includes(option.value)}
                  onChange={() => handleToggle('dietaryRestrictions', option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="preference-option-group profile-form-full">
          <span>Alergias o intolerancias</span>
          <div className="preference-options-grid">
            {allergyOptions.map((option) => (
              <label key={option.value} className="diet-toggle preference-toggle">
                <input
                  type="checkbox"
                  checked={form.allergies.includes(option.value)}
                  onChange={() => handleToggle('allergies', option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="distribution-card">
          <div>
            <span className="history-label">Preferidos actuales</span>
            <strong>{preferences?.preferred_foods?.join(', ') || 'Sin configurar'}</strong>
          </div>
          <div>
            <span className="history-label">No deseados actuales</span>
            <strong>{preferences?.disliked_foods?.join(', ') || 'Sin configurar'}</strong>
          </div>
          <div>
            <span className="history-label">Restricciones activas</span>
            <strong>{formatPreferenceList(preferences?.dietary_restrictions, dietaryRestrictionOptions)}</strong>
          </div>
          <div>
            <span className="history-label">Alergias activas</span>
            <strong>{formatPreferenceList(preferences?.allergies, allergyOptions)}</strong>
          </div>
        </div>

        {saveError ? <p className="form-error">{saveError}</p> : null}
        {saveMessage ? <p className="form-success">{saveMessage}</p> : null}

        <button type="submit" disabled={isSaving || isLoading}>
          {isSaving ? 'Guardando preferencias...' : 'Guardar preferencias alimentarias'}
        </button>
      </form>
    </section>
  )
}

export default FoodPreferencesForm
