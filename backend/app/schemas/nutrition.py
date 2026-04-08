"""Schemas for nutrition profile updates and calculated targets."""
from pydantic import BaseModel, Field

from app.schemas.user import GoalType, SexType


class NutritionProfileUpdate(BaseModel):
    age: int | None = Field(default=None, gt=0, le=120)
    sex: SexType | None = None
    height: float | None = Field(default=None, gt=0)
    current_weight: float | None = Field(default=None, gt=0)
    training_days_per_week: int | None = Field(default=None, ge=0, le=7)
    goal: GoalType | None = None


class NutritionCalculationInput(BaseModel):
    age: int = Field(gt=0, le=120)
    sex: SexType
    height: float = Field(gt=0)
    current_weight: float = Field(gt=0)
    training_days_per_week: int = Field(ge=0, le=7)
    goal: GoalType


class NutritionSummary(BaseModel):
    age: int
    sex: SexType
    height: float
    current_weight: float
    training_days_per_week: int
    goal: GoalType
    activity_factor: float
    bmr: float
    tdee: float
    target_calories: float
    protein_grams: float
    fat_grams: float
    carb_grams: float
