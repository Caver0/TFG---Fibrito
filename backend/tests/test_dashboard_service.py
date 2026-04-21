from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from app.schemas.diet import DailyDiet
from app.services.dashboard_service import get_active_diet_overview


def _build_food(code: str, name: str) -> dict:
    return {
        "food_code": code,
        "source": "internal_catalog",
        "origin_source": "internal_catalog",
        "spoonacular_id": None,
        "name": name,
        "category": "proteinas",
        "quantity": 100,
        "unit": "g",
        "grams": 100,
        "calories": 165,
        "protein_grams": 31,
        "fat_grams": 3.6,
        "carb_grams": 0,
    }


def _build_daily_diet() -> DailyDiet:
    return DailyDiet(
        id="6625b8b4d7a9e6b4d4a0f401",
        created_at=datetime(2026, 4, 21, tzinfo=UTC),
        diet_mode="manual",
        is_active=True,
        valid_from=datetime(2026, 4, 21, tzinfo=UTC),
        valid_to=None,
        adjusted_from_diet_id=None,
        meals_count=3,
        target_calories=2400,
        protein_grams=180,
        fat_grams=60,
        carb_grams=210,
        actual_calories=2285,
        actual_protein_grams=171,
        actual_fat_grams=55,
        actual_carb_grams=198,
        calorie_difference=-115,
        protein_difference=-9,
        fat_difference=-5,
        carb_difference=-12,
        distribution_percentages=[30, 40, 30],
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
            {
                "meal_number": 1,
                "meal_slot": "main",
                "meal_role": "breakfast",
                "meal_label": "Desayuno",
                "distribution_percentage": 30,
                "target_calories": 720,
                "target_protein_grams": 54,
                "target_fat_grams": 18,
                "target_carb_grams": 63,
                "actual_calories": 685,
                "actual_protein_grams": 50,
                "actual_fat_grams": 16,
                "actual_carb_grams": 60,
                "calorie_difference": -35,
                "protein_difference": -4,
                "fat_difference": -2,
                "carb_difference": -3,
                "foods": [_build_food("egg", "Huevos")],
            },
            {
                "meal_number": 2,
                "meal_slot": "main",
                "meal_role": "meal",
                "meal_label": "Comida",
                "distribution_percentage": 40,
                "target_calories": 960,
                "target_protein_grams": 72,
                "target_fat_grams": 24,
                "target_carb_grams": 84,
                "actual_calories": 915,
                "actual_protein_grams": 69,
                "actual_fat_grams": 22,
                "actual_carb_grams": 80,
                "calorie_difference": -45,
                "protein_difference": -3,
                "fat_difference": -2,
                "carb_difference": -4,
                "foods": [_build_food("chicken", "Pollo")],
            },
            {
                "meal_number": 3,
                "meal_slot": "main",
                "meal_role": "dinner",
                "meal_label": "Cena",
                "distribution_percentage": 30,
                "target_calories": 720,
                "target_protein_grams": 54,
                "target_fat_grams": 18,
                "target_carb_grams": 63,
                "actual_calories": 685,
                "actual_protein_grams": 52,
                "actual_fat_grams": 17,
                "actual_carb_grams": 58,
                "calorie_difference": -35,
                "protein_difference": -2,
                "fat_difference": -1,
                "carb_difference": -5,
                "foods": [_build_food("fish", "Pescado")],
            },
        ],
    )


def test_get_active_diet_overview_uses_same_active_diet_values_as_diets_section():
    active_diet = _build_daily_diet()

    with patch("app.services.dashboard_service.get_active_user_diet", return_value=active_diet):
        overview = get_active_diet_overview(object(), "6625b8b4d7a9e6b4d4a0f101")

    assert overview is not None
    assert overview.id == active_diet.id
    assert overview.target_calories == active_diet.target_calories
    assert overview.actual_calories == active_diet.actual_calories
    assert overview.protein_grams == active_diet.protein_grams
    assert overview.actual_protein_grams == active_diet.actual_protein_grams
    assert overview.fat_grams == active_diet.fat_grams
    assert overview.actual_fat_grams == active_diet.actual_fat_grams
    assert overview.carb_grams == active_diet.carb_grams
    assert overview.actual_carb_grams == active_diet.actual_carb_grams
