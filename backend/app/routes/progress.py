"""Routes for weekly weight analysis and calorie adjustments."""
from fastapi import APIRouter, Depends

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.adjustments import (
    AdjustmentHistoryResponse,
    ApplyWeeklyAdjustmentResponse,
)
from app.schemas.progress import WeeklyAnalysisResponse, WeeklyAveragesResponse
from app.schemas.user import UserPublic
from app.services.goal_adjustment_service import (
    analyze_weekly_progress,
    apply_calorie_adjustment,
    build_analysis_from_adjustment,
    get_existing_adjustment,
    list_adjustment_history,
)
from app.services.progress_service import (
    calculate_weekly_averages,
    list_weight_entries,
    serialize_weekly_averages,
)

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/weekly-averages", response_model=WeeklyAveragesResponse)
def read_weekly_averages(
    current_user: UserPublic = Depends(get_current_user),
) -> WeeklyAveragesResponse:
    database = get_database()
    entries = list_weight_entries(database, current_user.id)
    averages = serialize_weekly_averages(calculate_weekly_averages(entries))
    return WeeklyAveragesResponse(averages=averages)


@router.get("/weekly-analysis", response_model=WeeklyAnalysisResponse)
def read_weekly_analysis(
    current_user: UserPublic = Depends(get_current_user),
) -> WeeklyAnalysisResponse:
    database = get_database()
    entries = list_weight_entries(database, current_user.id)
    weekly_averages = calculate_weekly_averages(entries)
    return analyze_weekly_progress(current_user, weekly_averages)


@router.post("/apply-weekly-adjustment", response_model=ApplyWeeklyAdjustmentResponse)
def apply_weekly_adjustment(
    current_user: UserPublic = Depends(get_current_user),
) -> ApplyWeeklyAdjustmentResponse:
    database = get_database()
    entries = list_weight_entries(database, current_user.id)
    weekly_averages = calculate_weekly_averages(entries)
    analysis = analyze_weekly_progress(current_user, weekly_averages)
    existing_adjustment = get_existing_adjustment(
        database,
        current_user.id,
        analysis.previous_week_label,
        analysis.current_week_label,
    )
    if existing_adjustment:
        return ApplyWeeklyAdjustmentResponse(
            analysis=build_analysis_from_adjustment(existing_adjustment),
            adjustment=existing_adjustment,
        )

    adjustment = apply_calorie_adjustment(database, current_user.id, analysis, current_user.current_weight)
    return ApplyWeeklyAdjustmentResponse(analysis=analysis, adjustment=adjustment)


@router.get("/adjustments", response_model=AdjustmentHistoryResponse)
def read_adjustment_history(
    current_user: UserPublic = Depends(get_current_user),
) -> AdjustmentHistoryResponse:
    database = get_database()
    entries = list_adjustment_history(database, current_user.id)
    return AdjustmentHistoryResponse(entries=entries)
