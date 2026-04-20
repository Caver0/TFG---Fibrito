"""Schemas for diet adherence tracking and weekly interpretation."""
from datetime import date as date_type, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MealAdherenceStatus = Literal["pending", "completed", "omitted", "modified"]
AdherenceLevel = Literal["alta", "media", "baja"]


class MealAdherenceUpsertRequest(BaseModel):
    diet_id: str = Field(min_length=1)
    meal_number: int = Field(ge=1)
    date: date_type | None = None
    status: MealAdherenceStatus
    note: str | None = Field(default=None, max_length=280)


class MealAdherenceRecord(BaseModel):
    id: str | None = None
    user_id: str
    diet_id: str
    meal_number: int = Field(ge=1)
    date: date_type
    status: MealAdherenceStatus
    note: str | None = None
    adherence_score: float | None = Field(default=None, ge=0, le=1)
    is_recorded: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DailyAdherenceSummary(BaseModel):
    date: date_type
    diet_id: str | None = None
    total_meals: int = Field(default=0, ge=0)
    registered_meals: int = Field(default=0, ge=0)
    completed_meals: int = Field(default=0, ge=0)
    omitted_meals: int = Field(default=0, ge=0)
    modified_meals: int = Field(default=0, ge=0)
    pending_meals: int = Field(default=0, ge=0)
    adherence_score: float = Field(default=0, ge=0, le=1)
    adherence_percentage: float = Field(default=0, ge=0, le=100)


class DietAdherenceResponse(BaseModel):
    diet_id: str
    date: date_type
    total_meals: int = Field(ge=0)
    meals: list[MealAdherenceRecord] = Field(default_factory=list)
    daily_summary: DailyAdherenceSummary


class WeeklyAdherenceSummary(BaseModel):
    reference_date: date_type
    week_label: str
    start_date: date_type
    end_date: date_type
    days_with_records: int = Field(default=0, ge=0, le=7)
    total_planned_meals: int = Field(default=0, ge=0)
    total_meals_registered: int = Field(default=0, ge=0)
    completed_meals: int = Field(default=0, ge=0)
    omitted_meals: int = Field(default=0, ge=0)
    modified_meals: int = Field(default=0, ge=0)
    pending_meals: int = Field(default=0, ge=0)
    adherence_percentage: float = Field(default=0, ge=0, le=100)
    tracking_coverage_percentage: float = Field(default=0, ge=0, le=100)
    weekly_adherence_factor: float = Field(default=0, ge=0, le=1)
    tracking_coverage_factor: float = Field(default=0, ge=0, le=1)
    confidence_factor: float = Field(default=0, ge=0, le=1)
    confidence_percentage: float = Field(default=0, ge=0, le=100)
    adherence_level: AdherenceLevel
    interpretation_message: str


def normalize_adherence_note(note: str | None) -> str | None:
    normalized_note = " ".join(str(note or "").split()).strip()
    return normalized_note or None


def serialize_meal_adherence_record(document: dict[str, Any]) -> MealAdherenceRecord:
    return MealAdherenceRecord(
        id=str(document["_id"]) if document.get("_id") else None,
        user_id=str(document["user_id"]),
        diet_id=str(document["diet_id"]),
        meal_number=document["meal_number"],
        date=date_type.fromisoformat(document["date"]),
        status=document["status"],
        note=document.get("note"),
        adherence_score=document.get("adherence_score"),
        is_recorded=True,
        created_at=document.get("created_at"),
        updated_at=document.get("updated_at"),
    )