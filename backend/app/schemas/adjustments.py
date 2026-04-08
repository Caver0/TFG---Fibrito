"""Schemas for calorie adjustment history and responses."""
from datetime import datetime
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
    adjustment_applied: bool
    calorie_change: int
    previous_target_calories: float
    new_target_calories: float
    reason: str

    model_config = ConfigDict(from_attributes=True)


class AdjustmentHistoryResponse(BaseModel):
    entries: list[AdjustmentHistoryEntry]


class ApplyWeeklyAdjustmentResponse(BaseModel):
    analysis: WeeklyAnalysisResponse
    adjustment: AdjustmentHistoryEntry | None = None


def serialize_adjustment_entry(document: dict[str, Any]) -> AdjustmentHistoryEntry:
    return AdjustmentHistoryEntry(
        id=str(document["_id"]),
        created_at=document["created_at"],
        previous_week_label=document["previous_week_label"],
        current_week_label=document["current_week_label"],
        previous_week_avg=document["previous_week_avg"],
        current_week_avg=document["current_week_avg"],
        weekly_change=document["weekly_change"],
        goal=document["goal"],
        progress_status=document["progress_status"],
        adjustment_applied=document["adjustment_applied"],
        calorie_change=document["calorie_change"],
        previous_target_calories=document["previous_target_calories"],
        new_target_calories=document["new_target_calories"],
        reason=document["reason"],
    )
