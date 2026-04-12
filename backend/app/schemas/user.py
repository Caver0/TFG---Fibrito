"""User schemas and Mongo document serialization helpers."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

SexType = Literal["Masculino", "Femenino"]
GoalType = Literal["perder_grasa", "mantener_peso", "ganar_masa"]


class FoodPreferencesProfile(BaseModel):
    preferred_foods: list[str] = Field(default_factory=list)
    disliked_foods: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)


class FoodPreferencesUpdate(FoodPreferencesProfile):
    pass


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    age: int | None = Field(default=None, gt=0, le=120)
    sex: SexType | None = None
    height: float | None = Field(default=None, gt=0)
    current_weight: float | None = Field(default=None, gt=0)
    training_days_per_week: int | None = Field(default=None, ge=0, le=7)
    goal: GoalType | None = None
    target_calories: float | None = Field(default=None, gt=0)
    food_preferences: FoodPreferencesProfile = Field(default_factory=FoodPreferencesProfile)


class UserInDB(UserBase):
    password_hash: str
    created_at: datetime


class UserPublic(UserBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def serialize_user(document: dict[str, Any]) -> UserPublic:
    serialized_food_preferences = FoodPreferencesProfile(
        preferred_foods=document.get("food_preferences", {}).get("preferred_foods", document.get("preferences", [])),
        disliked_foods=document.get("food_preferences", {}).get("disliked_foods", []),
        dietary_restrictions=document.get("food_preferences", {}).get(
            "dietary_restrictions",
            document.get("restrictions", []),
        ),
        allergies=document.get("food_preferences", {}).get("allergies", []),
    )

    return UserPublic(
        id=str(document["_id"]),
        name=document["name"],
        email=document["email"],
        created_at=document["created_at"],
        age=document.get("age"),
        sex=document.get("sex"),
        height=document.get("height"),
        current_weight=document.get("current_weight"),
        training_days_per_week=document.get("training_days_per_week"),
        goal=document.get("goal"),
        target_calories=document.get("target_calories"),
        food_preferences=serialized_food_preferences,
    )
