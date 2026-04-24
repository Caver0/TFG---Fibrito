from __future__ import annotations

from datetime import datetime

from app.schemas.user import FoodPreferencesProfile, UserPublic
from app.services import diet_service


class _DummyFoodsCatalog:
    def find(self, *args, **kwargs):
        return []


class _DummyDatabase:
    foods_catalog = _DummyFoodsCatalog()


def _build_user(user_id: str) -> UserPublic:
    return UserPublic(
        id=user_id,
        name="Usuario Test",
        email=f"{user_id}@example.com",
        created_at=datetime(2026, 1, 1),
        age=30,
        sex="Masculino",
        height=180.0,
        current_weight=80.0,
        training_days_per_week=4,
        goal="ganar_masa",
        target_calories=2500.0,
        food_preferences=FoodPreferencesProfile(),
        auth_providers=["password"],
    )


def test_generate_food_based_diet_pasa_variety_seed_a_diet_v2(monkeypatch):
    engine_seeds: list[int | None] = []

    monkeypatch.setattr(
        diet_service,
        "build_user_food_preferences_profile",
        lambda user: {
            "preferred_foods": [],
            "disliked_foods": [],
            "dietary_restrictions": [],
            "allergies": [],
            "normalized_preferred_foods": set(),
            "normalized_disliked_foods": set(),
            "dietary_restriction_set": set(),
            "allergy_set": set(),
            "allergy_tag_set": set(),
            "has_positive_preferences": False,
            "has_negative_preferences": False,
            "has_preferences": False,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        diet_service,
        "generate_meal_distribution_targets",
        lambda **kwargs: (
            {
                "meals_count": 2,
                "target_calories": 2500.0,
                "protein_grams": 180.0,
                "fat_grams": 70.0,
                "carb_grams": 290.0,
                "distribution_percentages": [50.0, 50.0],
                "training_time_of_day": "manana",
                "training_optimization_applied": False,
                "meals": [
                    {
                        "meal_number": 1,
                        "meal_slot": "early",
                        "meal_role": "breakfast",
                        "meal_label": "Desayuno",
                        "distribution_percentage": 50.0,
                        "target_calories": 1250.0,
                        "target_protein_grams": 90.0,
                        "target_fat_grams": 35.0,
                        "target_carb_grams": 145.0,
                        "actual_calories": 0.0,
                        "actual_protein_grams": 0.0,
                        "actual_fat_grams": 0.0,
                        "actual_carb_grams": 0.0,
                    },
                    {
                        "meal_number": 2,
                        "meal_slot": "main",
                        "meal_role": "meal",
                        "meal_label": "Comida",
                        "distribution_percentage": 50.0,
                        "target_calories": 1250.0,
                        "target_protein_grams": 90.0,
                        "target_fat_grams": 35.0,
                        "target_carb_grams": 145.0,
                        "actual_calories": 0.0,
                        "actual_protein_grams": 0.0,
                        "actual_fat_grams": 0.0,
                        "actual_carb_grams": 0.0,
                    },
                ],
            },
            [],
        ),
    )
    monkeypatch.setattr(diet_service, "get_internal_food_lookup", lambda: {})
    monkeypatch.setattr(diet_service, "build_generation_food_lookup", lambda database, internal_food_lookup=None: {})
    monkeypatch.setattr(diet_service, "create_daily_food_usage_tracker", lambda: {})
    monkeypatch.setattr(diet_service, "build_weekly_food_usage", lambda database, user_id: {})
    monkeypatch.setattr(
        diet_service,
        "resolve_meal_context",
        lambda meal, meal_index, meals_count, training_focus: (meal.meal_slot, meal.meal_role),
    )
    monkeypatch.setattr(diet_service, "build_variety_seed", lambda *parts: 700)

    def fake_v2_engine(**kwargs):
        engine_seeds.append(kwargs.get("variety_seed"))
        return {
            "meal_plans": [
                {
                    "foods": [],
                    "selected_role_codes": {},
                    "support_food_specs": [],
                    "score": 0.0,
                },
                {
                    "foods": [],
                    "selected_role_codes": {},
                    "support_food_specs": [],
                    "score": 0.0,
                },
            ],
            "phase_timings": {},
            "used_legacy_fallback": False,
        }

    monkeypatch.setattr(diet_service, "generate_day_meal_plans_v2", fake_v2_engine)
    monkeypatch.setattr(diet_service, "collect_selected_food_codes", lambda meals: [])
    monkeypatch.setattr(
        diet_service,
        "resolve_foods_by_codes",
        lambda database, codes: ({}, {"resolved_foods_count": 0}),
    )
    monkeypatch.setattr(
        diet_service,
        "generate_food_based_meal",
        lambda **kwargs: {"meal_number": kwargs["meal"].meal_number, "foods": []},
    )
    monkeypatch.setattr(diet_service, "summarize_food_sources", lambda meals: ("internal", {"internal": len(meals)}))
    monkeypatch.setattr(diet_service, "count_preferred_food_matches_in_meals", lambda meals, profile: 0)
    monkeypatch.setattr(
        diet_service,
        "calculate_daily_totals_from_meals",
        lambda **kwargs: {
            "actual_calories": 0.0,
            "actual_protein_grams": 0.0,
            "actual_fat_grams": 0.0,
            "actual_carb_grams": 0.0,
            "calorie_difference": 0.0,
            "protein_difference": 0.0,
            "fat_difference": 0.0,
            "carb_difference": 0.0,
        },
    )
    monkeypatch.setattr(diet_service, "get_food_usage_summary_from_meals", lambda meals: {})
    monkeypatch.setattr(diet_service, "get_food_catalog_version", lambda: "test-version")

    diet_service.generate_food_based_diet(
        _DummyDatabase(),
        user=_build_user("user-a"),
        meals_count=2,
        training_time_of_day="manana",
    )

    assert engine_seeds == [700]


def test_generate_food_based_diet_desactiva_enriquecimiento_externo_final(monkeypatch):
    resolve_kwargs: list[bool] = []

    monkeypatch.setattr(
        diet_service,
        "build_user_food_preferences_profile",
        lambda user: {
            "preferred_foods": [],
            "disliked_foods": [],
            "dietary_restrictions": [],
            "allergies": [],
            "normalized_preferred_foods": set(),
            "normalized_disliked_foods": set(),
            "dietary_restriction_set": set(),
            "allergy_set": set(),
            "allergy_tag_set": set(),
            "has_positive_preferences": False,
            "has_negative_preferences": False,
            "has_preferences": False,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        diet_service,
        "generate_meal_distribution_targets",
        lambda **kwargs: (
            {
                "meals_count": 2,
                "target_calories": 2500.0,
                "protein_grams": 180.0,
                "fat_grams": 70.0,
                "carb_grams": 290.0,
                "distribution_percentages": [50.0, 50.0],
                "training_time_of_day": "manana",
                "training_optimization_applied": False,
                "meals": [
                    {
                        "meal_number": 1,
                        "meal_slot": "early",
                        "meal_role": "breakfast",
                        "meal_label": "Desayuno",
                        "distribution_percentage": 50.0,
                        "target_calories": 1250.0,
                        "target_protein_grams": 90.0,
                        "target_fat_grams": 35.0,
                        "target_carb_grams": 145.0,
                        "actual_calories": 0.0,
                        "actual_protein_grams": 0.0,
                        "actual_fat_grams": 0.0,
                        "actual_carb_grams": 0.0,
                    },
                    {
                        "meal_number": 2,
                        "meal_slot": "main",
                        "meal_role": "meal",
                        "meal_label": "Comida",
                        "distribution_percentage": 50.0,
                        "target_calories": 1250.0,
                        "target_protein_grams": 90.0,
                        "target_fat_grams": 35.0,
                        "target_carb_grams": 145.0,
                        "actual_calories": 0.0,
                        "actual_protein_grams": 0.0,
                        "actual_fat_grams": 0.0,
                        "actual_carb_grams": 0.0,
                    },
                ],
            },
            [],
        ),
    )
    monkeypatch.setattr(
        diet_service,
        "get_internal_food_lookup",
        lambda: {
            "greek_yogurt": {"code": "greek_yogurt"},
            "oats": {"code": "oats"},
            "mixed_nuts": {"code": "mixed_nuts"},
        },
    )
    monkeypatch.setattr(diet_service, "build_generation_food_lookup", lambda database, internal_food_lookup=None: {})
    monkeypatch.setattr(diet_service, "create_daily_food_usage_tracker", lambda: {})
    monkeypatch.setattr(diet_service, "build_weekly_food_usage", lambda database, user_id: {})
    monkeypatch.setattr(
        diet_service,
        "resolve_meal_context",
        lambda meal, meal_index, meals_count, training_focus: (meal.meal_slot, meal.meal_role),
    )
    monkeypatch.setattr(diet_service, "build_variety_seed", lambda *parts: 700)
    monkeypatch.setattr(
        diet_service,
        "generate_day_meal_plans_v2",
        lambda **kwargs: {
            "meal_plans": [
                {
                    "foods": [],
                    "selected_role_codes": {
                        "protein": "greek_yogurt",
                        "carb": "oats",
                        "fat": "mixed_nuts",
                    },
                    "support_food_specs": [],
                    "score": 0.0,
                },
                {
                    "foods": [],
                    "selected_role_codes": {
                        "protein": "greek_yogurt",
                        "carb": "oats",
                        "fat": "mixed_nuts",
                    },
                    "support_food_specs": [],
                    "score": 0.0,
                },
            ],
            "phase_timings": {},
            "used_legacy_fallback": False,
        },
    )
    monkeypatch.setattr(diet_service, "collect_selected_food_codes", lambda meals: ["greek_yogurt", "oats", "mixed_nuts"])

    def fake_resolve_foods_by_codes(database, codes, allow_external_enrichment=True):
        resolve_kwargs.append(allow_external_enrichment)
        return ({}, {"resolved_foods_count": len(codes), "food_catalog_version": "internal-v4", "catalog_source_strategy": "internal"})

    monkeypatch.setattr(diet_service, "resolve_foods_by_codes", fake_resolve_foods_by_codes)
    monkeypatch.setattr(
        diet_service,
        "generate_food_based_meal",
        lambda **kwargs: {"meal_number": kwargs["meal"].meal_number, "foods": []},
    )
    monkeypatch.setattr(diet_service, "summarize_food_sources", lambda meals: ("internal", {"internal": len(meals)}))
    monkeypatch.setattr(diet_service, "count_preferred_food_matches_in_meals", lambda meals, profile: 0)
    monkeypatch.setattr(
        diet_service,
        "calculate_daily_totals_from_meals",
        lambda **kwargs: {
            "actual_calories": 0.0,
            "actual_protein_grams": 0.0,
            "actual_fat_grams": 0.0,
            "actual_carb_grams": 0.0,
            "calorie_difference": 0.0,
            "protein_difference": 0.0,
            "fat_difference": 0.0,
            "carb_difference": 0.0,
        },
    )
    monkeypatch.setattr(diet_service, "get_food_usage_summary_from_meals", lambda meals: {})
    monkeypatch.setattr(diet_service, "get_food_catalog_version", lambda: "test-version")

    diet_service.generate_food_based_diet(
        _DummyDatabase(),
        user=_build_user("user-b"),
        meals_count=2,
        training_time_of_day="manana",
    )

    assert resolve_kwargs == [False]


def test_generate_food_based_diet_reintenta_hasta_obtener_payload_estricto(monkeypatch):
    engine_seeds: list[int | None] = []
    current_seed: dict[str, int | None] = {"value": None}

    monkeypatch.setattr(
        diet_service,
        "build_user_food_preferences_profile",
        lambda user: {
            "preferred_foods": [],
            "disliked_foods": [],
            "dietary_restrictions": [],
            "allergies": [],
            "normalized_preferred_foods": set(),
            "normalized_disliked_foods": set(),
            "dietary_restriction_set": set(),
            "allergy_set": set(),
            "allergy_tag_set": set(),
            "has_positive_preferences": False,
            "has_negative_preferences": False,
            "has_preferences": False,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        diet_service,
        "generate_meal_distribution_targets",
        lambda **kwargs: (
            {
                "meals_count": 2,
                "target_calories": 2500.0,
                "protein_grams": 180.0,
                "fat_grams": 70.0,
                "carb_grams": 290.0,
                "distribution_percentages": [50.0, 50.0],
                "training_time_of_day": "manana",
                "training_optimization_applied": False,
                "meals": [
                    {
                        "meal_number": 1,
                        "meal_slot": "early",
                        "meal_role": "breakfast",
                        "meal_label": "Desayuno",
                        "distribution_percentage": 50.0,
                        "target_calories": 1250.0,
                        "target_protein_grams": 90.0,
                        "target_fat_grams": 35.0,
                        "target_carb_grams": 145.0,
                        "actual_calories": 0.0,
                        "actual_protein_grams": 0.0,
                        "actual_fat_grams": 0.0,
                        "actual_carb_grams": 0.0,
                    },
                    {
                        "meal_number": 2,
                        "meal_slot": "main",
                        "meal_role": "meal",
                        "meal_label": "Comida",
                        "distribution_percentage": 50.0,
                        "target_calories": 1250.0,
                        "target_protein_grams": 90.0,
                        "target_fat_grams": 35.0,
                        "target_carb_grams": 145.0,
                        "actual_calories": 0.0,
                        "actual_protein_grams": 0.0,
                        "actual_fat_grams": 0.0,
                        "actual_carb_grams": 0.0,
                    },
                ],
            },
            [],
        ),
    )
    monkeypatch.setattr(diet_service, "get_internal_food_lookup", lambda: {})
    monkeypatch.setattr(diet_service, "build_generation_food_lookup", lambda database, internal_food_lookup=None: {})
    monkeypatch.setattr(diet_service, "create_daily_food_usage_tracker", lambda: {})
    monkeypatch.setattr(diet_service, "build_weekly_food_usage", lambda database, user_id: {})
    monkeypatch.setattr(
        diet_service,
        "resolve_meal_context",
        lambda meal, meal_index, meals_count, training_focus: (meal.meal_slot, meal.meal_role),
    )
    monkeypatch.setattr(diet_service, "build_variety_seed", lambda *parts: 700)
    monkeypatch.setattr(diet_service, "collect_selected_food_codes", lambda meals: [])
    monkeypatch.setattr(
        diet_service,
        "resolve_foods_by_codes",
        lambda database, codes, allow_external_enrichment=False: ({}, {"resolved_foods_count": len(codes)}),
    )
    monkeypatch.setattr(diet_service, "summarize_food_sources", lambda meals: ("internal", {"internal": len(meals)}))
    monkeypatch.setattr(diet_service, "count_preferred_food_matches_in_meals", lambda meals, profile: 0)
    monkeypatch.setattr(diet_service, "get_food_usage_summary_from_meals", lambda meals: {})
    monkeypatch.setattr(diet_service, "get_food_catalog_version", lambda: "test-version")

    def fake_v2_engine(**kwargs):
        current_seed["value"] = kwargs.get("variety_seed")
        engine_seeds.append(current_seed["value"])
        return {
            "meal_plans": [
                {"foods": [], "selected_role_codes": {}, "support_food_specs": [], "score": 0.0},
                {"foods": [], "selected_role_codes": {}, "support_food_specs": [], "score": 0.0},
            ],
            "phase_timings": {},
            "used_legacy_fallback": False,
            "diagnostics": {},
        }

    def fake_generate_food_based_meal(**kwargs):
        meal = kwargs["meal"]
        invalid_first_attempt = current_seed["value"] == 700
        if invalid_first_attempt:
            actual_protein = 100.0 if meal.meal_number == 1 else 80.0
            actual_carb = 120.0 if meal.meal_number == 1 else 170.0
        else:
            actual_protein = 90.0
            actual_carb = 145.0
        return {
            "meal_number": meal.meal_number,
            "meal_slot": meal.meal_slot,
            "meal_role": meal.meal_role,
            "meal_label": meal.meal_label,
            "distribution_percentage": meal.distribution_percentage,
            "target_calories": meal.target_calories,
            "target_protein_grams": meal.target_protein_grams,
            "target_fat_grams": meal.target_fat_grams,
            "target_carb_grams": meal.target_carb_grams,
            "actual_calories": meal.target_calories,
            "actual_protein_grams": actual_protein,
            "actual_fat_grams": 35.0,
            "actual_carb_grams": actual_carb,
            "calorie_difference": 0.0,
            "protein_difference": actual_protein - meal.target_protein_grams,
            "fat_difference": 0.0,
            "carb_difference": actual_carb - meal.target_carb_grams,
            "foods": [],
        }

    monkeypatch.setattr(diet_service, "generate_day_meal_plans_v2", fake_v2_engine)
    monkeypatch.setattr(diet_service, "generate_food_based_meal", fake_generate_food_based_meal)

    generated_diet = diet_service.generate_food_based_diet(
        _DummyDatabase(),
        user=_build_user("user-strict-retry"),
        meals_count=2,
        training_time_of_day="manana",
    )

    assert engine_seeds[:2] == [700, 717]
    assert generated_diet["protein_difference"] == 0.0
    assert generated_diet["carb_difference"] == 0.0
