"""Schemas for calorie adjustment history and responses."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.progress import WeeklyAnalysisResponse
from app.schemas.user import GoalType


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


def serialize_adjustment_entry(document: dict[str, Any]) -> AdjustmentHistoryEntry:
    adjustment_reason = document.get("adjustment_reason", document["reason"])

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
        adjustment_reason=adjustment_reason,
        reason=adjustment_reason,
    )
