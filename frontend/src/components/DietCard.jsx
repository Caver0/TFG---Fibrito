function formatDietTimestamp(value) {
  if (!value) {
    return 'Sin fecha'
  }

  return new Date(value).toLocaleString('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
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
              <span>Calorias totales</span>
              <strong>{diet.target_calories} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Proteina total</span>
              <strong>{diet.protein_grams} g</strong>
            </article>
            <article className="metric-card">
              <span>Grasas totales</span>
              <strong>{diet.fat_grams} g</strong>
            </article>
            <article className="metric-card">
              <span>Carbohidratos totales</span>
              <strong>{diet.carb_grams} g</strong>
            </article>
          </div>

          <div className="meal-list">
            {diet.meals.map((meal) => (
              <article key={meal.meal_number} className="meal-card">
                <div className="meal-card-header">
                  <strong>Comida {meal.meal_number}</strong>
                </div>
                <p>Calorias objetivo: {meal.target_calories} kcal</p>
                <p>Proteina objetivo: {meal.target_protein_grams} g</p>
                <p>Grasas objetivo: {meal.target_fat_grams} g</p>
                <p>Carbohidratos objetivo: {meal.target_carb_grams} g</p>
              </article>
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}

export default DietCard
