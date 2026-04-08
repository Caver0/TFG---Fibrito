"""Business logic for weight tracking, weekly grouping, and progress summaries."""
from collections import defaultdict
from decimal import Decimal
from datetime import UTC, date, datetime

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.progress import ProgressSummary, WeeklyAverage
from app.schemas.weight import WeightEntry, WeightEntryCreate, serialize_weight_entry


def create_weight_entry(database, user_id: str, payload: WeightEntryCreate) -> WeightEntry:
    entry_date = payload.date or datetime.now(UTC).date()
    weight_document = {
        "user_id": ObjectId(user_id),
        "weight": payload.weight,
        "date": entry_date.isoformat(),
        "created_at": datetime.now(UTC),
    }
    inserted = database.weight_logs.insert_one(weight_document)
    created_entry = database.weight_logs.find_one({"_id": inserted.inserted_id})
    return serialize_weight_entry(created_entry)


def list_weight_entries(database, user_id: str) -> list[WeightEntry]:
    documents = database.weight_logs.find(
        {"user_id": ObjectId(user_id)}
    ).sort([("date", 1), ("created_at", 1)])
    return [serialize_weight_entry(document) for document in documents]


def delete_weight_entry(database, user_id: str, entry_id: str) -> None:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight entry not found",
        )

    entry_object_id = ObjectId(entry_id)
    existing_entry = database.weight_logs.find_one({"_id": entry_object_id})
    if not existing_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight entry not found",
        )

    if existing_entry["user_id"] != ObjectId(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to delete this weight entry",
        )

    database.weight_logs.delete_one({"_id": entry_object_id})


def build_progress_summary(entries: list[WeightEntry]) -> ProgressSummary:
    if not entries:
        return ProgressSummary(
            latest_weight=None,
            first_weight=None,
            total_change=None,
            number_of_entries=0,
            latest_entry_date=None,
        )

    first_entry = entries[0]
    latest_entry = entries[-1]
    total_change = float(
        Decimal(str(latest_entry.weight)) - Decimal(str(first_entry.weight))
    )

    return ProgressSummary(
        latest_weight=latest_entry.weight,
        first_weight=first_entry.weight,
        total_change=total_change,
        number_of_entries=len(entries),
        latest_entry_date=latest_entry.date,
    )


def get_week_label(iso_year: int, iso_week: int) -> str:
    return f"{iso_year}-W{iso_week:02d}"


def get_week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    start_date = date.fromisocalendar(iso_year, iso_week, 1)
    end_date = date.fromisocalendar(iso_year, iso_week, 7)
    return start_date, end_date


def group_weight_entries_by_week(entries: list[WeightEntry]) -> dict[tuple[int, int], list[WeightEntry]]:
    grouped_entries: dict[tuple[int, int], list[WeightEntry]] = defaultdict(list)
    for entry in entries:
        iso_year, iso_week, _ = entry.date.isocalendar()
        grouped_entries[(iso_year, iso_week)].append(entry)
    return grouped_entries


def calculate_weekly_averages(
    entries: list[WeightEntry],
    reference_date: date | None = None,
) -> list[WeeklyAverage]:
    grouped_entries = group_weight_entries_by_week(entries)
    today = reference_date or datetime.now(UTC).date()
    weekly_averages: list[WeeklyAverage] = []

    for (iso_year, iso_week), week_entries in sorted(grouped_entries.items()):
        start_date, end_date = get_week_bounds(iso_year, iso_week)
        average_weight = float(
            sum(Decimal(str(entry.weight)) for entry in week_entries) / Decimal(len(week_entries))
        )
        weekly_averages.append(
            WeeklyAverage(
                week_label=get_week_label(iso_year, iso_week),
                iso_year=iso_year,
                iso_week=iso_week,
                start_date=start_date,
                end_date=end_date,
                average_weight=average_weight,
                entry_count=len(week_entries),
                is_complete=end_date < today,
            )
        )

    return weekly_averages


def get_last_two_weeks_for_analysis(
    weekly_averages: list[WeeklyAverage],
) -> tuple[WeeklyAverage, WeeklyAverage] | None:
    complete_weeks = [week for week in weekly_averages if week.is_complete]
    if len(complete_weeks) < 2:
        return None

    return complete_weeks[-2], complete_weeks[-1]
