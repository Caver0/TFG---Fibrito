import { useEffect, useState } from 'react'

function formatStatusLabel(status) {
  if (status === 'completed') {
    return 'Completada'
  }
  if (status === 'omitted') {
    return 'Omitida'
  }
  if (status === 'modified') {
    return 'Modificada'
  }
  return 'Pendiente'
}

function formatScoreLabel(status) {
  if (status === 'completed') {
    return 'Puntuacion 1.0'
  }
  if (status === 'modified') {
    return 'Puntuacion 0.5'
  }
  if (status === 'omitted') {
    return 'Puntuacion 0.0'
  }
  return 'Sin registrar aun'
}

function MealAdherenceControls({
  adherence,
  isSaving,
  mealNumber,
  onSave,
}) {
  const currentStatus = adherence?.status ?? 'pending'
  const [isEditingModified, setIsEditingModified] = useState(false)
  const [note, setNote] = useState(adherence?.note ?? '')

  useEffect(() => {
    setNote(adherence?.note ?? '')
    setIsEditingModified(false)
  }, [adherence?.note, adherence?.status, adherence?.updated_at, mealNumber])

  async function handleQuickSave(status) {
    setIsEditingModified(false)
    await onSave(mealNumber, { status })
  }

  async function handleSubmitModified(event) {
    event.preventDefault()
    await onSave(mealNumber, { status: 'modified', note })
  }

  function handleOpenModifiedEditor() {
    setNote(adherence?.note ?? '')
    setIsEditingModified(true)
  }

  function handleCancelModifiedEditor() {
    setNote(adherence?.note ?? '')
    setIsEditingModified(false)
  }

  return (
    <section className="meal-adherence-panel">
      <div className="meal-adherence-header">
        <div className="meal-adherence-status">
          <span className={`adherence-pill adherence-pill-${currentStatus}`}>
            {formatStatusLabel(currentStatus)}
          </span>
          <small>{formatScoreLabel(currentStatus)}</small>
        </div>

        <div className="meal-adherence-actions">
          <button
            className={`secondary-button ${currentStatus === 'completed' ? 'secondary-button-active' : ''}`}
            disabled={isSaving}
            type="button"
            onClick={() => handleQuickSave('completed')}
          >
            Completada
          </button>
          <button
            className={`secondary-button ${currentStatus === 'omitted' ? 'secondary-button-active' : ''}`}
            disabled={isSaving}
            type="button"
            onClick={() => handleQuickSave('omitted')}
          >
            Omitida
          </button>
          <button
            className={`secondary-button ${currentStatus === 'modified' ? 'secondary-button-active' : ''}`}
            disabled={isSaving}
            type="button"
            onClick={handleOpenModifiedEditor}
          >
            {currentStatus === 'modified' ? 'Editar modificacion' : 'Modificada'}
          </button>
          <button
            className={`secondary-button ${currentStatus === 'pending' ? 'secondary-button-active' : ''}`}
            disabled={isSaving}
            type="button"
            onClick={() => handleQuickSave('pending')}
          >
            Pendiente
          </button>
        </div>
      </div>

      {currentStatus === 'modified' && adherence?.note && !isEditingModified ? (
        <p className="meal-adherence-note-preview">Nota guardada: {adherence.note}</p>
      ) : null}

      {isEditingModified ? (
        <form className="meal-adherence-note" onSubmit={handleSubmitModified}>
          <label>
            <span>Observacion de la desviacion</span>
            <textarea
              maxLength={280}
              placeholder="Ejemplo: cambie arroz por pan, comi menos cantidad, no tome el yogur..."
              rows={3}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>

          <div className="meal-adherence-note-actions">
            <button disabled={isSaving} type="submit">
              {isSaving ? 'Guardando...' : 'Guardar modificacion'}
            </button>
            <button
              className="secondary-button"
              disabled={isSaving}
              type="button"
              onClick={handleCancelModifiedEditor}
            >
              Cancelar
            </button>
          </div>
        </form>
      ) : null}
    </section>
  )
}

export default MealAdherenceControls
