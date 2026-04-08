"""Schemas for basic progress summary."""
from datetime import date

from pydantic import BaseModel


class ProgressSummary(BaseModel):
    latest_weight: float | None
    first_weight: float | None
    total_change: float | None
    number_of_entries: int
    latest_entry_date: date | None
