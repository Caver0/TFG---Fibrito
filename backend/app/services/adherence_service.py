"""Business logic for diet adherence tracking and interpretability summaries."""
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.adherence import (
    DailyAdherenceSummary,
    DietAdherenceResponse,
    MealAdherenceRecord,
    MealAdherenceStatus,
    MealAdherenceUpsertRequest,
    WeeklyAdherenceSummary,
    normalize_adherence_note,
    serialize_meal_adherence_record,
)
from app.services.diet_service import get_user_diet_document_by_id

ADHERENCE_SCORE_BY_STATUS = {
    "completed": 1.0,
    "modified": 0.5,
    "omitted": 0.0,
}
HIGH_ADHERENCE_THRESHOLD = 0.85
MEDIUM_ADHERENCE_THRESHOLD = 0.60


def round_adherence_value(value: float | Decimal | None, precision: str = "0.01") -> float:
    if value is None:
        value = 0.0

    return float(Decimal(str(value)).quantize(Decimal(precision), rounding=ROUND_HALF_UP))


def resolve_adherence_date(value: date | None) -> date:
    return value or datetime.now(UTC).date()


def resolve_week_reference_date(
    *,
    reference_date: date | None = None,
    week_label: str | None = None,
) -> date:
    if not week_label:
        return resolve_adherence_date(reference_date)

    normalized_label = str(week_label).strip()
    try:
        iso_year_raw, iso_week_raw = normalized_label.split("-W", maxsplit=1)
        iso_year = int(iso_year_raw)
        iso_week = int(iso_week_raw)
        return date.fromisocalendar(iso_year, iso_week, 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid week_label. Expected format YYYY-Www.",
        ) from exc


def get_week_bounds(reference_date: date) -> tuple[date, date]:
    start_date = reference_date - timedelta(days=reference_date.weekday())
    end_date = start_date + timedelta(days=6)
    return start_date, end_date


def build_week_label(reference_date: date) -> str:
    iso_year, iso_week, _ = reference_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def compute_adherence_score(status: MealAdherenceStatus) -> float | None:
    if status == "pending":
        return None

    return ADHERENCE_SCORE_BY_STATUS[status]


def classify_adherence_level(weekly_adherence_factor: float) -> str:
    if weekly_adherence_factor >= HIGH_ADHERENCE_THRESHOLD:
        return "alta"
    if weekly_adherence_factor >= MEDIUM_ADHERENCE_THRESHOLD:
        return "media"
    return "baja"


def build_adherence_interpretation(
    *,
    weekly_adherence_factor: float,
    total_meals_registered: int,
    total_planned_meals: int,
    tracking_coverage_percentage: float,
) -> str:
    if total_planned_meals == 0:
        return (
            "Baja adherencia: todavia no hay una dieta activa con registros suficientes "
            "para interpretar con confianza la tendencia del peso semanal."
        )

    if total_meals_registered == 0:
        return (
            "Baja adherencia: no hay registros de cumplimiento esta semana, asi que la "
            "tendencia del peso no permite valorar con confianza si el plan esta bien ajustado."
        )

    adherence_level = classify_adherence_level(weekly_adherence_factor)
    if adherence_level == "alta":
        base_message = (
            "Alta adherencia: la tendencia del peso semanal parece representar bien la respuesta "
            "al plan actual."
        )
    elif adherence_level == "media":
        base_message = (
            "Adherencia media: la tendencia del peso puede estar parcialmente afectada por "
            "modificaciones u omisiones."
        )
    else:
        base_message = (
            "Baja adherencia: la tendencia del peso no permite evaluar con confianza si el plan "
            "esta bien ajustado."
        )

    if total_planned_meals > 0 and tracking_coverage_percentage < 60:
        return (
            f"{base_message} Ademas, faltan registros en varias comidas de la semana, "
            "asi que la lectura sigue siendo parcial."
        )

    return base_message


def _get_user_object_id(user_id: str) -> ObjectId:
    return ObjectId(user_id)


def _get_day_end_boundary(target_date: date) -> datetime:
    return datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=UTC)


def _get_diet_object_id(diet_id: str) -> ObjectId:
    if not ObjectId.is_valid(diet_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet not found",
        )

    return ObjectId(diet_id)


def _validate_meal_number_exists(diet_document: dict[str, Any], meal_number: int) -> None:
    available_meal_numbers = {
        int(meal["meal_number"])
        for meal in diet_document.get("meals", [])
    }
    if meal_number not in available_meal_numbers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The provided meal_number does not exist in this diet",
        )


def _build_pending_meal_record(
    *,
    user_id: str,
    diet_id: str,
    meal_number: int,
    target_date: date,
) -> MealAdherenceRecord:
    return MealAdherenceRecord(
        id=None,
        user_id=user_id,
        diet_id=diet_id,
        meal_number=meal_number,
        date=target_date,
        status="pending",
        note=None,
        adherence_score=None,
        is_recorded=False,
        created_at=None,
        updated_at=None,
    )


def _build_daily_summary(
    *,
    target_date: date,
    total_meals: int,
    meal_entries: list[MealAdherenceRecord],
    diet_id: str | None = None,
) -> DailyAdherenceSummary:
    completed_meals = sum(1 for entry in meal_entries if entry.status == "completed")
    omitted_meals = sum(1 for entry in meal_entries if entry.status == "omitted")
    modified_meals = sum(1 for entry in meal_entries if entry.status == "modified")
    pending_meals = sum(1 for entry in meal_entries if entry.status == "pending")
    registered_meals = completed_meals + omitted_meals + modified_meals
    total_score = sum(
        Decimal(str(entry.adherence_score))
        for entry in meal_entries
        if entry.adherence_score is not None
    )
    adherence_score = (
        round_adherence_value(total_score / Decimal(total_meals))
        if total_meals > 0
        else 0.0
    )

    return DailyAdherenceSummary(
        date=target_date,
        diet_id=diet_id,
        total_meals=total_meals,
        registered_meals=registered_meals,
        completed_meals=completed_meals,
        omitted_meals=omitted_meals,
        modified_meals=modified_meals,
        pending_meals=pending_meals,
        adherence_score=adherence_score,
        adherence_percentage=round_adherence_value(adherence_score * 100),
    )


def _build_empty_daily_summary(target_date: date, diet_id: str | None = None) -> DailyAdherenceSummary:
    return DailyAdherenceSummary(
        date=target_date,
        diet_id=diet_id,
        total_meals=0,
        registered_meals=0,
        completed_meals=0,
        omitted_meals=0,
        modified_meals=0,
        pending_meals=0,
        adherence_score=0.0,
        adherence_percentage=0.0,
    )


def _fetch_adherence_documents_for_date(
    database,
    *,
    user_id: str,
    target_date: date,
    diet_id: str | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "user_id": _get_user_object_id(user_id),
        "date": target_date.isoformat(),
    }
    if diet_id is not None:
        query["diet_id"] = _get_diet_object_id(diet_id)

    return list(
        database.diet_adherence.find(query).sort(
            [("meal_number", 1), ("updated_at", 1)]
        )
    )


def _fetch_adherence_documents_for_range(
    database,
    *,
    user_id: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    return list(
        database.diet_adherence.find(
            {
                "user_id": _get_user_object_id(user_id),
                "date": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat(),
                },
            }
        ).sort([("date", 1), ("meal_number", 1), ("updated_at", 1)])
    )


def _get_cached_diet_document(
    database,
    *,
    user_id: str,
    diet_id: str,
    diet_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if diet_id not in diet_cache:
        diet_cache[diet_id] = get_user_diet_document_by_id(database, user_id, diet_id)

    return diet_cache[diet_id]


def get_active_diet_document_for_date(database, user_id: str, target_date: date) -> dict[str, Any] | None:
    return database.diets.find_one(
        {
            "user_id": _get_user_object_id(user_id),
            "created_at": {"$lt": _get_day_end_boundary(target_date)},
        },
        sort=[("created_at", -1)],
    )


def _build_meal_entries_for_diet(
    *,
    user_id: str,
    diet_document: dict[str, Any],
    target_date: date,
    adherence_documents: list[dict[str, Any]],
) -> list[MealAdherenceRecord]:
    diet_id = str(diet_document["_id"])
    documents_by_meal_number = {
        int(document["meal_number"]): document
        for document in adherence_documents
    }

    meal_entries: list[MealAdherenceRecord] = []
    for meal in sorted(diet_document.get("meals", []), key=lambda item: item["meal_number"]):
        meal_number = int(meal["meal_number"])
        if meal_number in documents_by_meal_number:
            meal_entries.append(serialize_meal_adherence_record(documents_by_meal_number[meal_number]))
            continue

        meal_entries.append(
            _build_pending_meal_record(
                user_id=user_id,
                diet_id=diet_id,
                meal_number=meal_number,
                target_date=target_date,
            )
        )

    return meal_entries


def _build_diet_adherence_response(
    *,
    user_id: str,
    diet_document: dict[str, Any],
    target_date: date,
    adherence_documents: list[dict[str, Any]],
) -> DietAdherenceResponse:
    meal_entries = _build_meal_entries_for_diet(
        user_id=user_id,
        diet_document=diet_document,
        target_date=target_date,
        adherence_documents=adherence_documents,
    )
    diet_id = str(diet_document["_id"])
    daily_summary = _build_daily_summary(
        target_date=target_date,
        diet_id=diet_id,
        total_meals=len(diet_document.get("meals", [])),
        meal_entries=meal_entries,
    )

    return DietAdherenceResponse(
        diet_id=diet_id,
        date=target_date,
        total_meals=len(meal_entries),
        meals=meal_entries,
        daily_summary=daily_summary,
    )


def _aggregate_daily_summaries(
    target_date: date,
    daily_summaries: list[DailyAdherenceSummary],
) -> DailyAdherenceSummary:
    if not daily_summaries:
        return _build_empty_daily_summary(target_date)

    total_meals = sum(summary.total_meals for summary in daily_summaries)
    completed_meals = sum(summary.completed_meals for summary in daily_summaries)
    omitted_meals = sum(summary.omitted_meals for summary in daily_summaries)
    modified_meals = sum(summary.modified_meals for summary in daily_summaries)
    pending_meals = sum(summary.pending_meals for summary in daily_summaries)
    registered_meals = sum(summary.registered_meals for summary in daily_summaries)
    planned_score_total = (
        Decimal(completed_meals)
        + (Decimal(modified_meals) * Decimal("0.5"))
    )
    adherence_score = (
        round_adherence_value(planned_score_total / Decimal(total_meals))
        if total_meals > 0
        else 0.0
    )

    return DailyAdherenceSummary(
        date=target_date,
        diet_id=None,
        total_meals=total_meals,
        registered_meals=registered_meals,
        completed_meals=completed_meals,
        omitted_meals=omitted_meals,
        modified_meals=modified_meals,
        pending_meals=pending_meals,
        adherence_score=adherence_score,
        adherence_percentage=round_adherence_value(adherence_score * 100),
    )


def save_meal_adherence(
    database,
    user_id: str,
    payload: MealAdherenceUpsertRequest,
) -> MealAdherenceRecord:
    target_date = resolve_adherence_date(payload.date)
    diet_document = get_user_diet_document_by_id(database, user_id, payload.diet_id)
    _validate_meal_number_exists(diet_document, payload.meal_number)

    record_query = {
        "user_id": _get_user_object_id(user_id),
        "diet_id": _get_diet_object_id(payload.diet_id),
        "meal_number": payload.meal_number,
        "date": target_date.isoformat(),
    }

    if payload.status == "pending":
        database.diet_adherence.delete_one(record_query)
        return _build_pending_meal_record(
            user_id=user_id,
            diet_id=payload.diet_id,
            meal_number=payload.meal_number,
            target_date=target_date,
        )

    now = datetime.now(UTC)
    normalized_note = normalize_adherence_note(payload.note)
    adherence_score = compute_adherence_score(payload.status)
    existing_document = database.diet_adherence.find_one(record_query)
    persistable_payload = {
        **record_query,
        "status": payload.status,
        "note": normalized_note,
        "adherence_score": adherence_score,
        "updated_at": now,
    }

    if existing_document:
        database.diet_adherence.update_one(
            {"_id": existing_document["_id"]},
            {
                "$set": {
                    "status": persistable_payload["status"],
                    "note": persistable_payload["note"],
                    "adherence_score": persistable_payload["adherence_score"],
                    "updated_at": persistable_payload["updated_at"],
                }
            },
        )
        updated_document = database.diet_adherence.find_one({"_id": existing_document["_id"]})
        return serialize_meal_adherence_record(updated_document)

    inserted = database.diet_adherence.insert_one(
        {
            **persistable_payload,
            "created_at": now,
        }
    )
    created_document = database.diet_adherence.find_one({"_id": inserted.inserted_id})
    return serialize_meal_adherence_record(created_document)


def get_diet_adherence(
    database,
    user_id: str,
    diet_id: str,
    target_date: date | None = None,
) -> DietAdherenceResponse:
    resolved_date = resolve_adherence_date(target_date)
    diet_document = get_user_diet_document_by_id(database, user_id, diet_id)
    adherence_documents = _fetch_adherence_documents_for_date(
        database,
        user_id=user_id,
        target_date=resolved_date,
        diet_id=diet_id,
    )

    return _build_diet_adherence_response(
        user_id=user_id,
        diet_document=diet_document,
        target_date=resolved_date,
        adherence_documents=adherence_documents,
    )


def calculate_daily_adherence_summary(
    database,
    user_id: str,
    target_date: date | None = None,
    diet_id: str | None = None,
) -> DailyAdherenceSummary:
    resolved_date = resolve_adherence_date(target_date)
    if diet_id is not None:
        return get_diet_adherence(
            database,
            user_id=user_id,
            diet_id=diet_id,
            target_date=resolved_date,
        ).daily_summary

    adherence_documents = _fetch_adherence_documents_for_date(
        database,
        user_id=user_id,
        target_date=resolved_date,
    )
    if adherence_documents:
        grouped_documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for document in adherence_documents:
            grouped_documents[str(document["diet_id"])].append(document)

        if len(grouped_documents) == 1:
            only_diet_id = next(iter(grouped_documents))
            return get_diet_adherence(
                database,
                user_id=user_id,
                diet_id=only_diet_id,
                target_date=resolved_date,
            ).daily_summary

        diet_cache: dict[str, dict[str, Any]] = {}
        daily_summaries: list[DailyAdherenceSummary] = []
        for grouped_diet_id, grouped_records in grouped_documents.items():
            diet_document = _get_cached_diet_document(
                database,
                user_id=user_id,
                diet_id=grouped_diet_id,
                diet_cache=diet_cache,
            )
            daily_summaries.append(
                _build_diet_adherence_response(
                    user_id=user_id,
                    diet_document=diet_document,
                    target_date=resolved_date,
                    adherence_documents=grouped_records,
                ).daily_summary
            )

        return _aggregate_daily_summaries(resolved_date, daily_summaries)

    active_diet_document = get_active_diet_document_for_date(database, user_id, resolved_date)
    if active_diet_document is None:
        return _build_empty_daily_summary(resolved_date)

    return _build_diet_adherence_response(
        user_id=user_id,
        diet_document=active_diet_document,
        target_date=resolved_date,
        adherence_documents=[],
    ).daily_summary


def calculate_weekly_adherence_summary(
    database,
    user_id: str,
    *,
    reference_date: date | None = None,
    week_label: str | None = None,
) -> WeeklyAdherenceSummary:
    resolved_reference_date = resolve_week_reference_date(
        reference_date=reference_date,
        week_label=week_label,
    )
    start_date, end_date = get_week_bounds(resolved_reference_date)
    adherence_documents = _fetch_adherence_documents_for_range(
        database,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    diet_cache: dict[str, dict[str, Any]] = {}
    documents_by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for document in adherence_documents:
        documents_by_date[date.fromisoformat(document["date"])].append(document)

    completed_meals = 0
    omitted_meals = 0
    modified_meals = 0
    pending_meals = 0
    total_planned_meals = 0
    total_meals_registered = 0

    for day_offset in range(7):
        current_date = start_date + timedelta(days=day_offset)
        current_day_documents = documents_by_date.get(current_date, [])
        if current_day_documents:
            grouped_documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for document in current_day_documents:
                grouped_documents[str(document["diet_id"])].append(document)

            current_day_summaries: list[DailyAdherenceSummary] = []
            for grouped_diet_id, grouped_records in grouped_documents.items():
                diet_document = _get_cached_diet_document(
                    database,
                    user_id=user_id,
                    diet_id=grouped_diet_id,
                    diet_cache=diet_cache,
                )
                current_day_summaries.append(
                    _build_diet_adherence_response(
                        user_id=user_id,
                        diet_document=diet_document,
                        target_date=current_date,
                        adherence_documents=grouped_records,
                    ).daily_summary
                )

            current_day_summary = _aggregate_daily_summaries(current_date, current_day_summaries)
        else:
            active_diet_document = get_active_diet_document_for_date(database, user_id, current_date)
            if active_diet_document is None:
                continue

            current_day_summary = _build_diet_adherence_response(
                user_id=user_id,
                diet_document=active_diet_document,
                target_date=current_date,
                adherence_documents=[],
            ).daily_summary

        total_planned_meals += current_day_summary.total_meals
        total_meals_registered += current_day_summary.registered_meals
        completed_meals += current_day_summary.completed_meals
        omitted_meals += current_day_summary.omitted_meals
        modified_meals += current_day_summary.modified_meals
        pending_meals += current_day_summary.pending_meals

    recorded_scores = [
        Decimal(str(document["adherence_score"]))
        for document in adherence_documents
        if document.get("adherence_score") is not None
    ]
    weekly_adherence_factor = (
        round_adherence_value(sum(recorded_scores) / Decimal(len(recorded_scores)))
        if recorded_scores
        else 0.0
    )
    adherence_percentage = (
        round_adherence_value(
            (
                Decimal(completed_meals)
                + (Decimal(modified_meals) * Decimal("0.5"))
            )
            / Decimal(total_planned_meals)
            * Decimal("100")
        )
        if total_planned_meals > 0
        else 0.0
    )
    tracking_coverage_percentage = (
        round_adherence_value(
            Decimal(total_meals_registered) / Decimal(total_planned_meals) * Decimal("100")
        )
        if total_planned_meals > 0
        else 0.0
    )
    adherence_level = classify_adherence_level(weekly_adherence_factor)

    return WeeklyAdherenceSummary(
        reference_date=resolved_reference_date,
        week_label=build_week_label(resolved_reference_date),
        start_date=start_date,
        end_date=end_date,
        days_with_records=len(documents_by_date),
        total_planned_meals=total_planned_meals,
        total_meals_registered=total_meals_registered,
        completed_meals=completed_meals,
        omitted_meals=omitted_meals,
        modified_meals=modified_meals,
        pending_meals=pending_meals,
        adherence_percentage=adherence_percentage,
        tracking_coverage_percentage=tracking_coverage_percentage,
        weekly_adherence_factor=weekly_adherence_factor,
        adherence_level=adherence_level,
        interpretation_message=build_adherence_interpretation(
            weekly_adherence_factor=weekly_adherence_factor,
            total_meals_registered=total_meals_registered,
            total_planned_meals=total_planned_meals,
            tracking_coverage_percentage=tracking_coverage_percentage,
        ),
    )
