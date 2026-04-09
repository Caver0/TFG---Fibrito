import { formatTrainingTimeOfDay } from '../utils/dietDistribution'

function formatDietTimestamp(value) {
  if (!value) {
    return 'Sin fecha'
  }

  return new Date(value).toLocaleString('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatDistribution(percentages) {
  if (!percentages?.length) {
    return 'Sin distribucion guardada'
  }

  return percentages.map((value) => `${value}%`).join(' / ')
}

function formatFoodQuantity(food) {
  const quantity = Number.isInteger(food.quantity) ? food.quantity.toFixed(0) : String(food.quantity)
  const unit = food.unit === 'unidad' ? (food.quantity === 1 ? 'unidad' : 'unidades') : food.unit
  const quantityLabel = `${quantity} ${unit}`

  if (!food.grams || food.unit === 'g') {
    return quantityLabel
  }

  return `${quantityLabel} (${food.grams} g aprox.)`
}

function formatFoodSource(value) {
  if (value === 'legacy_structural') {
    return 'Dieta estructural antigua'
  }

  if (value === 'internal_catalog') {
    return 'Catalogo interno'
  }

  return value || 'No indicado'
}

function DietCard({ description, diet, error, isLoading, title }) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Dieta diaria</span>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>

      {isLoading ? <p className="info-note">Cargando dieta...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}
      {!isLoading && !error && !diet ? (
        <p className="info-note">Todavia no hay una dieta generada para mostrar.</p>
      ) : null}

      {!isLoading && diet ? (
        <>
          <div className="nutrition-grid">
            <article className="metric-card">
              <span>Creada</span>
              <strong>{formatDietTimestamp(diet.created_at)}</strong>
            </article>
            <article className="metric-card">
              <span>Comidas</span>
              <strong>{diet.meals_count}</strong>
            </article>
            <article className="metric-card">
              <span>Calorias generadas</span>
              <strong>{diet.actual_calories} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Objetivo diario</span>
              <strong>{diet.target_calories} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Proteina generada</span>
              <strong>{diet.actual_protein_grams} g</strong>
            </article>
            <article className="metric-card">
              <span>Grasas generadas</span>
              <strong>{diet.actual_fat_grams} g</strong>
            </article>
            <article className="metric-card">
              <span>Carbohidratos generados</span>
              <strong>{diet.actual_carb_grams} g</strong>
            </article>
            <article className="metric-card">
              <span>Distribucion usada</span>
              <strong>{formatDistribution(diet.distribution_percentages)}</strong>
            </article>
            <article className="metric-card">
              <span>Fuente de alimentos</span>
              <strong>{formatFoodSource(diet.food_data_source)}</strong>
            </article>
            <article className="metric-card">
              <span>Optimizacion por entreno</span>
              <strong>{diet.training_optimization_applied ? 'Si' : 'No'}</strong>
            </article>
            <article className="metric-card">
              <span>Momento de entreno</span>
              <strong>{formatTrainingTimeOfDay(diet.training_time_of_day)}</strong>
            </article>
            <article className="metric-card">
              <span>Version del catalogo</span>
              <strong>{diet.food_catalog_version ?? 'No aplica'}</strong>
            </article>
          </div>

          <div className="meal-list">
            {diet.meals.map((meal) => (
              <article key={meal.meal_number} className="meal-card">
                <div className="meal-card-header">
                  <strong>Comida {meal.meal_number}</strong>
                  <span>{meal.distribution_percentage ?? 'Sin dato'}%</span>
                </div>

                <div className="meal-summary-grid">
                  <div className="meal-summary-item">
                    <span>Calorias</span>
                    <strong>{meal.actual_calories} / {meal.target_calories} kcal</strong>
                  </div>
                  <div className="meal-summary-item">
                    <span>Proteina</span>
                    <strong>{meal.actual_protein_grams} / {meal.target_protein_grams} g</strong>
                  </div>
                  <div className="meal-summary-item">
                    <span>Grasas</span>
                    <strong>{meal.actual_fat_grams} / {meal.target_fat_grams} g</strong>
                  </div>
                  <div className="meal-summary-item">
                    <span>Carbohidratos</span>
                    <strong>{meal.actual_carb_grams} / {meal.target_carb_grams} g</strong>
                  </div>
                </div>

                {meal.foods?.length ? (
                  <div className="food-list">
                    {meal.foods.map((food) => (
                      <article key={`${meal.meal_number}-${food.food_code ?? food.name}`} className="food-row">
                        <div className="food-row-header">
                          <strong>{food.name}</strong>
                          <span>{formatFoodQuantity(food)}</span>
                        </div>
                        <p className="food-row-meta">
                          {food.calories} kcal | P {food.protein_grams} g | G {food.fat_grams} g | C {food.carb_grams} g
                        </p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="info-note">Esta dieta no tiene alimentos concretos guardados.</p>
                )}
              </article>
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}

export default DietCard
