function NutritionSummary({ nutrition, error, isLoading }) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Objetivos iniciales</span>
        <h2>Resumen calculado</h2>
        <p>Mostramos tu base energetica y una primera distribucion de macronutrientes.</p>
      </div>

      {isLoading ? <p className="info-note">Calculando resumen nutricional...</p> : null}
      {!isLoading && error ? <p className="info-note info-note-warning">{error}</p> : null}

      {!isLoading && !error && nutrition ? (
        <>
          <div className="nutrition-grid">
            <article className="metric-card">
              <span>BMR</span>
              <strong>{nutrition.bmr} kcal</strong>
            </article>
            <article className="metric-card">
              <span>TDEE</span>
              <strong>{nutrition.tdee} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Calorias objetivo</span>
              <strong>{nutrition.target_calories} kcal</strong>
            </article>
            <article className="metric-card">
              <span>Proteina</span>
              <strong>{nutrition.protein_grams} g</strong>
            </article>
            <article className="metric-card">
              <span>Grasas</span>
              <strong>{nutrition.fat_grams} g</strong>
            </article>
            <article className="metric-card">
              <span>Carbohidratos</span>
              <strong>{nutrition.carb_grams} g</strong>
            </article>
          </div>

          <div className="summary-footnote">
            <span>Factor de actividad: {nutrition.activity_factor}</span>
            <span>{nutrition.training_days_per_week} dias de entreno por semana</span>
            <span>Objetivo: {nutrition.goal}</span>
          </div>
        </>
      ) : null}
    </section>
  )
}

export default NutritionSummary
