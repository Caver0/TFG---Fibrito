"""Routes for meal-level diet adherence tracking and summaries."""
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.adherence import (
    DailyAdherenceSummary,
    DietAdherenceResponse,
    MealAdherenceRecord,
    MealAdherenceUpsertRequest,
    WeeklyAdherenceSummary,
)
from app.schemas.user import UserPublic
from app.services.adherence_service import (
    calculate_daily_adherence_summary,
    calculate_weekly_adherence_summary,
    get_diet_adherence,
    save_meal_adherence,
)

router = APIRouter(prefix="/adherence", tags=["adherence"])


@router.post("/meals", response_model=MealAdherenceRecord)
def create_or_update_meal_adherence(
    payload: MealAdherenceUpsertRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> MealAdherenceRecord:
    database = get_database()
    return save_meal_adherence(database, current_user.id, payload)


@router.get("/diets/{diet_id}", response_model=DietAdherenceResponse)
def read_diet_adherence(
    diet_id: str,
    date_value: date | None = Query(default=None, alias="date"),
    current_user: UserPublic = Depends(get_current_user),
) -> DietAdherenceResponse:
    database = get_database()
    return get_diet_adherence(
        database,
        current_user.id,
        diet_id,
        target_date=date_value,
    )


@router.get("/daily-summary", response_model=DailyAdherenceSummary)
def read_daily_adherence_summary(
    date_value: date | None = Query(default=None, alias="date"),
    diet_id: str | None = Query(default=None),
    current_user: UserPublic = Depends(get_current_user),
) -> DailyAdherenceSummary:
    database = get_database()
    return calculate_daily_adherence_summary(
        database,
        current_user.id,
        target_date=date_value,
        diet_id=diet_id,
    )


@router.get("/weekly-summary", response_model=WeeklyAdherenceSummary)
def read_weekly_adherence_summary(
    reference_date: date | None = Query(default=None),
    week_label: str | None = Query(default=None),
    current_user: UserPublic = Depends(get_current_user),
) -> WeeklyAdherenceSummary:
    database = get_database()
    return calculate_weekly_adherence_summary(
        database,
        current_user.id,
        reference_date=reference_date,
        week_label=week_label,
    )
