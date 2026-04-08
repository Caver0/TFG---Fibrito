"""Schemas de usuario y serialización de documentos Mongo."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    age: int | None = Field(default=None, ge=0, le=120)
    sex: str | None = Field(default=None, max_length=50)
    height: float | None = Field(default=None, gt=0)
    current_weight: float | None = Field(default=None, gt=0)
    activity_level: str | None = Field(default=None, max_length=100)
    goal: str | None = Field(default=None, max_length=150)
    preferences: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


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
        activity_level=document.get("activity_level"),
        goal=document.get("goal"),
        preferences=document.get("preferences", []),
        restrictions=document.get("restrictions", []),
    )
