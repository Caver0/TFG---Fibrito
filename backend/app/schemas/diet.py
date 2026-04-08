"""Schemas for generated daily diets."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TrainingTimeOfDay = Literal["manana", "mediodia", "tarde", "noche"]
PERCENTAGE_PRECISION = Decimal("0.1")


def _round_percentage(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(PERCENTAGE_PRECISION, rounding=ROUND_HALF_UP))


def _derive_distribution_percentages(document: dict[str, Any]) -> list[float]:
    explicit_distribution = document.get("distribution_percentages")
    if explicit_distribution:
        return [_round_percentage(value) for value in explicit_distribution]

    meals = document.get("meals", [])
    total_calories = document.get("target_calories")
    if not meals or total_calories in (None, 0):
        return []

    remaining_percentage = Decimal("100.0")
    remaining_calories = Decimal(str(total_calories))
    derived_percentages: list[float] = []

    for index, meal in enumerate(meals):
        meal_calories = Decimal(str(meal.get("target_calories", 0)))
        remaining_slots = len(meals) - index
        if remaining_slots == 1 or remaining_calories == 0:
            percentage = remaining_percentage
        else:
            percentage = (
                (meal_calories / remaining_calories) * remaining_percentage
            ).quantize(PERCENTAGE_PRECISION, rounding=ROUND_HALF_UP)

        derived_percentages.append(float(percentage))
        remaining_percentage -= percentage
        remaining_calories -= meal_calories

    return derived_percentages


class DietGenerateRequest(BaseModel):
    meals_count: int = Field(ge=3, le=6)
    custom_percentages: list[float] | None = None
    training_time_of_day: TrainingTimeOfDay | None = None


class DietMeal(BaseModel):
    meal_number: int = Field(ge=1)
    distribution_percentage: float | None = Field(default=None, gt=0)
    target_calories: float = Field(gt=0)
    target_protein_grams: float = Field(ge=0)
    target_fat_grams: float = Field(ge=0)
    target_carb_grams: float = Field(ge=0)


class DietBase(BaseModel):
    meals_count: int = Field(ge=3, le=6)
    target_calories: float = Field(gt=0)
    protein_grams: float = Field(ge=0)
    fat_grams: float = Field(ge=0)
    carb_grams: float = Field(ge=0)
    distribution_percentages: list[float] = Field(default_factory=list)
    training_time_of_day: TrainingTimeOfDay | None = None
    training_optimization_applied: bool = False


class DailyDiet(DietBase):
    id: str
    created_at: datetime
    meals: list[DietMeal]

    model_config = ConfigDict(from_attributes=True)


class DietListItem(DietBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DietListResponse(BaseModel):
    diets: list[DietListItem]


def serialize_diet_meal(
    document: dict[str, Any],
    distribution_percentage: float | None = None,
) -> DietMeal:
    meal_distribution_percentage = document.get("distribution_percentage", distribution_percentage)
    return DietMeal(
        meal_number=document["meal_number"],
        distribution_percentage=meal_distribution_percentage,
        target_calories=document["target_calories"],
        target_protein_grams=document["target_protein_grams"],
        target_fat_grams=document["target_fat_grams"],
        target_carb_grams=document["target_carb_grams"],
    )


def serialize_daily_diet(document: dict[str, Any]) -> DailyDiet:
    distribution_percentages = _derive_distribution_percentages(document)
    meals = [
        serialize_diet_meal(
            meal,
            distribution_percentages[index] if index < len(distribution_percentages) else None,
        )
        for index, meal in enumerate(document["meals"])
    ]

    return DailyDiet(
        id=str(document["_id"]),
        created_at=document["created_at"],
        meals_count=document["meals_count"],
        target_calories=document["target_calories"],
        protein_grams=document["protein_grams"],
        fat_grams=document["fat_grams"],
        carb_grams=document["carb_grams"],
        distribution_percentages=distribution_percentages,
        training_time_of_day=document.get("training_time_of_day"),
        training_optimization_applied=document.get("training_optimization_applied", False),
        meals=meals,
    )


def serialize_diet_list_item(document: dict[str, Any]) -> DietListItem:
    distribution_percentages = _derive_distribution_percentages(document)
    return DietListItem(
        id=str(document["_id"]),
        created_at=document["created_at"],
        meals_count=document["meals_count"],
        target_calories=document["target_calories"],
        protein_grams=document["protein_grams"],
        fat_grams=document["fat_grams"],
        carb_grams=document["carb_grams"],
        distribution_percentages=distribution_percentages,
        training_time_of_day=document.get("training_time_of_day"),
        training_optimization_applied=document.get("training_optimization_applied", False),
    )
