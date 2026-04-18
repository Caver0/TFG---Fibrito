"""Business logic for weekly goal analysis and calorie adjustments."""
from decimal import Decimal
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.schemas.diet import DietMeal
from app.schemas.adjustments import AdjustmentHistoryEntry, serialize_adjustment_entry
from app.schemas.progress import WeeklyAnalysisResponse, WeeklyAverage
from app.schemas.user import UserPublic
from app.services.diet_service import (
    build_exact_meal_solution,
    build_food_portion,
    build_updated_diet_payload,
    calculate_difference_summary,
    calculate_meal_actuals_from_foods,
    get_active_user_diet,
    resolve_meal_context,
    save_diet,
)
from app.services.food_catalog_service import build_catalog_food_from_diet_food
from app.services.meal_regeneration_service import (
    build_diet_context_food_lookup,
    get_training_focus_for_meal,
    infer_existing_meal_plan,
)
from app.services.nutrition_service import (
    NutritionProfileIncompleteError,
    build_nutrition_summary,
    calculate_macros,
)
from app.services.progress_service import get_last_two_weeks_for_analysis, round_progress_value


INSUFFICIENT_DATA_REASON = (
    "Se necesitan al menos dos semanas completas con registros de peso para analizar el progreso."
)
MISSING_CALORIES_REASON = (
    "Completa primero tu perfil nutricional para disponer de calorias objetivo antes de aplicar ajustes."
)
MISSING_GOAL_REASON = (
    "Completa tu objetivo nutricional antes de analizar el progreso semanal."
)
MISSING_CURRENT_WEIGHT_REASON = (
    "Completa tu peso actual en el perfil nutricional para analizar correctamente una perdida de grasa."
)
EXISTING_ANALYSIS_PREFIX = "Ya existe un analisis guardado para estas semanas. "


def get_current_target_calories(user: UserPublic) -> float | None:
    if user.target_calories is not None:
        return user.target_calories

    try:
        return build_nutrition_summary(user).target_calories
    except NutritionProfileIncompleteError:
        return None


def _build_macro_snapshot(
    *,
    reference_weight: float | None,
    target_calories: float | None,
) -> dict[str, float] | None:
    if reference_weight is None or target_calories is None:
        return None

    macros = calculate_macros(reference_weight, target_calories)
    return {
        "protein_grams": round(float(macros["protein_grams"]), 1),
        "fat_grams": round(float(macros["fat_grams"]), 1),
        "carb_grams": round(float(macros["carb_grams"]), 1),
    }


def _build_target_macros(
    *,
    reference_weight: float,
    target_calories: float,
) -> dict[str, float]:
    macro_snapshot = _build_macro_snapshot(
        reference_weight=reference_weight,
        target_calories=target_calories,
    )
    if macro_snapshot is None:
        raise ValueError("No se pudieron calcular los macros objetivo para reajustar la dieta activa.")

    return macro_snapshot


def _get_meal_distribution_percentage(latest_diet, meal_index: int, meal) -> float:
    if meal.distribution_percentage is not None:
        return float(meal.distribution_percentage)

    if meal_index < len(latest_diet.distribution_percentages):
        return float(latest_diet.distribution_percentages[meal_index])

    if latest_diet.target_calories:
        return round((float(meal.target_calories) / float(latest_diet.target_calories)) * 100.0, 1)

    return 0.0


def _build_adjusted_meal_target(
    *,
    latest_diet,
    meal,
    meal_index: int,
    new_target_calories: float,
    macro_targets: dict[str, float],
) -> DietMeal:
    distribution_percentage = _get_meal_distribution_percentage(latest_diet, meal_index, meal)
    distribution_ratio = distribution_percentage / 100.0

    return DietMeal.model_validate({
        "meal_number": meal.meal_number,
        "meal_slot": meal.meal_slot,
        "meal_role": meal.meal_role,
        "meal_label": meal.meal_label,
        "distribution_percentage": distribution_percentage,
        "target_calories": round(new_target_calories * distribution_ratio, 1),
        "target_protein_grams": round(macro_targets["protein_grams"] * distribution_ratio, 1),
        "target_fat_grams": round(macro_targets["fat_grams"] * distribution_ratio, 1),
        "target_carb_grams": round(macro_targets["carb_grams"] * distribution_ratio, 1),
        "actual_calories": 0.0,
        "actual_protein_grams": 0.0,
        "actual_fat_grams": 0.0,
        "actual_carb_grams": 0.0,
        "calorie_difference": 0.0,
        "protein_difference": 0.0,
        "fat_difference": 0.0,
        "carb_difference": 0.0,
        "foods": [],
    })


def _build_updated_meal_payload(
    *,
    target_meal: DietMeal,
    foods: list[dict[str, Any]],
) -> dict[str, Any]:
    actuals = calculate_meal_actuals_from_foods(foods)
    differences = calculate_difference_summary(
        target_calories=target_meal.target_calories,
        target_protein_grams=target_meal.target_protein_grams,
        target_fat_grams=target_meal.target_fat_grams,
        target_carb_grams=target_meal.target_carb_grams,
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
    )
    return {
        "meal_number": target_meal.meal_number,
        "distribution_percentage": target_meal.distribution_percentage or 0.0,
        "target_calories": target_meal.target_calories,
        "target_protein_grams": target_meal.target_protein_grams,
        "target_fat_grams": target_meal.target_fat_grams,
        "target_carb_grams": target_meal.target_carb_grams,
        "actual_calories": actuals["actual_calories"],
        "actual_protein_grams": actuals["actual_protein_grams"],
        "actual_fat_grams": actuals["actual_fat_grams"],
        "actual_carb_grams": actuals["actual_carb_grams"],
        "calorie_difference": differences["calorie_difference"],
        "protein_difference": differences["protein_difference"],
        "fat_difference": differences["fat_difference"],
        "carb_difference": differences["carb_difference"],
        "foods": foods,
    }


def _reorder_foods_like_current_meal(current_meal, foods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered_foods: list[dict[str, Any]] = []
    used_indexes: set[int] = set()

    for current_food in current_meal.foods:
        current_food_code = str(current_food.food_code or "").strip()
        current_food_name = str(current_food.name or "").strip().lower()
        matched_index: int | None = None

        for index, food in enumerate(foods):
            if index in used_indexes:
                continue

            if current_food_code and str(food.get("food_code") or "").strip() == current_food_code:
                matched_index = index
                break
            if not current_food_code and str(food.get("name") or "").strip().lower() == current_food_name:
                matched_index = index
                break

        if matched_index is None:
            continue

        ordered_foods.append(foods[matched_index])
        used_indexes.add(matched_index)

    ordered_foods.extend(
        food
        for index, food in enumerate(foods)
        if index not in used_indexes
    )
    return ordered_foods


def _calculate_meal_scale_ratio(current_meal, target_meal: DietMeal) -> float:
    reference_calories = float(current_meal.target_calories or current_meal.actual_calories or 0.0)
    if reference_calories <= 0:
        return 1.0

    return float(target_meal.target_calories) / reference_calories


def _build_scaled_meal_with_same_foods(
    *,
    current_meal,
    target_meal: DietMeal,
) -> dict[str, Any]:
    scale_ratio = _calculate_meal_scale_ratio(current_meal, target_meal)
    scaled_foods = []

    for food in current_meal.foods:
        food_entry = build_catalog_food_from_diet_food(food.model_dump())
        scaled_foods.append(
            build_food_portion(
                food_entry,
                float(food.quantity) * scale_ratio,
            )
        )

    return _build_updated_meal_payload(
        target_meal=target_meal,
        foods=scaled_foods,
    )


def _build_adjustment_decision(
    *,
    progress_status: str,
    adjustment_needed: bool,
    calorie_change: int,
    progress_direction_ok: bool,
    progress_rate_ok: bool,
    adjustment_reason: str,
    max_weekly_loss: float | None = None,
) -> dict[str, Any]:
    return {
        "progress_status": progress_status,
        "adjustment_needed": adjustment_needed,
        "calorie_change": calorie_change,
        "progress_direction_ok": progress_direction_ok,
        "progress_rate_ok": progress_rate_ok,
        "adjustment_reason": adjustment_reason,
        "max_weekly_loss": max_weekly_loss,
    }


def calculate_calorie_adjustment(
    goal: str,
    weekly_change: float,
    current_weight: float | None = None,
    adherence_level: str = "alta"
) -> dict[str, Any]:
    if goal == "ganar_masa":
        if weekly_change <= 0:
            status = "needs_adjustment" if adherence_level != "baja" else "needs_attention"
            return _build_adjustment_decision(
                progress_status=status,
                adjustment_needed=(status == "needs_adjustment"),
                calorie_change=150,
                progress_direction_ok=False,
                progress_rate_ok=False,
                adjustment_reason=(
                    "No estás subiendo de peso. " + 
                    ("El plan requiere más energía." if adherence_level != "baja" else 
                     "Con baja adherencia es normal; intenta cumplir el plan antes de subir calorías.")
                ),
            )
        if weekly_change > 0.2:
            status = "needs_adjustment" if adherence_level != "baja" else "needs_attention"
            return _build_adjustment_decision(
                progress_status=status,
                adjustment_needed=(status == "needs_adjustment"),
                calorie_change=-100,
                progress_direction_ok=True,
                progress_rate_ok=False,
                adjustment_reason=(
                    "Subida demasiado rápida. " +
                    ("Ajustamos para minimizar ganancia de grasa." if adherence_level != "baja" else 
                     "Es posible que se deba a excesos puntuales. ¿Quieres ajustar o ser más estricto?")
                ),
            )
        return _build_adjustment_decision(
            progress_status="on_track",
            adjustment_needed=False,
            calorie_change=0,
            progress_direction_ok=True,
            progress_rate_ok=True,
            adjustment_reason="El usuario esta subiendo de peso dentro del rango esperado.",
        )

    if goal == "perder_grasa":
        if current_weight is None:
            raise ValueError(MISSING_CURRENT_WEIGHT_REASON)

        max_weekly_loss = float(Decimal(str(current_weight)) * Decimal("0.01"))
        weekly_loss = abs(weekly_change)

        if weekly_change >= 0:
            status = "needs_adjustment" if adherence_level != "baja" else "needs_attention"
            return _build_adjustment_decision(
                progress_status=status,
                adjustment_needed=(status == "needs_adjustment"),
                calorie_change=-150,
                progress_direction_ok=False,
                progress_rate_ok=False,
                adjustment_reason=(
                    "No hay pérdida de peso. " +
                    ("Es necesario recortar calorías." if adherence_level != "baja" else 
                     "La baja adherencia explica el estancamiento. Cumple el plan antes de recortar más.")
                ),
                max_weekly_loss=max_weekly_loss,
            )
        if weekly_loss > max_weekly_loss:
            status = "needs_adjustment" if adherence_level != "baja" else "needs_attention"
            return _build_adjustment_decision(
                progress_status=status,
                adjustment_needed=(status == "needs_adjustment"),
                calorie_change=100,
                progress_direction_ok=True,
                progress_rate_ok=False,
                adjustment_reason=(
                    "Pérdida excesivamente rápida. " +
                    ("Subimos calorías para proteger tu masa muscular." if adherence_level != "baja" else 
                     "Baja adherencia: puede ser pérdida de líquidos o error de medición por falta de registros.")
                ),
                max_weekly_loss=max_weekly_loss,
            )
        if weekly_loss < 0.3:
            status = "needs_adjustment" if adherence_level != "baja" else "needs_attention"
            return _build_adjustment_decision(
                progress_status=status,
                adjustment_needed=(status == "needs_adjustment"),
                calorie_change=-100,
                progress_direction_ok=True,
                progress_rate_ok=False,
                adjustment_reason=(
                    "Ritmo de pérdida muy lento. " +
                    ("Ajuste necesario para mantener la tendencia." if adherence_level != "baja" else 
                     "Probablemente los excesos registrados impiden la bajada. ¡Mejora tu adherencia!")
                ),
                max_weekly_loss=max_weekly_loss,
            )
        return _build_adjustment_decision(
            progress_status="on_track",
            adjustment_needed=False,
            calorie_change=0,
            progress_direction_ok=True,
            progress_rate_ok=True,
            adjustment_reason="El usuario esta bajando de peso dentro del rango esperado.",
            max_weekly_loss=max_weekly_loss,
        )

    if abs(weekly_change) <= 0.15:
        return _build_adjustment_decision(
            progress_status="on_track",
            adjustment_needed=False,
            calorie_change=0,
            progress_direction_ok=True,
            progress_rate_ok=True,
            adjustment_reason="El peso se mantiene dentro del rango aceptable para mantenimiento.",
        )
    if weekly_change > 0.15:
        return _build_adjustment_decision(
            progress_status="needs_adjustment",
            adjustment_needed=True,
            calorie_change=-100,
            progress_direction_ok=True,
            progress_rate_ok=False,
            adjustment_reason=(
                "El usuario esta subiendo demasiado de peso para un objetivo de mantenimiento."
            ),
        )
    return _build_adjustment_decision(
        progress_status="needs_adjustment",
        adjustment_needed=True,
        calorie_change=100,
        progress_direction_ok=True,
        progress_rate_ok=False,
        adjustment_reason=(
            "El usuario esta bajando demasiado de peso para un objetivo de mantenimiento."
        ),
    )


def analyze_weekly_progress(
    user: UserPublic,
    weekly_averages: list[WeeklyAverage],
    *,
    adherence_level: str = "alta",
) -> WeeklyAnalysisResponse:
    if user.goal is None:
        adjustment_reason = MISSING_GOAL_REASON
        return WeeklyAnalysisResponse(
            can_analyze=False,
            progress_status="profile_incomplete",
            adjustment_needed=False,
            goal=None,
            progress_direction_ok=None,
            progress_rate_ok=None,
            previous_week_label=None,
            current_week_label=None,
            previous_week_avg=None,
            current_week_avg=None,
            weekly_change=None,
            max_weekly_loss=None,
            calorie_change=0,
            previous_target_calories=user.target_calories,
            new_target_calories=user.target_calories,
            adjustment_reason=adjustment_reason,
            reason=adjustment_reason,
        )

    current_target_calories = get_current_target_calories(user)
    if current_target_calories is None:
        adjustment_reason = MISSING_CALORIES_REASON
        return WeeklyAnalysisResponse(
            can_analyze=False,
            progress_status="profile_incomplete",
            adjustment_needed=False,
            goal=user.goal,
            progress_direction_ok=None,
            progress_rate_ok=None,
            previous_week_label=None,
            current_week_label=None,
            previous_week_avg=None,
            current_week_avg=None,
            weekly_change=None,
            max_weekly_loss=None,
            calorie_change=0,
            previous_target_calories=None,
            new_target_calories=None,
            adjustment_reason=adjustment_reason,
            reason=adjustment_reason,
        )

    if user.goal == "perder_grasa" and user.current_weight is None:
        adjustment_reason = MISSING_CURRENT_WEIGHT_REASON
        return WeeklyAnalysisResponse(
            can_analyze=False,
            progress_status="profile_incomplete",
            adjustment_needed=False,
            goal=user.goal,
            progress_direction_ok=None,
            progress_rate_ok=None,
            previous_week_label=None,
            current_week_label=None,
            previous_week_avg=None,
            current_week_avg=None,
            weekly_change=None,
            max_weekly_loss=None,
            calorie_change=0,
            previous_target_calories=current_target_calories,
            new_target_calories=current_target_calories,
            adjustment_reason=adjustment_reason,
            reason=adjustment_reason,
        )

    weeks_for_analysis = get_last_two_weeks_for_analysis(weekly_averages)
    if not weeks_for_analysis:
        adjustment_reason = INSUFFICIENT_DATA_REASON
        return WeeklyAnalysisResponse(
            can_analyze=False,
            progress_status="insufficient_data",
            adjustment_needed=False,
            goal=user.goal,
            progress_direction_ok=None,
            progress_rate_ok=None,
            previous_week_label=None,
            current_week_label=None,
            previous_week_avg=None,
            current_week_avg=None,
            weekly_change=None,
            max_weekly_loss=None,
            calorie_change=0,
            previous_target_calories=current_target_calories,
            new_target_calories=current_target_calories,
            adjustment_reason=adjustment_reason,
            reason=adjustment_reason,
        )

    previous_week, current_week = weeks_for_analysis
    weekly_change = float(
        Decimal(str(current_week.average_weight)) - Decimal(str(previous_week.average_weight))
    )
    adjustment_decision = calculate_calorie_adjustment(
        user.goal,
        weekly_change,
        current_weight=user.current_weight,
        adherence_level=adherence_level,
    )
    new_target_calories = current_target_calories + adjustment_decision["calorie_change"]
    adjustment_reason = adjustment_decision["adjustment_reason"]

    return WeeklyAnalysisResponse(
        can_analyze=True,
        progress_status=adjustment_decision["progress_status"],
        adjustment_needed=adjustment_decision["adjustment_needed"],
        goal=user.goal,
        progress_direction_ok=adjustment_decision["progress_direction_ok"],
        progress_rate_ok=adjustment_decision["progress_rate_ok"],
        previous_week_label=previous_week.week_label,
        current_week_label=current_week.week_label,
        previous_week_avg=round_progress_value(previous_week.average_weight),
        current_week_avg=round_progress_value(current_week.average_weight),
        weekly_change=round_progress_value(weekly_change),
        max_weekly_loss=round_progress_value(adjustment_decision["max_weekly_loss"]),
        calorie_change=adjustment_decision["calorie_change"],
        previous_target_calories=current_target_calories,
        new_target_calories=new_target_calories,
        adjustment_reason=adjustment_reason,
        reason=adjustment_reason,
    )


def _try_build_exact_meal_with_same_foods(
    *,
    latest_diet,
    current_meal,
    target_meal: DietMeal,
    meal_index: int,
    food_lookup: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    if any(not str(food.food_code or "").strip() for food in current_meal.foods):
        return None, (
            f"Comida {current_meal.meal_number}: se uso un reajuste proporcional porque faltaban "
            "food_code en la dieta activa."
        )

    training_focus = get_training_focus_for_meal(latest_diet, meal_index)
    original_food_codes = [
        str(food.food_code).strip()
        for food in current_meal.foods
        if str(food.food_code or "").strip()
    ]

    try:
        inferred_plan = infer_existing_meal_plan(
            current_meal,
            meal_index=meal_index,
            meals_count=latest_diet.meals_count,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )
    except Exception:
        return None, (
            f"Comida {current_meal.meal_number}: se uso un reajuste proporcional porque no se pudo "
            "inferir su estructura exacta con el solver actual."
        )

    selected_role_codes = inferred_plan.get("selected_role_codes", {})
    support_food_specs = inferred_plan.get("support_food_specs", [])
    plan_food_codes = [
        *selected_role_codes.values(),
        *[support_food["food_code"] for support_food in support_food_specs],
    ]
    if (
        len(selected_role_codes) != 3
        or len(plan_food_codes) != len(original_food_codes)
        or set(plan_food_codes) != set(original_food_codes)
    ):
        return None, (
            f"Comida {current_meal.meal_number}: se uso un reajuste proporcional porque la estructura "
            "guardada no se pudo reconstruir exactamente con los mismos alimentos."
        )

    meal_slot, _ = resolve_meal_context(
        target_meal,
        meal_index=meal_index,
        meals_count=latest_diet.meals_count,
        training_focus=training_focus,
    )
    scale_ratio = _calculate_meal_scale_ratio(current_meal, target_meal)
    scaled_support_foods = [
        {
            "role": support_food["role"],
            "food_code": support_food["food_code"],
            "quantity": float(support_food["quantity"]) * scale_ratio,
        }
        for support_food in support_food_specs
    ]
    exact_solution = build_exact_meal_solution(
        meal=target_meal,
        role_foods={
            role: food_lookup[food_code]
            for role, food_code in selected_role_codes.items()
        },
        support_food_specs=scaled_support_foods,
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=food_lookup,
        training_focus=training_focus,
        meal_slot=meal_slot,
    )
    if not exact_solution:
        return None, (
            f"Comida {current_meal.meal_number}: se uso un reajuste proporcional porque el solver no "
            "encontro una solucion exacta manteniendo los mismos alimentos."
        )

    exact_food_codes = [
        str(food.get("food_code") or "").strip()
        for food in exact_solution.get("foods", [])
        if str(food.get("food_code") or "").strip()
    ]
    if len(exact_food_codes) != len(original_food_codes) or set(exact_food_codes) != set(original_food_codes):
        return None, (
            f"Comida {current_meal.meal_number}: se uso un reajuste proporcional porque la solucion exacta "
            "eliminaba o sustituia alimentos de la comida original."
        )

    return _build_updated_meal_payload(
        target_meal=target_meal,
        foods=_reorder_foods_like_current_meal(current_meal, exact_solution["foods"]),
    ), None


def _recalculate_active_diet_after_adjustment(
    database,
    user_id: str,
    new_target_calories: float,
    reference_weight: float,
) -> list[str]:
    latest_diet = get_active_user_diet(database, user_id)
    if not latest_diet:
        return [
            "No habia una dieta activa para reajustar; solo se actualizaron los objetivos nutricionales."
        ]

    macro_targets = _build_target_macros(
        reference_weight=reference_weight,
        target_calories=new_target_calories,
    )
    updated_diet = latest_diet.model_copy(update={
        "target_calories": round(float(new_target_calories), 1),
        "protein_grams": macro_targets["protein_grams"],
        "fat_grams": macro_targets["fat_grams"],
        "carb_grams": macro_targets["carb_grams"],
    })
    food_lookup = build_diet_context_food_lookup(database, latest_diet)
    updated_meals: list[dict[str, Any]] = []
    update_notes: list[str] = []

    for meal_index, current_meal in enumerate(latest_diet.meals):
        target_meal = _build_adjusted_meal_target(
            latest_diet=latest_diet,
            meal=current_meal,
            meal_index=meal_index,
            new_target_calories=new_target_calories,
            macro_targets=macro_targets,
        )
        updated_meal, note = _try_build_exact_meal_with_same_foods(
            latest_diet=latest_diet,
            current_meal=current_meal,
            target_meal=target_meal,
            meal_index=meal_index,
            food_lookup=food_lookup,
        )
        if updated_meal is None:
            updated_meal = _build_scaled_meal_with_same_foods(
                current_meal=current_meal,
                target_meal=target_meal,
            )
        if note:
            update_notes.append(note)

        updated_meals.append(updated_meal)

    updated_diet_payload = build_updated_diet_payload(
        existing_diet=updated_diet,
        meals=updated_meals,
    )
    save_diet(
        database,
        user_id,
        updated_diet_payload,
        adjusted_from_diet_id=latest_diet.id,
    )

    if not update_notes:
        return [
            "Se creo una nueva version derivada de la dieta activa y se archivo la anterior.",
            "Se reajusto la dieta activa manteniendo las mismas comidas y los mismos alimentos en cada comida.",
        ]

    return [
        "Se creo una nueva version derivada de la dieta activa y se archivo la anterior.",
        "Se reajusto la dieta activa manteniendo las mismas comidas y los mismos alimentos.",
        *update_notes,
    ]


def _update_latest_diet_macro_targets(
    database,
    user_id: str,
    new_target_calories: float,
    current_weight: float,
) -> None:
    """Recalcula los targets de macros en la dieta más reciente sin tocar los alimentos."""
    latest_diet = database.diets.find_one(
        {"user_id": ObjectId(user_id)},
        sort=[("created_at", -1)],
    )
    if not latest_diet:
        return

    macros = calculate_macros(current_weight, new_target_calories)
    protein = round(macros["protein_grams"], 1)
    fat = round(macros["fat_grams"], 1)
    carbs = round(macros["carb_grams"], 1)

    updated_meals = []
    for meal in latest_diet.get("meals", []):
        pct = (meal.get("distribution_percentage") or 0.0) / 100.0
        t_cal = round(new_target_calories * pct, 1)
        t_p   = round(protein * pct, 1)
        t_f   = round(fat * pct, 1)
        t_c   = round(carbs * pct, 1)
        updated_meals.append({
            **meal,
            "target_calories":        t_cal,
            "target_protein_grams":   t_p,
            "target_fat_grams":       t_f,
            "target_carb_grams":      t_c,
            "calorie_difference":     round(meal["actual_calories"]        - t_cal, 1),
            "protein_difference":     round(meal["actual_protein_grams"]   - t_p,   1),
            "fat_difference":         round(meal["actual_fat_grams"]       - t_f,   1),
            "carb_difference":        round(meal["actual_carb_grams"]      - t_c,   1),
        })

    act_cal = latest_diet.get("actual_calories", 0.0)
    act_p   = latest_diet.get("actual_protein_grams", 0.0)
    act_f   = latest_diet.get("actual_fat_grams", 0.0)
    act_c   = latest_diet.get("actual_carb_grams", 0.0)

    database.diets.update_one(
        {"_id": latest_diet["_id"]},
        {"$set": {
            "target_calories":        round(new_target_calories, 1),
            "protein_grams":          protein,
            "fat_grams":              fat,
            "carb_grams":             carbs,
            "calorie_difference":     round(act_cal - new_target_calories, 1),
            "protein_difference":     round(act_p   - protein, 1),
            "fat_difference":         round(act_f   - fat, 1),
            "carb_difference":        round(act_c   - carbs, 1),
            "meals":                  updated_meals,
        }},
    )


def apply_calorie_adjustment(
    database,
    user_id: str,
    analysis: WeeklyAnalysisResponse,
    current_weight: float | None = None,
) -> AdjustmentHistoryEntry | None:
    if not analysis.can_analyze:
        return None

    reference_weight = current_weight if current_weight is not None else analysis.current_week_avg
    diet_adjustment_notes: list[str] = []
    if analysis.adjustment_needed:
        database.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"target_calories": analysis.new_target_calories}},
        )
        if reference_weight is not None:
            diet_adjustment_notes = _recalculate_active_diet_after_adjustment(
                database,
                user_id,
                analysis.new_target_calories,
                reference_weight,
            )
        else:
            diet_adjustment_notes = [
                "Se actualizaron las calorias objetivo, pero no fue posible reajustar la dieta activa por falta de un peso de referencia."
            ]

    adjustment_document = {
        "user_id": ObjectId(user_id),
        "created_at": datetime.now(UTC),
        "previous_week_label": analysis.previous_week_label,
        "current_week_label": analysis.current_week_label,
        "previous_week_avg": analysis.previous_week_avg,
        "current_week_avg": analysis.current_week_avg,
        "weekly_change": analysis.weekly_change,
        "goal": analysis.goal,
        "progress_status": analysis.progress_status,
        "progress_direction_ok": analysis.progress_direction_ok,
        "progress_rate_ok": analysis.progress_rate_ok,
        "adjustment_applied": analysis.adjustment_needed,
        "max_weekly_loss": analysis.max_weekly_loss,
        "calorie_change": analysis.calorie_change,
        "previous_target_calories": analysis.previous_target_calories,
        "new_target_calories": analysis.new_target_calories,
        "macro_reference_weight": reference_weight,
        "previous_target_macros": _build_macro_snapshot(
            reference_weight=reference_weight,
            target_calories=analysis.previous_target_calories,
        ),
        "new_target_macros": _build_macro_snapshot(
            reference_weight=reference_weight,
            target_calories=analysis.new_target_calories,
        ),
        "diet_adjustment_notes": diet_adjustment_notes,
        "adjustment_reason": analysis.adjustment_reason,
        "reason": analysis.adjustment_reason,
    }
    inserted = database.calorie_adjustments.insert_one(adjustment_document)
    created_adjustment = database.calorie_adjustments.find_one({"_id": inserted.inserted_id})
    return serialize_adjustment_entry(created_adjustment)


def get_existing_adjustment(
    database,
    user_id: str,
    previous_week_label: str | None,
    current_week_label: str | None,
) -> AdjustmentHistoryEntry | None:
    if not previous_week_label or not current_week_label:
        return None

    document = database.calorie_adjustments.find_one(
        {
            "user_id": ObjectId(user_id),
            "previous_week_label": previous_week_label,
            "current_week_label": current_week_label,
        },
        sort=[("created_at", -1)],
    )
    if not document:
        return None

    return serialize_adjustment_entry(document)


def build_analysis_from_adjustment(adjustment: AdjustmentHistoryEntry) -> WeeklyAnalysisResponse:
    adjustment_reason = EXISTING_ANALYSIS_PREFIX + adjustment.adjustment_reason

    return WeeklyAnalysisResponse(
        can_analyze=True,
        progress_status=adjustment.progress_status,
        adjustment_needed=adjustment.adjustment_applied,
        goal=adjustment.goal,
        progress_direction_ok=adjustment.progress_direction_ok,
        progress_rate_ok=adjustment.progress_rate_ok,
        previous_week_label=adjustment.previous_week_label,
        current_week_label=adjustment.current_week_label,
        previous_week_avg=adjustment.previous_week_avg,
        current_week_avg=adjustment.current_week_avg,
        weekly_change=adjustment.weekly_change,
        max_weekly_loss=adjustment.max_weekly_loss,
        calorie_change=adjustment.calorie_change,
        previous_target_calories=adjustment.previous_target_calories,
        new_target_calories=adjustment.new_target_calories,
        adjustment_reason=adjustment_reason,
        reason=adjustment_reason,
    )


def list_adjustment_history(database, user_id: str) -> list[AdjustmentHistoryEntry]:
    documents = database.calorie_adjustments.find(
        {"user_id": ObjectId(user_id)}
    ).sort([("created_at", -1)])
    return [serialize_adjustment_entry(document) for document in documents]
