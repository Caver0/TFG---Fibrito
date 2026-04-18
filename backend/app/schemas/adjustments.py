"""Schemas for calorie adjustment history and responses."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.progress import WeeklyAnalysisResponse
from app.schemas.user import GoalType
from app.services.nutrition_service import calculate_macros


class AdjustmentMacroTargets(BaseModel):
    protein_grams: float
    fat_grams: float
    carb_grams: float


class AdjustmentHistoryEntry(BaseModel):
    id: str
    created_at: datetime
    previous_week_label: str
    current_week_label: str
    previous_week_avg: float
    current_week_avg: float
    weekly_change: float
    goal: GoalType
    progress_status: str
    progress_direction_ok: bool | None
    progress_rate_ok: bool | None
    adjustment_applied: bool
    max_weekly_loss: float | None
    calorie_change: int
    previous_target_calories: float
    new_target_calories: float
    previous_target_macros: AdjustmentMacroTargets | None = None
    new_target_macros: AdjustmentMacroTargets | None = None
    diet_adjustment_notes: list[str] = Field(default_factory=list)
    adjustment_reason: str
    reason: str

    model_config = ConfigDict(from_attributes=True)


class AdjustmentHistoryResponse(BaseModel):
    entries: list[AdjustmentHistoryEntry]


class ApplyWeeklyAdjustmentResponse(BaseModel):
    analysis: WeeklyAnalysisResponse
    adjustment: AdjustmentHistoryEntry | None = None


def _round_progress_metric(value: float | None) -> float | None:
    if value is None:
        return None

    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _serialize_macro_targets(snapshot: dict[str, Any] | None) -> AdjustmentMacroTargets | None:
    if not snapshot:
        return None

    protein_grams = snapshot.get("protein_grams")
    fat_grams = snapshot.get("fat_grams")
    carb_grams = snapshot.get("carb_grams")
    if protein_grams is None or fat_grams is None or carb_grams is None:
        return None

    return AdjustmentMacroTargets(
        protein_grams=float(Decimal(str(protein_grams)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
        fat_grams=float(Decimal(str(fat_grams)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
        carb_grams=float(Decimal(str(carb_grams)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
    )


def _build_macro_targets_from_history(
    *,
    document: dict[str, Any],
    target_calories_key: str,
) -> AdjustmentMacroTargets | None:
    reference_weight = (
        document.get("macro_reference_weight")
        or document.get("current_week_avg")
        or document.get("previous_week_avg")
    )
    target_calories = document.get(target_calories_key)
    if reference_weight is None or target_calories is None:
        return None

    return _serialize_macro_targets(calculate_macros(float(reference_weight), float(target_calories)))


def serialize_adjustment_entry(document: dict[str, Any]) -> AdjustmentHistoryEntry:
    adjustment_reason = document.get("adjustment_reason", document["reason"])
    previous_target_macros = _serialize_macro_targets(document.get("previous_target_macros"))
    new_target_macros = _serialize_macro_targets(document.get("new_target_macros"))

    return AdjustmentHistoryEntry(
        id=str(document["_id"]),
        created_at=document["created_at"],
        previous_week_label=document["previous_week_label"],
        current_week_label=document["current_week_label"],
        previous_week_avg=_round_progress_metric(document["previous_week_avg"]),
        current_week_avg=_round_progress_metric(document["current_week_avg"]),
        weekly_change=_round_progress_metric(document["weekly_change"]),
        goal=document["goal"],
        progress_status=document["progress_status"],
        progress_direction_ok=document.get("progress_direction_ok"),
        progress_rate_ok=document.get("progress_rate_ok"),
        adjustment_applied=document["adjustment_applied"],
        max_weekly_loss=_round_progress_metric(document.get("max_weekly_loss")),
        calorie_change=document["calorie_change"],
        previous_target_calories=document["previous_target_calories"],
        new_target_calories=document["new_target_calories"],
        previous_target_macros=previous_target_macros or _build_macro_targets_from_history(
            document=document,
            target_calories_key="previous_target_calories",
        ),
        new_target_macros=new_target_macros or _build_macro_targets_from_history(
            document=document,
            target_calories_key="new_target_calories",
        ),
        diet_adjustment_notes=document.get("diet_adjustment_notes", []),
        adjustment_reason=adjustment_reason,
        reason=adjustment_reason,
    )
