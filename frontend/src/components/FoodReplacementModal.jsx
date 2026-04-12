import { useEffect, useState } from 'react'

function FoodReplacementModal({
  food,
  isOpen,
  isSubmitting,
  mealNumber,
  onClose,
  onSearchFoods,
  onSubmit,
}) {
  const [replacementQuery, setReplacementQuery] = useState('')
  const [selectedReplacement, setSelectedReplacement] = useState(null)
  const [searchResults, setSearchResults] = useState([])
  const [searchError, setSearchError] = useState('')
  const [isSearching, setIsSearching] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      setReplacementQuery('')
      setSelectedReplacement(null)
      setSearchResults([])
      setSearchError('')
      setIsSearching(false)
    }
  }, [isOpen])

  if (!isOpen || !food) {
    return null
  }

  async function handleSearch() {
    if (!replacementQuery.trim()) {
      setSearchResults([])
      setSearchError('')
      return
    }

    setIsSearching(true)
    setSearchError('')

    try {
      const foods = await onSearchFoods(replacementQuery.trim())
      setSearchResults(foods)
      if (!foods.length) {
        setSearchError('No hemos encontrado resultados claros para esa busqueda.')
      }
    } catch (error) {
      setSearchResults([])
      setSearchError(error.message)
    } finally {
      setIsSearching(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const replacementFoodName = selectedReplacement?.display_name || replacementQuery.trim() || undefined

    await onSubmit({
      current_food_name: food.name,
      current_food_code: food.food_code,
      replacement_food_name: replacementFoodName,
      replacement_food_code: selectedReplacement?.code,
    })
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        aria-label="Sustitucion de alimento"
        className="modal-panel"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="section-heading">
          <span className="eyebrow">Edicion de comida</span>
          <h2>Sustituir alimento</h2>
          <p>
            Vas a sustituir <strong>{food.name}</strong> en la comida {mealNumber}. Puedes dejar el campo vacio
            y Fibrito buscara una alternativa equivalente automaticamente.
          </p>
        </div>

        <form className="replacement-form" onSubmit={handleSubmit}>
          <label>
            Sustituto deseado
            <input
              placeholder="Ejemplo: pasta, pavo o leche"
              type="text"
              value={replacementQuery}
              onChange={(event) => {
                setReplacementQuery(event.target.value)
                setSelectedReplacement(null)
              }}
            />
            <span className="input-helper">
              Si eliges un resultado de la busqueda, enviaremos ese alimento exacto. Si no, se usara el texto escrito.
            </span>
          </label>

          <div className="replacement-actions">
            <button
              className="secondary-button"
              disabled={isSearching || isSubmitting || replacementQuery.trim().length < 2}
              type="button"
              onClick={handleSearch}
            >
              {isSearching ? 'Buscando...' : 'Buscar sugerencias'}
            </button>
            <button
              className="secondary-button"
              disabled={isSubmitting}
              type="button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button disabled={isSubmitting} type="submit">
              {isSubmitting ? 'Sustituyendo...' : 'Sustituir alimento'}
            </button>
          </div>
        </form>

        {searchError ? <p className="info-note info-note-warning">{searchError}</p> : null}

        {searchResults.length ? (
          <div className="replacement-results">
            {searchResults.map((result) => (
              <button
                key={result.code}
                className={`replacement-result ${selectedReplacement?.code === result.code ? 'replacement-result-active' : ''}`}
                type="button"
                onClick={() => {
                  setSelectedReplacement(result)
                  setReplacementQuery(result.display_name)
                }}
              >
                <strong>{result.display_name}</strong>
                <span>
                  {result.category} · {result.functional_group} · {Number(result.calories ?? 0).toFixed(1)} kcal por{' '}
                  {Number(result.reference_amount ?? 0).toFixed(Number(result.reference_amount ?? 0) % 1 === 0 ? 0 : 1)} {result.reference_unit}
                </span>
              </button>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  )
}

export default FoodReplacementModal
