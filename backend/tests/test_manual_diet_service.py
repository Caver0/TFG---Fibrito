from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.schemas.diet import ManualDietCreateRequest
from app.schemas.user import UserPublic
from app.services.manual_diet_service import build_manual_diet_payload


def _build_user() -> UserPublic:
    return UserPublic(
        id="6625b8b4d7a9e6b4d4a0f101",
        name="Jorge",
        email="jorge@example.com",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        age=29,
        sex="Masculino",
        height=178,
        current_weight=78,
        training_days_per_week=4,
        goal="mantener_peso",
        target_calories=2400,
    )


def test_build_manual_diet_payload_marks_diet_as_manual_and_recalculates_totals():
    payload = ManualDietCreateRequest(
        meals_count=3,
        meals=[
            {"meal_number": 1, "foods": [{"food_code": "chicken_breast", "quantity": 150}]},
            {"meal_number": 2, "foods": [{"food_code": "rice", "quantity": 200}]},
            {"meal_number": 3, "foods": [{"food_code": "avocado", "quantity": 50}]},
        ],
    )
    catalog_lookup = {
        "chicken_breast": {
            "code": "chicken_breast",
            "display_name": "Pechuga de pollo",
            "category": "proteinas",
            "reference_amount": 100,
            "reference_unit": "g",
            "grams_per_reference": 100,
            "calories": 120,
            "protein_grams": 24,
            "fat_grams": 2,
            "carb_grams": 0,
            "source": "internal_catalog",
            "origin_source": "internal_catalog",
        },
        "rice": {
            "code": "rice",
            "display_name": "Arroz cocido",
            "category": "carbohidratos",
            "reference_amount": 100,
            "reference_unit": "g",
            "grams_per_reference": 100,
            "calories": 130,
            "protein_grams": 2.5,
            "fat_grams": 0.3,
            "carb_grams": 28,
            "source": "internal_catalog",
            "origin_source": "internal_catalog",
        },
        "avocado": {
            "code": "avocado",
            "display_name": "Aguacate",
            "category": "grasas",
            "reference_amount": 100,
            "reference_unit": "g",
            "grams_per_reference": 100,
            "calories": 160,
            "protein_grams": 2,
            "fat_grams": 15,
            "carb_grams": 9,
            "source": "internal_catalog",
            "origin_source": "internal_catalog",
        },
    }

    with patch(
        "app.services.manual_diet_service.get_food_by_code",
        side_effect=lambda _database, code: catalog_lookup.get(code),
    ):
        manual_diet = build_manual_diet_payload(object(), _build_user(), payload)

    assert manual_diet["diet_mode"] == "manual"
    assert manual_diet["meals_count"] == 3
    assert manual_diet["actual_calories"] == 520.0
    assert manual_diet["actual_protein_grams"] == 42.0
    assert manual_diet["actual_fat_grams"] == 11.1
    assert manual_diet["actual_carb_grams"] == 60.5
    assert manual_diet["distribution_percentages"] == [30.0, 40.0, 30.0]
    assert [meal["meal_number"] for meal in manual_diet["meals"]] == [1, 2, 3]
    assert manual_diet["meals"][0]["foods"][0]["name"] == "Pechuga de pollo"
    assert manual_diet["meals"][0]["foods"][0]["grams"] == 150.0
    assert manual_diet["meals"][1]["actual_calories"] == 260.0
    assert manual_diet["meals"][2]["actual_fat_grams"] == 7.5


def test_build_manual_diet_payload_rejects_empty_meals():
    payload = ManualDietCreateRequest(
        meals_count=3,
        meals=[
            {"meal_number": 1, "foods": [{"food_code": "rice", "quantity": 100}]},
            {"meal_number": 2, "foods": []},
            {"meal_number": 3, "foods": [{"food_code": "avocado", "quantity": 50}]},
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        build_manual_diet_payload(object(), _build_user(), payload)

    assert exc_info.value.status_code == 422
    assert "Meal 2" in exc_info.value.detail
