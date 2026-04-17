"""Schemas for the aggregated user dashboard overview."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.adherence import AdherenceLevel
from app.schemas.progress import WeeklyAnalysisResponse
from app.schemas.user import GoalType
from app.utils.meal_roles import MealRole


class DashboardMacroSummary(BaseModel):
    protein_grams: float | None = None
    fat_grams: float | None = None
    carb_grams: float | None = None


class DashboardSummaryMetrics(BaseModel):
    current_weight: float | None = None
    current_weight_date: date | None = None
    latest_weekly_change: float | None = None
    current_target_calories: float | None = None
    current_macros: DashboardMacroSummary = Field(default_factory=DashboardMacroSummary)
    weekly_adherence_percentage: float = 0.0
    weekly_adherence_factor: float = 0.0
    adherence_level: AdherenceLevel = "baja"
    adherence_interpretation: str = ""
    goal: GoalType | None = None


class WeightProgressPoint(BaseModel):
    date: date
    weight: float


class WeeklyWeightAveragePoint(BaseModel):
    week_label: str
    start_date: date
    end_date: date
    average_weight: float
    entry_count: int
    is_complete: bool


class ExpectedWeightTrendPoint(BaseModel):
    date: date
    expected_weight: float


class RegressionTrendPoint(BaseModel):
    date: date
    weight: float
    is_projection: bool


class CalorieAdjustmentEventPoint(BaseModel):
    id: str
    date: date
    week_label: str
    reference_weight: float | None = None
    previous_target_calories: float | None = None
    new_target_calories: float | None = None
    calorie_change: int
    adjustment_reason: str
    progress_status: str


class WeightProgressOverview(BaseModel):
    entries: list[WeightProgressPoint] = Field(default_factory=list)
    weekly_averages: list[WeeklyWeightAveragePoint] = Field(default_factory=list)
    expected_trend: list[ExpectedWeightTrendPoint] = Field(default_factory=list)
    expected_trend_label: str | None = None
    regression_trend: list[RegressionTrendPoint] = Field(default_factory=list)
    regression_weekly_change: float | None = None
    adjustment_events: list[CalorieAdjustmentEventPoint] = Field(default_factory=list)
    latest_analysis: WeeklyAnalysisResponse | None = None


class AdherenceDailyBreakdownPoint(BaseModel):
    date: date
    day_label: str
    total_meals: int = 0
    registered_meals: int = 0
    completed_meals: int = 0
    modified_meals: int = 0
    omitted_meals: int = 0
    pending_meals: int = 0
    adherence_percentage: float = 0.0


class AdherenceOverview(BaseModel):
    week_label: str
    start_date: date
    end_date: date
    adherence_percentage: float = 0.0
    weekly_adherence_factor: float = 0.0
    adherence_level: AdherenceLevel = "baja"
    tracking_coverage_percentage: float = 0.0
    total_planned_meals: int = 0
    total_meals_registered: int = 0
    completed_meals: int = 0
    modified_meals: int = 0
    omitted_meals: int = 0
    pending_meals: int = 0
    interpretation_message: str
    daily_breakdown: list[AdherenceDailyBreakdownPoint] = Field(default_factory=list)


class ActiveDietMealOverview(BaseModel):
    meal_number: int
    meal_role: MealRole = "meal"
    label: str
    target_calories: float
    actual_calories: float
    target_protein_grams: float
    target_fat_grams: float
    target_carb_grams: float
    distribution_percentage: float | None = None


class ActiveDietOverview(BaseModel):
    id: str
    created_at: datetime
    target_calories: float
    protein_grams: float
    fat_grams: float
    carb_grams: float
    meals_count: int
    calories_per_meal: list[ActiveDietMealOverview] = Field(default_factory=list)


class DashboardOverviewResponse(BaseModel):
    summary: DashboardSummaryMetrics
    weight_progress: WeightProgressOverview
    adherence: AdherenceOverview
    active_diet: ActiveDietOverview | None = None
