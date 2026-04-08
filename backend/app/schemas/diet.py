"""Schemas for generated daily diets."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DietGenerateRequest(BaseModel):
    meals_count: int = Field(ge=3, le=6)


class DietMeal(BaseModel):
    meal_number: int = Field(ge=1)
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


def serialize_diet_meal(document: dict[str, Any]) -> DietMeal:
    return DietMeal(
        meal_number=document["meal_number"],
        target_calories=document["target_calories"],
        target_protein_grams=document["target_protein_grams"],
        target_fat_grams=document["target_fat_grams"],
        target_carb_grams=document["target_carb_grams"],
    )


def serialize_daily_diet(document: dict[str, Any]) -> DailyDiet:
    return DailyDiet(
        id=str(document["_id"]),
        created_at=document["created_at"],
        meals_count=document["meals_count"],
        target_calories=document["target_calories"],
        protein_grams=document["protein_grams"],
        fat_grams=document["fat_grams"],
        carb_grams=document["carb_grams"],
        meals=[serialize_diet_meal(meal) for meal in document["meals"]],
    )


def serialize_diet_list_item(document: dict[str, Any]) -> DietListItem:
    return DietListItem(
        id=str(document["_id"]),
        created_at=document["created_at"],
        meals_count=document["meals_count"],
        target_calories=document["target_calories"],
        protein_grams=document["protein_grams"],
        fat_grams=document["fat_grams"],
        carb_grams=document["carb_grams"],
    )
