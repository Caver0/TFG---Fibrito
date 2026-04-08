import { useState } from 'react'

function DietGeneratorForm({ error, isGenerating, message, onGenerate }) {
  const [mealsCount, setMealsCount] = useState('4')

  async function handleSubmit(event) {
    event.preventDefault()
    await onGenerate({ meals_count: Number(mealsCount) })
  }

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Generador de dieta</span>
        <h2>Crea una dieta diaria base</h2>
        <p>Repartimos tus calorias y macros actuales en un numero de comidas simple y equilibrado.</p>
      </div>

      <form className="diet-form" onSubmit={handleSubmit}>
        <label>
          <span>Numero de comidas</span>
          <select
            name="meals_count"
            value={mealsCount}
            onChange={(event) => setMealsCount(event.target.value)}
          >
            <option value="3">3 comidas</option>
            <option value="4">4 comidas</option>
            <option value="5">5 comidas</option>
            <option value="6">6 comidas</option>
          </select>
        </label>

        {error ? <p className="form-error">{error}</p> : null}
        {message ? <p className="form-success">{message}</p> : null}

        <button type="submit" disabled={isGenerating}>
          {isGenerating ? 'Generando dieta...' : 'Generar dieta'}
        </button>
      </form>
    </section>
  )
}

export default DietGeneratorForm
