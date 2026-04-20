import { useEffect, useMemo, useState } from 'react'

function formatNumber(value, decimals = 1) {
  return Number(value ?? 0).toFixed(decimals)
}

function formatSigned(value, unit = '') {
  const numericValue = Number(value ?? 0)
  const prefix = numericValue > 0 ? '+' : ''
  return `${prefix}${formatNumber(numericValue)}${unit ? ` ${unit}` : ''}`
}

function formatQuantity(quantity, unit, grams) {
  const normalizedQuantity = Number(quantity ?? 0)
  const quantityLabel = Number.isInteger(normalizedQuantity)
    ? normalizedQuantity.toFixed(0)
    : normalizedQuantity.toFixed(normalizedQuantity < 1 ? 2 : 1)
  const normalizedUnit = unit === 'unidad' ? (normalizedQuantity === 1 ? 'unidad' : 'unidades') : unit
  const baseLabel = `${quantityLabel} ${normalizedUnit}`

  if (!grams || unit === 'g') {
    return baseLabel
  }

  return `${baseLabel} (${formatNumber(grams, 1)} g aprox.)`
}

function FoodReplacementModal({
  food,
  isOpen,
  isSubmitting,
  mealNumber,
  onCancel,
  onLoadOptions,
  onSubmit,
}) {
  const [selectedOptionCode, setSelectedOptionCode] = useState('')
  const [replacementOptions, setReplacementOptions] = useState([])
  const [optionsError, setOptionsError] = useState('')
  const [isLoadingOptions, setIsLoadingOptions] = useState(false)

  useEffect(() => {
    if (!isOpen || !food) {
      setSelectedOptionCode('')
      setReplacementOptions([])
      setOptionsError('')
      setIsLoadingOptions(false)
      return
    }

    let isCancelled = false

    async function loadOptions() {
      setIsLoadingOptions(true)
      setOptionsError('')
      setReplacementOptions([])
      setSelectedOptionCode('')

      try {
        const response = await onLoadOptions(mealNumber, food)
        if (isCancelled) {
          return
        }

        const options = response.options ?? []
        setReplacementOptions(options)
        setSelectedOptionCode(options[0]?.food_code ?? '')
        if (!options.length) {
          setOptionsError('No hemos encontrado sustitutos compatibles para este alimento.')
        }
      } catch (error) {
        if (!isCancelled) {
          setOptionsError(error.message)
        }
      } finally {
        if (!isCancelled) {
          setIsLoadingOptions(false)
        }
      }
    }

    loadOptions()

    return () => {
      isCancelled = true
    }
  }, [food, isOpen, mealNumber, onLoadOptions])

  const selectedOption = useMemo(
    () => replacementOptions.find((option) => option.food_code === selectedOptionCode) ?? null,
    [replacementOptions, selectedOptionCode],
  )

  if (!isOpen || !food) {
    return null
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!selectedOption) {
      return
    }

    await onSubmit({
      current_food_name: food.name,
      current_food_code: food.food_code,
      replacement_food_name: selectedOption.name,
      replacement_food_code: selectedOption.food_code,
    })
  }

  return (
    <section className="replacement-panel">
      <div className="replacement-panel-header">
        <div>
          <span className="eyebrow">Sustitución</span>
          <strong>{food.name}</strong>
          <p>
            Comida {mealNumber}. Elige una alternativa y revisa la cantidad recomendada antes de aplicarla.
          </p>
        </div>

        <button
          className="secondary-button replacement-inline-cancel"
          disabled={isSubmitting}
          type="button"
          onClick={onCancel}
        >
          Cerrar
        </button>
      </div>

      {isLoadingOptions ? <p className="info-note">Buscando sustitutos compatibles...</p> : null}
      {optionsError ? <p className="info-note info-note-warning">{optionsError}</p> : null}

      {!isLoadingOptions && !optionsError && replacementOptions.length ? (
        <form className="replacement-form replacement-form-inline" onSubmit={handleSubmit}>
          <div className="replacement-form-layout">
            <label className="replacement-select-label">
              Opciones disponibles
              <select
                value={selectedOptionCode}
                onChange={(event) => setSelectedOptionCode(event.target.value)}
              >
                {replacementOptions.map((option) => (
                  <option key={option.food_code} value={option.food_code}>
                    {option.name} - {formatQuantity(option.recommended_quantity, option.recommended_unit, option.recommended_grams)}
                  </option>
                ))}
              </select>
              <span className="input-helper">
                La cantidad ya viene ajustada para esta comida.
              </span>
            </label>
          </div>

          {selectedOption ? (
            <article className="replacement-selected-card">
              <div className="replacement-result-header">
                <div>
                  <strong>{selectedOption.name}</strong>
                  <span>{selectedOption.category} | {selectedOption.functional_group}</span>
                </div>
                <span className={`replacement-strategy replacement-strategy-${selectedOption.strategy}`}>
                  {selectedOption.strategy === 'strict' ? 'Ajuste directo' : 'Ajuste flexible'}
                </span>
              </div>

              <div className="replacement-selected-layout">
                <div className="replacement-selected-main">
                  <p className="replacement-quantity">
                    Cantidad recomendada: <strong>{formatQuantity(selectedOption.recommended_quantity, selectedOption.recommended_unit, selectedOption.recommended_grams)}</strong>
                  </p>
                  <p className="replacement-result-note">{selectedOption.note}</p>
                </div>

                <div className="replacement-selected-summary">
                  <span>{formatNumber(selectedOption.calories, 1)} kcal</span>
                  <span>P {formatNumber(selectedOption.protein_grams, 1)} g</span>
                  <span>G {formatNumber(selectedOption.fat_grams, 1)} g</span>
                  <span>C {formatNumber(selectedOption.carb_grams, 1)} g</span>
                </div>

                <div className="replacement-selected-metrics">
                  <div className="replacement-result-grid replacement-result-grid-compact">
                    <span>Vs kcal: {formatSigned(selectedOption.calorie_delta_vs_current, 'kcal')}</span>
                    <span>Vs proteína: {formatSigned(selectedOption.protein_delta_vs_current, 'g')}</span>
                    <span>Vs grasas: {formatSigned(selectedOption.fat_delta_vs_current, 'g')}</span>
                    <span>Vs carbohidratos: {formatSigned(selectedOption.carb_delta_vs_current, 'g')}</span>
                  </div>

                  <p className="replacement-meal-impact">
                    Impacto en la comida: {formatSigned(selectedOption.meal_calorie_difference, 'kcal')} | P {formatSigned(selectedOption.meal_protein_difference, 'g')} | G {formatSigned(selectedOption.meal_fat_difference, 'g')} | C {formatSigned(selectedOption.meal_carb_difference, 'g')}
                  </p>
                </div>
              </div>
            </article>
          ) : null}

          <div className="replacement-actions replacement-actions-inline">
            <button className="secondary-button" disabled={isSubmitting} type="button" onClick={onCancel}>
              Cancelar
            </button>
            <button disabled={isSubmitting || !selectedOption} type="submit">
              {isSubmitting ? 'Sustituyendo...' : 'Aplicar sustitución'}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  )
}

export default FoodReplacementModal