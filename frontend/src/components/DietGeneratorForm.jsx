import { useEffect, useMemo, useState } from 'react'
import {
  TRAINING_TIME_OPTIONS,
  getDefaultDistributionTemplate,
  validateDistribution,
} from '../utils/dietDistribution'

function DietGeneratorForm({ error, isGenerating, message, onGenerate }) {
  const [mealsCount, setMealsCount] = useState('4')
  const [percentages, setPercentages] = useState(() =>
    getDefaultDistributionTemplate(4).map((value) => String(value)),
  )
  const [useTrainingOptimization, setUseTrainingOptimization] = useState(false)
  const [trainingTimeOfDay, setTrainingTimeOfDay] = useState('')

  useEffect(() => {
    setPercentages(getDefaultDistributionTemplate(mealsCount).map((value) => String(value)))
  }, [mealsCount])

  const validation = useMemo(
    () => validateDistribution(percentages, mealsCount),
    [percentages, mealsCount],
  )

  function handlePercentageChange(index, value) {
    setPercentages((currentPercentages) =>
      currentPercentages.map((currentValue, currentIndex) =>
        currentIndex === index ? value : currentValue,
      ),
    )
  }

  function restoreTemplate() {
    setPercentages(getDefaultDistributionTemplate(mealsCount).map((value) => String(value)))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!validation.isValid) {
      return
    }

    if (useTrainingOptimization && !trainingTimeOfDay) {
      return
    }

    const defaultTemplate = getDefaultDistributionTemplate(mealsCount)
    const parsedPercentages = percentages.map((value) => Number(value))
    const isCustomDistribution = parsedPercentages.some(
      (value, index) => value !== defaultTemplate[index],
    )

    await onGenerate({
      meals_count: Number(mealsCount),
      ...(isCustomDistribution ? { custom_percentages: parsedPercentages } : {}),
      ...(useTrainingOptimization ? { training_time_of_day: trainingTimeOfDay } : {}),
    })
  }

  const defaultTemplatePreview = getDefaultDistributionTemplate(mealsCount).join(' / ')
  const trainingValidationError = useTrainingOptimization && !trainingTimeOfDay
    ? 'Selecciona un momento del dia si quieres optimizar por entrenamiento.'
    : ''

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Generador de dieta</span>
        <h2>Crea una dieta diaria por alimentos</h2>
        <p>Partimos de tu distribucion por comidas y la convertimos en alimentos reales mostrando despues si cada alimento se resolvio con Spoonacular, cache local o catalogo interno.</p>
      </div>

      <form className="diet-form diet-form-wide" onSubmit={handleSubmit}>
        <label className="diet-form-field diet-form-field-compact">
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

        <div className="distribution-card diet-template-card">
          <div className="diet-template-card-header">
            <div className="distribution-card-header">
              <div>
                <span className="history-label">Plantilla por defecto</span>
                <strong>{defaultTemplatePreview}</strong>
              </div>
              <button
                type="button"
                className="secondary-button distribution-reset"
                onClick={restoreTemplate}
              >
                Restaurar plantilla
              </button>
            </div>

            <p className={`info-note ${validation.isValid ? '' : 'info-note-warning'}`}>
              Suma actual: {validation.sum.toFixed(1)}%
            </p>
          </div>

          <div className="distribution-grid diet-template-grid">
            {percentages.map((value, index) => (
              <label key={`${mealsCount}-${index}`}>
                <span>Comida {index + 1} (%)</span>
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={value}
                  onChange={(event) => handlePercentageChange(index, event.target.value)}
                  required
                />
              </label>
            ))}
          </div>
        </div>

        <label className="diet-toggle diet-toggle-wide">
          <input
            type="checkbox"
            checked={useTrainingOptimization}
            onChange={(event) => {
              setUseTrainingOptimization(event.target.checked)
              if (!event.target.checked) {
                setTrainingTimeOfDay('')
              }
            }}
          />
          <span>Quiero indicar mi momento habitual de entrenamiento</span>
        </label>

        {useTrainingOptimization ? (
          <label className="diet-form-field diet-form-field-secondary">
            <span>Momento del dia</span>
            <select
              value={trainingTimeOfDay}
              onChange={(event) => setTrainingTimeOfDay(event.target.value)}
              required
            >
              <option value="">Selecciona una opcion</option>
              {TRAINING_TIME_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <div className="info-note diet-form-placeholder">
            Si tu horario de entreno es estable, puedes indicarlo para repartir mejor la energia entre comidas.
          </div>
        )}

        <div className="diet-form-feedback">
          {!validation.isValid ? <p className="form-error">{validation.message}</p> : null}
          {trainingValidationError ? <p className="form-error">{trainingValidationError}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}
        </div>

        <div className="diet-form-actions">
          <button
            type="submit"
            disabled={isGenerating || !validation.isValid || Boolean(trainingValidationError)}
          >
            {isGenerating ? 'Generando dieta...' : 'Generar dieta por alimentos'}
          </button>
        </div>
      </form>
    </section>
  )
}

export default DietGeneratorForm
