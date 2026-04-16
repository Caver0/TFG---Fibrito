"""Business logic for weekly goal analysis and calorie adjustments."""
from decimal import Decimal
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.schemas.adjustments import AdjustmentHistoryEntry, serialize_adjustment_entry
from app.schemas.progress import WeeklyAnalysisResponse, WeeklyAverage
from app.schemas.user import UserPublic
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

    if analysis.adjustment_needed:
        database.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"target_calories": analysis.new_target_calories}},
        )
        if current_weight is not None:
            _update_latest_diet_macro_targets(
                database, user_id, analysis.new_target_calories, current_weight
            )

    reference_weight = current_weight if current_weight is not None else analysis.current_week_avg
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
