from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from app.schemas.diet import DailyDiet
from app.services.diet.persistence import activate_user_diet


def _build_food(name: str, code: str) -> dict:
    return {
        "food_code": code,
        "source": "internal_catalog",
        "origin_source": "internal_catalog",
        "spoonacular_id": None,
        "name": name,
        "category": "proteinas",
        "quantity": 150,
        "unit": "g",
        "grams": 150,
        "calories": 165,
        "protein_grams": 31,
        "fat_grams": 3.6,
        "carb_grams": 0,
    }


def _build_meal(meal_number: int, meal_label: str, food_code: str) -> dict:
    return {
        "meal_number": meal_number,
        "meal_slot": "main",
        "meal_role": "meal",
        "meal_label": meal_label,
        "distribution_percentage": 33.3,
        "target_calories": 800,
        "target_protein_grams": 60,
        "target_fat_grams": 20,
        "target_carb_grams": 70,
        "actual_calories": 790,
        "actual_protein_grams": 58,
        "actual_fat_grams": 19,
        "actual_carb_grams": 68,
        "calorie_difference": -10,
        "protein_difference": -2,
        "fat_difference": -1,
        "carb_difference": -2,
        "foods": [_build_food(f"Pechuga {meal_number}", food_code)],
    }


def _build_diet(*, diet_id: str, is_active: bool) -> DailyDiet:
    return DailyDiet(
        id=diet_id,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        diet_mode="manual",
        is_active=is_active,
        valid_from=datetime(2026, 4, 1, tzinfo=UTC),
        valid_to=None,
        adjusted_from_diet_id=None,
        meals_count=3,
        target_calories=2400,
        protein_grams=180,
        fat_grams=60,
        carb_grams=210,
        actual_calories=2370,
        actual_protein_grams=174,
        actual_fat_grams=57,
        actual_carb_grams=204,
        calorie_difference=-30,
        protein_difference=-6,
        fat_difference=-3,
        carb_difference=-6,
        distribution_percentages=[33.3, 33.3, 33.4],
        training_time_of_day=None,
        training_optimization_applied=False,
        food_data_source="internal_catalog",
        food_data_sources=["internal_catalog"],
        food_catalog_version=None,
        food_preferences_applied=False,
        applied_dietary_restrictions=[],
        applied_allergies=[],
        preferred_food_matches=0,
        diversity_strategy_applied=False,
        food_usage_summary={},
        food_filter_warnings=[],
        catalog_source_strategy="auto",
        spoonacular_attempted=False,
        spoonacular_attempts=0,
        spoonacular_hits=0,
        cache_hits=0,
        internal_fallbacks=0,
        resolved_foods_count=3,
        meals=[
            _build_meal(1, "Desayuno", "pollo_desayuno"),
            _build_meal(2, "Comida", "pollo_comida"),
            _build_meal(3, "Cena", "pollo_cena"),
        ],
    )


def test_activate_user_diet_clones_historical_diet_as_new_active_version():
    source_diet = _build_diet(
        diet_id="6625b8b4d7a9e6b4d4a0f301",
        is_active=False,
    )
    activated_diet = _build_diet(
        diet_id="6625b8b4d7a9e6b4d4a0f302",
        is_active=True,
    )

    with patch(
        "app.services.diet.persistence.get_user_diet_by_id",
        return_value=source_diet,
    ), patch(
        "app.services.diet.persistence.save_diet",
        return_value=activated_diet,
    ) as save_diet_mock:
        result = activate_user_diet(object(), "6625b8b4d7a9e6b4d4a0f101", source_diet.id)

    assert result == activated_diet
    save_diet_mock.assert_called_once()

    args, kwargs = save_diet_mock.call_args
    saved_payload = args[2]
    assert saved_payload["diet_mode"] == "manual"
    assert saved_payload["meals_count"] == 3
    assert saved_payload["meals"][0]["foods"][0]["name"] == "Pechuga 1"
    assert "id" not in saved_payload
    assert "created_at" not in saved_payload
    assert "is_active" not in saved_payload
    assert kwargs["adjusted_from_diet_id"] == source_diet.id


def test_activate_user_diet_returns_same_document_when_already_active():
    active_diet = _build_diet(
        diet_id="6625b8b4d7a9e6b4d4a0f303",
        is_active=True,
    )

    with patch(
        "app.services.diet.persistence.get_user_diet_by_id",
        return_value=active_diet,
    ), patch("app.services.diet.persistence.save_diet") as save_diet_mock:
        result = activate_user_diet(object(), "6625b8b4d7a9e6b4d4a0f101", active_diet.id)

    assert result == active_diet
    save_diet_mock.assert_not_called()
