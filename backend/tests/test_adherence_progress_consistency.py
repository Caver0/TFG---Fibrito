from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

from bson import ObjectId

from app.schemas.progress import WeeklyAverage
from app.schemas.user import UserPublic
from app.services import adherence_service
from app.services.goal_adjustment_service import analyze_weekly_progress


def _build_diet_document(meal_numbers: list[int]) -> dict:
    return {
        "_id": ObjectId(),
        "created_at": datetime(2026, 4, 1, tzinfo=UTC),
        "meals": [{"meal_number": meal_number} for meal_number in meal_numbers],
    }


def _build_adherence_document(
    *,
    user_id: str,
    diet_id: ObjectId,
    meal_number: int,
    target_date: date,
    status: str,
) -> dict:
    return {
        "_id": ObjectId(),
        "user_id": ObjectId(user_id),
        "diet_id": diet_id,
        "meal_number": meal_number,
        "date": target_date.isoformat(),
        "status": status,
        "note": None,
        "adherence_score": adherence_service.compute_adherence_score(status),
        "created_at": datetime(2026, 4, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 1, tzinfo=UTC),
    }


def _build_user(**overrides) -> UserPublic:
    payload = {
        "id": str(ObjectId()),
        "name": "Jorge",
        "email": "jorge@example.com",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "goal": "mantener_peso",
        "target_calories": 2200,
    }
    payload.update(overrides)
    return UserPublic(**payload)


def test_daily_adherence_summary_uses_valid_diet_for_the_date():
    user_id = str(ObjectId())
    target_date = date(2026, 4, 13)
    valid_diet = _build_diet_document([1, 2, 3, 4])
    stale_diet = _build_diet_document([1, 2])
    stale_record = _build_adherence_document(
        user_id=user_id,
        diet_id=stale_diet["_id"],
        meal_number=1,
        target_date=target_date,
        status="completed",
    )

    with (
        patch(
            "app.services.adherence_service._fetch_adherence_documents_for_date",
            return_value=[stale_record],
        ),
        patch(
            "app.services.adherence_service.get_active_diet_document_for_date",
            return_value=valid_diet,
        ),
    ):
        summary = adherence_service.calculate_daily_adherence_summary(
            object(),
            user_id,
            target_date=target_date,
        )

    assert summary.diet_id == str(valid_diet["_id"])
    assert summary.total_meals == 4
    assert summary.registered_meals == 0
    assert summary.pending_meals == 4
    assert summary.adherence_percentage == 0.0


def test_weekly_adherence_summary_uses_valid_daily_diet_and_consistent_factors():
    user_id = str(ObjectId())
    reference_date = date(2026, 4, 15)
    monday = date(2026, 4, 13)
    valid_diet = _build_diet_document([1, 2, 3, 4])
    stale_diet = _build_diet_document([1, 2])
    documents = [
        _build_adherence_document(
            user_id=user_id,
            diet_id=stale_diet["_id"],
            meal_number=1,
            target_date=monday,
            status="completed",
        ),
        _build_adherence_document(
            user_id=user_id,
            diet_id=valid_diet["_id"],
            meal_number=1,
            target_date=monday,
            status="completed",
        ),
        _build_adherence_document(
            user_id=user_id,
            diet_id=valid_diet["_id"],
            meal_number=2,
            target_date=monday,
            status="modified",
        ),
    ]

    def _resolve_valid_diet(_database, _user_id, target_day):
        return valid_diet if target_day == monday else None

    with (
        patch(
            "app.services.adherence_service._fetch_adherence_documents_for_range",
            return_value=documents,
        ),
        patch(
            "app.services.adherence_service.get_active_diet_document_for_date",
            side_effect=_resolve_valid_diet,
        ),
    ):
        summary = adherence_service.calculate_weekly_adherence_summary(
            object(),
            user_id,
            reference_date=reference_date,
        )

    assert summary.week_label == "2026-W16"
    assert summary.days_with_records == 1
    assert summary.total_planned_meals == 4
    assert summary.total_meals_registered == 2
    assert summary.completed_meals == 1
    assert summary.modified_meals == 1
    assert summary.pending_meals == 2
    assert summary.adherence_percentage == 37.5
    assert summary.weekly_adherence_factor == 0.75
    assert summary.tracking_coverage_factor == 0.5
    assert summary.confidence_factor == 0.375
    assert summary.confidence_factor == round(
        summary.weekly_adherence_factor * summary.tracking_coverage_factor,
        4,
    )
    assert "registradas" in summary.interpretation_message
    assert "parcial" in summary.interpretation_message


def test_weekly_progress_returns_reference_week_even_when_it_cannot_analyze_yet():
    weekly_averages = [
        WeeklyAverage(
            week_label="2026-W16",
            iso_year=2026,
            iso_week=16,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 19),
            average_weight=80.2,
            entry_count=4,
            is_complete=True,
        )
    ]

    analysis = analyze_weekly_progress(_build_user(), weekly_averages)

    assert analysis.can_analyze is False
    assert analysis.current_week_label == "2026-W16"
    assert analysis.current_week_avg == 80.2
    assert analysis.previous_week_label is None


def test_weekly_progress_uses_confidence_to_block_unreliable_adjustments():
    weekly_averages = [
        WeeklyAverage(
            week_label="2026-W15",
            iso_year=2026,
            iso_week=15,
            start_date=date(2026, 4, 6),
            end_date=date(2026, 4, 12),
            average_weight=82.0,
            entry_count=7,
            is_complete=True,
        ),
        WeeklyAverage(
            week_label="2026-W16",
            iso_year=2026,
            iso_week=16,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 19),
            average_weight=82.1,
            entry_count=7,
            is_complete=True,
        ),
    ]

    analysis = analyze_weekly_progress(
        _build_user(goal="perder_grasa", current_weight=82.1),
        weekly_averages,
        adherence_level="alta",
        confidence_factor=0.42,
        tracking_coverage_percentage=48.0,
    )

    assert analysis.can_analyze is True
    assert analysis.progress_status == "needs_attention"
    assert analysis.adjustment_needed is False
    assert analysis.calorie_change == -150


def test_weekly_progress_keeps_adjustment_when_confidence_is_sufficient():
    weekly_averages = [
        WeeklyAverage(
            week_label="2026-W15",
            iso_year=2026,
            iso_week=15,
            start_date=date(2026, 4, 6),
            end_date=date(2026, 4, 12),
            average_weight=82.0,
            entry_count=7,
            is_complete=True,
        ),
        WeeklyAverage(
            week_label="2026-W16",
            iso_year=2026,
            iso_week=16,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 19),
            average_weight=82.1,
            entry_count=7,
            is_complete=True,
        ),
    ]

    analysis = analyze_weekly_progress(
        _build_user(goal="perder_grasa", current_weight=82.1),
        weekly_averages,
        adherence_level="alta",
        confidence_factor=0.89,
        tracking_coverage_percentage=96.0,
    )

    assert analysis.can_analyze is True
    assert analysis.progress_status == "needs_adjustment"
    assert analysis.adjustment_needed is True
    assert analysis.calorie_change == -150
