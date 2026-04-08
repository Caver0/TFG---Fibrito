"""Schemas for progress summaries and weekly analysis."""
from datetime import date

from pydantic import BaseModel

from app.schemas.user import GoalType


class ProgressSummary(BaseModel):
    latest_weight: float | None
    first_weight: float | None
    total_change: float | None
    number_of_entries: int
    latest_entry_date: date | None


class WeeklyAverage(BaseModel):
    week_label: str
    iso_year: int
    iso_week: int
    start_date: date
    end_date: date
    average_weight: float
    entry_count: int
    is_complete: bool


class WeeklyAveragesResponse(BaseModel):
    averages: list[WeeklyAverage]


class WeeklyAnalysisResponse(BaseModel):
    can_analyze: bool
    progress_status: str
    adjustment_needed: bool
    goal: GoalType | None
    progress_direction_ok: bool | None
    progress_rate_ok: bool | None
    previous_week_label: str | None
    current_week_label: str | None
    previous_week_avg: float | None
    current_week_avg: float | None
    weekly_change: float | None
    max_weekly_loss: float | None
    calorie_change: int
    previous_target_calories: float | None
    new_target_calories: float | None
    adjustment_reason: str
    reason: str
