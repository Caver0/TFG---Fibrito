"""Business logic for weekly goal analysis and calorie adjustments."""
from decimal import Decimal
from datetime import UTC, datetime

from bson import ObjectId

from app.schemas.adjustments import AdjustmentHistoryEntry, serialize_adjustment_entry
from app.schemas.progress import WeeklyAnalysisResponse, WeeklyAverage
from app.schemas.user import UserPublic
from app.services.nutrition_service import (
    NutritionProfileIncompleteError,
    build_nutrition_summary,
)
from app.services.progress_service import get_last_two_weeks_for_analysis


INSUFFICIENT_DATA_REASON = (
    "Se necesitan al menos dos semanas completas con registros de peso para analizar el progreso."
)
MISSING_CALORIES_REASON = (
    "Completa primero tu perfil nutricional para disponer de calorias objetivo antes de aplicar ajustes."
)
MISSING_GOAL_REASON = (
    "Completa tu objetivo nutricional antes de analizar el progreso semanal."
)


def get_current_target_calories(user: UserPublic) -> float | None:
    if user.target_calories is not None:
        return user.target_calories

    try:
        return build_nutrition_summary(user).target_calories
    except NutritionProfileIncompleteError:
        return None


def calculate_calorie_adjustment(goal: str, weekly_change: float) -> tuple[str, bool, int, str]:
    if goal == "ganar_masa":
        if weekly_change > 0:
            return (
                "on_track",
                False,
                0,
                "La media semanal ha subido y el progreso encaja con el objetivo de ganar masa.",
            )
        return (
            "needs_adjustment",
            True,
            150,
            "La media semanal no ha subido; se aumentan 150 kcal para favorecer una ganancia de peso sostenida.",
        )

    if goal == "perder_grasa":
        if weekly_change < 0:
            return (
                "on_track",
                False,
                0,
                "La media semanal ha bajado y el progreso encaja con el objetivo de perder grasa.",
            )
        return (
            "needs_adjustment",
            True,
            -150,
            "La media semanal no ha bajado; se reducen 150 kcal para reactivar la perdida de grasa.",
        )

    if abs(weekly_change) <= 0.15:
        return (
            "on_track",
            False,
            0,
            "El cambio semanal esta dentro del margen de mantenimiento de +/-0.15 kg.",
        )
    if weekly_change > 0.15:
        return (
            "needs_adjustment",
            True,
            -100,
            "El peso medio ha subido demasiado para mantenimiento; se reducen 100 kcal.",
        )
    return (
        "needs_adjustment",
        True,
        100,
        "El peso medio ha bajado demasiado para mantenimiento; se aumentan 100 kcal.",
    )


def analyze_weekly_progress(
    user: UserPublic,
    weekly_averages: list[WeeklyAverage],
) -> WeeklyAnalysisResponse:
    if user.goal is None:
        return WeeklyAnalysisResponse(
            can_analyze=False,
            progress_status="profile_incomplete",
            adjustment_needed=False,
            goal=None,
            previous_week_label=None,
            current_week_label=None,
            previous_week_avg=None,
            current_week_avg=None,
            weekly_change=None,
            calorie_change=0,
            previous_target_calories=user.target_calories,
            new_target_calories=user.target_calories,
            reason=MISSING_GOAL_REASON,
        )

    current_target_calories = get_current_target_calories(user)
    if current_target_calories is None:
        return WeeklyAnalysisResponse(
            can_analyze=False,
            progress_status="profile_incomplete",
            adjustment_needed=False,
            goal=user.goal,
            previous_week_label=None,
            current_week_label=None,
            previous_week_avg=None,
            current_week_avg=None,
            weekly_change=None,
            calorie_change=0,
            previous_target_calories=None,
            new_target_calories=None,
            reason=MISSING_CALORIES_REASON,
        )

    weeks_for_analysis = get_last_two_weeks_for_analysis(weekly_averages)
    if not weeks_for_analysis:
        return WeeklyAnalysisResponse(
            can_analyze=False,
            progress_status="insufficient_data",
            adjustment_needed=False,
            goal=user.goal,
            previous_week_label=None,
            current_week_label=None,
            previous_week_avg=None,
            current_week_avg=None,
            weekly_change=None,
            calorie_change=0,
            previous_target_calories=current_target_calories,
            new_target_calories=current_target_calories,
            reason=INSUFFICIENT_DATA_REASON,
        )

    previous_week, current_week = weeks_for_analysis
    weekly_change = float(
        Decimal(str(current_week.average_weight)) - Decimal(str(previous_week.average_weight))
    )
    progress_status, adjustment_needed, calorie_change, reason = calculate_calorie_adjustment(
        user.goal,
        weekly_change,
    )
    new_target_calories = current_target_calories + calorie_change

    return WeeklyAnalysisResponse(
        can_analyze=True,
        progress_status=progress_status,
        adjustment_needed=adjustment_needed,
        goal=user.goal,
        previous_week_label=previous_week.week_label,
        current_week_label=current_week.week_label,
        previous_week_avg=previous_week.average_weight,
        current_week_avg=current_week.average_weight,
        weekly_change=weekly_change,
        calorie_change=calorie_change,
        previous_target_calories=current_target_calories,
        new_target_calories=new_target_calories,
        reason=reason,
    )


def apply_calorie_adjustment(
    database,
    user_id: str,
    analysis: WeeklyAnalysisResponse,
) -> AdjustmentHistoryEntry | None:
    if not analysis.can_analyze:
        return None

    if analysis.adjustment_needed:
        database.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"target_calories": analysis.new_target_calories}},
        )

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
        "adjustment_applied": analysis.adjustment_needed,
        "calorie_change": analysis.calorie_change,
        "previous_target_calories": analysis.previous_target_calories,
        "new_target_calories": analysis.new_target_calories,
        "reason": analysis.reason,
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
    return WeeklyAnalysisResponse(
        can_analyze=True,
        progress_status=adjustment.progress_status,
        adjustment_needed=adjustment.adjustment_applied,
        goal=adjustment.goal,
        previous_week_label=adjustment.previous_week_label,
        current_week_label=adjustment.current_week_label,
        previous_week_avg=adjustment.previous_week_avg,
        current_week_avg=adjustment.current_week_avg,
        weekly_change=adjustment.weekly_change,
        calorie_change=adjustment.calorie_change,
        previous_target_calories=adjustment.previous_target_calories,
        new_target_calories=adjustment.new_target_calories,
        reason="Ya existe un analisis guardado para estas semanas. " + adjustment.reason,
    )


def list_adjustment_history(database, user_id: str) -> list[AdjustmentHistoryEntry]:
    documents = database.calorie_adjustments.find(
        {"user_id": ObjectId(user_id)}
    ).sort([("created_at", -1)])
    return [serialize_adjustment_entry(document) for document in documents]
