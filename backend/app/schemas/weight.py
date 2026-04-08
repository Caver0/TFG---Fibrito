"""Schemas for weight history entries."""
from datetime import date as date_type
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WeightEntryCreate(BaseModel):
    weight: float = Field(gt=0)
    date: date_type | None = None


class WeightEntry(BaseModel):
    id: str
    weight: float
    date: date_type
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WeightEntryList(BaseModel):
    entries: list[WeightEntry]


def serialize_weight_entry(document: dict[str, Any]) -> WeightEntry:
    return WeightEntry(
        id=str(document["_id"]),
        weight=document["weight"],
        date=document["date"],
        created_at=document["created_at"],
    )
