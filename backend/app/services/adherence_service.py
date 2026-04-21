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
MODIFIED_ADHERENCE_SCORE = Decimal(str(ADHERENCE_SCORE_BY_STATUS["modified"]))
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
            "Baja adherencia: esta semana no hay una dieta valida con comidas planificadas "
            "para interpretar con confianza la tendencia del peso."
        )

    if total_meals_registered == 0:
        return (
            "Baja adherencia: no hay registros de cumplimiento en la dieta valida de esta "
            "semana, asi que la tendencia del peso no permite valorar con confianza si el plan "
            "esta bien ajustado."
        )

    adherence_level = classify_adherence_level(weekly_adherence_factor)
    if tracking_coverage_percentage < 60:
        if adherence_level == "alta":
            return (
                "Alta adherencia en las comidas registradas, pero faltan bastantes registros "
                "esta semana, asi que la tendencia del peso solo se puede interpretar de forma parcial."
            )
        if adherence_level == "media":
            return (
                "Adherencia media en las comidas registradas y cobertura semanal baja; "
                "la tendencia del peso solo se puede interpretar de forma parcial."
            )
        return (
            "Baja adherencia y cobertura semanal baja: la tendencia del peso no permite "
            "evaluar con confianza si el plan esta bien ajustado."
        )

    if adherence_level == "alta":
        return (
            "Alta adherencia: la tendencia del peso semanal parece representar bien la respuesta "
            "al plan actual."
        )
    if adherence_level == "media":
        return (
            "Adherencia media: la tendencia del peso puede estar parcialmente afectada por "
            "modificaciones u omisiones."
        )
    return (
        "Baja adherencia: la tendencia del peso no permite evaluar con confianza si el plan "
        "esta bien ajustado."
    )


def _get_user_object_id(user_id: str) -> ObjectId:
    return ObjectId(user_id)


def _get_day_end_boundary(target_date: date) -> datetime:
    return datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=UTC)


def _get_day_start_boundary(target_date: date) -> datetime:
    return datetime.combine(target_date, time.min, tzinfo=UTC)


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


def _calculate_recorded_score_total(*, completed_meals: int, modified_meals: int) -> Decimal:
    return Decimal(completed_meals) + (Decimal(modified_meals) * MODIFIED_ADHERENCE_SCORE)


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
    start_boundary = _get_day_start_boundary(target_date)
    end_boundary = _get_day_end_boundary(target_date)
    document = database.diets.find_one(
        {
            "user_id": _get_user_object_id(user_id),
            "valid_from": {"$lt": end_boundary},
            "$or": [
                {"valid_to": None},
                {"valid_to": {"$exists": False}},
                {"valid_to": {"$gte": start_boundary}},
            ],
        },
        sort=[("valid_from", -1), ("created_at", -1)],
    )
    if document is not None:
        return document

    return database.diets.find_one(
        {
            "user_id": _get_user_object_id(user_id),
            "is_active": {"$exists": False},
            "created_at": {"$lt": end_boundary},
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
    planned_score_total = _calculate_recorded_score_total(
        completed_meals=completed_meals,
        modified_meals=modified_meals,
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


def _filter_adherence_documents_for_diet(
    adherence_documents: list[dict[str, Any]],
    diet_document: dict[str, Any],
) -> list[dict[str, Any]]:
    diet_id = str(diet_document["_id"])
    return [
        document
        for document in adherence_documents
        if str(document.get("diet_id")) == diet_id
    ]


def _build_daily_summary_for_valid_diet(
    database,
    *,
    user_id: str,
    target_date: date,
    adherence_documents: list[dict[str, Any]],
) -> DailyAdherenceSummary:
    valid_diet_document = get_active_diet_document_for_date(database, user_id, target_date)
    if valid_diet_document is None:
        return _build_empty_daily_summary(target_date)

    return _build_diet_adherence_response(
        user_id=user_id,
        diet_document=valid_diet_document,
        target_date=target_date,
        adherence_documents=_filter_adherence_documents_for_diet(
            adherence_documents,
            valid_diet_document,
        ),
    ).daily_summary


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
    return _build_daily_summary_for_valid_diet(
        database,
        user_id=user_id,
        target_date=resolved_date,
        adherence_documents=adherence_documents,
    )


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
    documents_by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for document in adherence_documents:
        documents_by_date[date.fromisoformat(document["date"])].append(document)

    days_with_records = 0
    completed_meals = 0
    omitted_meals = 0
    modified_meals = 0
    pending_meals = 0
    total_planned_meals = 0
    total_meals_registered = 0

    for day_offset in range(7):
        current_date = start_date + timedelta(days=day_offset)
        current_day_summary = _build_daily_summary_for_valid_diet(
            database,
            user_id=user_id,
            target_date=current_date,
            adherence_documents=documents_by_date.get(current_date, []),
        )
        if current_day_summary.total_meals == 0:
            continue

        total_planned_meals += current_day_summary.total_meals
        total_meals_registered += current_day_summary.registered_meals
        completed_meals += current_day_summary.completed_meals
        omitted_meals += current_day_summary.omitted_meals
        modified_meals += current_day_summary.modified_meals
        pending_meals += current_day_summary.pending_meals
        if current_day_summary.registered_meals > 0:
            days_with_records += 1

    recorded_score_total = _calculate_recorded_score_total(
        completed_meals=completed_meals,
        modified_meals=modified_meals,
    )
    weekly_adherence_factor = (
        round_adherence_value(
            recorded_score_total / Decimal(total_meals_registered),
            precision="0.0001",
        )
        if total_meals_registered > 0
        else 0.0
    )

    adherence_percentage = (
        round_adherence_value(
            (
                recorded_score_total
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

    tracking_coverage_factor = (
        round_adherence_value(
            Decimal(total_meals_registered) / Decimal(total_planned_meals),
            precision="0.0001",
        )
        if total_planned_meals > 0
        else 0.0
    )

    confidence_factor = round_adherence_value(
        Decimal(str(weekly_adherence_factor)) * Decimal(str(tracking_coverage_factor)),
        precision="0.0001",
    )

    confidence_percentage = round_adherence_value(
        Decimal(str(confidence_factor)) * Decimal("100")
    )

    adherence_level = classify_adherence_level(weekly_adherence_factor)

    return WeeklyAdherenceSummary(
        reference_date=resolved_reference_date,
        week_label=build_week_label(resolved_reference_date),
        start_date=start_date,
        end_date=end_date,
        days_with_records=days_with_records,
        total_planned_meals=total_planned_meals,
        total_meals_registered=total_meals_registered,
        completed_meals=completed_meals,
        omitted_meals=omitted_meals,
        modified_meals=modified_meals,
        pending_meals=pending_meals,
        adherence_percentage=adherence_percentage,
        tracking_coverage_percentage=tracking_coverage_percentage,
        weekly_adherence_factor=weekly_adherence_factor,
        tracking_coverage_factor=tracking_coverage_factor,
        confidence_factor=confidence_factor,
        confidence_percentage=confidence_percentage,
        adherence_level=adherence_level,
        interpretation_message=build_adherence_interpretation(
            weekly_adherence_factor=weekly_adherence_factor,
            total_meals_registered=total_meals_registered,
            total_planned_meals=total_planned_meals,
            tracking_coverage_percentage=tracking_coverage_percentage,
        ),
    )
