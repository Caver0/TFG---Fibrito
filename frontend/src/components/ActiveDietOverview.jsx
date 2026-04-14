import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  formatCalories,
  formatLongDate,
  formatMacro,
  formatPercentage,
} from '../utils/dashboardFormat'

function buildTooltipContent({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null
  }

  const point = payload[0]?.payload
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <p>Calorias objetivo: {formatCalories(point.target_calories)}</p>
      <p>Calorias resueltas: {formatCalories(point.actual_calories)}</p>
      <p>
        Macros: {formatMacro(point.target_protein_grams)} P / {formatMacro(point.target_carb_grams)} C / {formatMacro(point.target_fat_grams)} G
      </p>
      {point.distribution_percentage ? <p>Distribucion: {formatPercentage(point.distribution_percentage)}</p> : null}
    </div>
  )
}

function ActiveDietOverview({ activeDiet }) {
  const mealData = (activeDiet?.calories_per_meal ?? []).map((meal) => ({
    ...meal,
    short_label: `C${meal.meal_number}`,
  }))

  return (
    <section className="profile-section">
      <div className="section-heading">
        <span className="eyebrow">Dieta activa</span>
        <h2>Plan actual o ultima dieta</h2>
        <p>El dashboard resume las calorias y macros del plan disponible y como se distribuyen por comida.</p>
      </div>

      {!activeDiet ? (
        <p className="info-note">Todavia no hay una dieta generada para mostrar en el dashboard.</p>
      ) : (
        <>
          <div className="dashboard-diet-grid dashboard-diet-grid-wide">
            <article className="metric-card">
              <span>Calorias diarias</span>
              <strong>{formatCalories(activeDiet.target_calories)}</strong>
            </article>
            <article className="metric-card">
              <span>Proteina</span>
              <strong>{formatMacro(activeDiet.protein_grams)}</strong>
            </article>
            <article className="metric-card">
              <span>Carbohidratos</span>
              <strong>{formatMacro(activeDiet.carb_grams)}</strong>
            </article>
            <article className="metric-card">
              <span>Grasas</span>
              <strong>{formatMacro(activeDiet.fat_grams)}</strong>
            </article>
          </div>

          <div className="dashboard-diet-content-grid">
            <div className="dashboard-chart-shell dashboard-chart-shell-compact dashboard-diet-chart-shell">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={mealData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid stroke="rgba(152, 176, 214, 0.16)" strokeDasharray="4 4" />
                  <XAxis dataKey="short_label" tick={{ fill: '#8fa0bd', fontSize: 12 }} />
                  <YAxis tickFormatter={(value) => `${Math.round(Number(value))}`} tick={{ fill: '#8fa0bd', fontSize: 12 }} />
                  <Tooltip content={buildTooltipContent} />
                  <Bar dataKey="target_calories" fill="#72d8ff" radius={[6, 6, 0, 0]} name="Calorias objetivo" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="dashboard-meal-list dashboard-meal-list-wide">
              {mealData.map((meal) => (
                <article key={meal.meal_number} className="dashboard-meal-card">
                  <strong>{meal.label}</strong>
                  <span>{formatCalories(meal.target_calories)}</span>
                  <p>
                    {formatMacro(meal.target_protein_grams)} P / {formatMacro(meal.target_carb_grams)} C / {formatMacro(meal.target_fat_grams)} G
                  </p>
                </article>
              ))}
            </div>
          </div>

          <p className="info-note">
            Ultima dieta guardada: {formatLongDate(activeDiet.created_at)}. Numero de comidas: {activeDiet.meals_count}.
          </p>
        </>
      )}
    </section>
  )
}

export default ActiveDietOverview
