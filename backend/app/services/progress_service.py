"""Business logic for weight tracking, weekly grouping, and progress summaries."""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from datetime import UTC, date, datetime

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.schemas.progress import ProgressSummary, WeeklyAverage
from app.schemas.weight import WeightEntry, WeightEntryCreate, serialize_weight_entry


WEIGHT_ENTRY_NOT_FOUND_DETAIL = "No se encontro el registro de peso"
WEIGHT_ENTRY_DUPLICATE_DATE_DETAIL = "Ya existe un registro de peso para esa fecha"
WEIGHT_ENTRY_DELETE_FORBIDDEN_DETAIL = "No tienes permiso para eliminar este registro de peso"
WEIGHT_ENTRY_UPDATE_FORBIDDEN_DETAIL = "No tienes permiso para editar este registro de peso"


def _get_weight_entry_or_raise(database, user_object_id: ObjectId, entry_id: str, forbidden_detail: str) -> dict:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WEIGHT_ENTRY_NOT_FOUND_DETAIL,
        )

    existing_entry = database.weight_logs.find_one({"_id": ObjectId(entry_id)})
    if not existing_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WEIGHT_ENTRY_NOT_FOUND_DETAIL,
        )

    if existing_entry["user_id"] != user_object_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=forbidden_detail,
        )

    return existing_entry


def _ensure_unique_weight_entry_date(
    database,
    user_object_id: ObjectId,
    entry_date: date,
    excluded_entry_id: ObjectId | None = None,
) -> None:
    query = {
        "user_id": user_object_id,
        "date": entry_date.isoformat(),
    }
    if excluded_entry_id is not None:
        query["_id"] = {"$ne": excluded_entry_id}

    if database.weight_logs.find_one(query):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=WEIGHT_ENTRY_DUPLICATE_DATE_DETAIL,
        )


def _sync_user_current_weight(database, user_object_id: ObjectId) -> None:
    latest_entry = database.weight_logs.find_one(
        {"user_id": user_object_id},
        sort=[("date", -1), ("created_at", -1)],
    )

    if latest_entry is None:
        # Si ya no quedan pesos, se conserva el valor actual del perfil.
        return

    database.users.update_one(
        {"_id": user_object_id},
        {"$set": {"current_weight": latest_entry["weight"]}},
    )


def create_weight_entry(database, user_id: str, payload: WeightEntryCreate) -> WeightEntry:
    user_object_id = ObjectId(user_id)
    entry_date = payload.date or datetime.now(UTC).date()
    _ensure_unique_weight_entry_date(database, user_object_id, entry_date)

    weight_document = {
        "user_id": user_object_id,
        "weight": payload.weight,
        "date": entry_date.isoformat(),
        "created_at": datetime.now(UTC),
    }

    try:
        inserted = database.weight_logs.insert_one(weight_document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=WEIGHT_ENTRY_DUPLICATE_DATE_DETAIL,
        ) from exc

    _sync_user_current_weight(database, user_object_id)
    created_entry = database.weight_logs.find_one({"_id": inserted.inserted_id})
    return serialize_weight_entry(created_entry)


def update_weight_entry(database, user_id: str, entry_id: str, payload: WeightEntryCreate) -> WeightEntry:
    user_object_id = ObjectId(user_id)
    existing_entry = _get_weight_entry_or_raise(
        database,
        user_object_id,
        entry_id,
        WEIGHT_ENTRY_UPDATE_FORBIDDEN_DETAIL,
    )
    entry_date = payload.date or existing_entry["date"]
    if isinstance(entry_date, str):
        entry_date = date.fromisoformat(entry_date)

    _ensure_unique_weight_entry_date(database, user_object_id, entry_date, existing_entry["_id"])

    try:
        updated_entry = database.weight_logs.find_one_and_update(
            {"_id": existing_entry["_id"]},
            {
                "$set": {
                    "weight": payload.weight,
                    "date": entry_date.isoformat(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=WEIGHT_ENTRY_DUPLICATE_DATE_DETAIL,
        ) from exc

    if not updated_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=WEIGHT_ENTRY_NOT_FOUND_DETAIL,
        )

    _sync_user_current_weight(database, user_object_id)
    return serialize_weight_entry(updated_entry)


def list_weight_entries(database, user_id: str) -> list[WeightEntry]:
    documents = database.weight_logs.find(
        {"user_id": ObjectId(user_id)}
    ).sort([("date", 1), ("created_at", 1)])
    return [serialize_weight_entry(document) for document in documents]


def delete_weight_entry(database, user_id: str, entry_id: str) -> None:
    user_object_id = ObjectId(user_id)
    existing_entry = _get_weight_entry_or_raise(
        database,
        user_object_id,
        entry_id,
        WEIGHT_ENTRY_DELETE_FORBIDDEN_DETAIL,
    )
    database.weight_logs.delete_one({"_id": existing_entry["_id"]})
    _sync_user_current_weight(database, user_object_id)


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


def round_progress_value(value: float | None) -> float | None:
    if value is None:
        return None

    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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


def serialize_weekly_average(average: WeeklyAverage) -> WeeklyAverage:
    return WeeklyAverage(
        week_label=average.week_label,
        iso_year=average.iso_year,
        iso_week=average.iso_week,
        start_date=average.start_date,
        end_date=average.end_date,
        average_weight=round_progress_value(average.average_weight),
        entry_count=average.entry_count,
        is_complete=average.is_complete,
    )


def serialize_weekly_averages(weekly_averages: list[WeeklyAverage]) -> list[WeeklyAverage]:
    return [serialize_weekly_average(average) for average in weekly_averages]


def get_last_two_weeks_for_analysis(
    weekly_averages: list[WeeklyAverage],
) -> tuple[WeeklyAverage, WeeklyAverage] | None:
    complete_weeks = [week for week in weekly_averages if week.is_complete]
    if len(complete_weeks) < 2:
        return None

    return complete_weeks[-2], complete_weeks[-1]
