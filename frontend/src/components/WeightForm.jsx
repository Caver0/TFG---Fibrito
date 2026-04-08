import { useState } from 'react'

const initialForm = {
  weight: '',
  date: '',
}

function WeightForm({ error, isSaving, message, onSave }) {
  const [form, setForm] = useState(initialForm)

  function handleChange(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()

    const payload = {
      weight: Number(form.weight),
      ...(form.date ? { date: form.date } : {}),
    }

    const saved = await onSave(payload)
    if (saved) {
      setForm(initialForm)
    }
  }

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Registro de peso</span>
        <h2>Anade una nueva entrada</h2>
        <p>Guarda tu peso actual para empezar a construir un historial de progreso.</p>
      </div>

      <form className="weight-form" onSubmit={handleSubmit}>
        <label>
          <span>Peso</span>
          <input
            name="weight"
            type="number"
            min="0.1"
            step="0.01"
            value={form.weight}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          <span>Fecha</span>
          <input
            name="date"
            type="date"
            value={form.date}
            onChange={handleChange}
          />
        </label>

        {error ? <p className="form-error">{error}</p> : null}
        {message ? <p className="form-success">{message}</p> : null}

        <button type="submit" disabled={isSaving}>
          {isSaving ? 'Guardando peso...' : 'Guardar peso'}
        </button>
      </form>
    </section>
  )
}

export default WeightForm
