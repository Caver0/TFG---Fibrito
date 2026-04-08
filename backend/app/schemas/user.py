"""User schemas and Mongo document serialization helpers."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

SexType = Literal["Masculino", "Femenino"]
GoalType = Literal["perder_grasa", "mantener_peso", "ganar_masa"]


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
    preferences: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)


class UserInDB(UserBase):
    password_hash: str
    created_at: datetime


class UserPublic(UserBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def serialize_user(document: dict[str, Any]) -> UserPublic:
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
        preferences=document.get("preferences", []),
        restrictions=document.get("restrictions", []),
    )
