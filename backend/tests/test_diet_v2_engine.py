from __future__ import annotations

from datetime import datetime

from app.schemas.diet import DietMeal
from app.schemas.user import FoodPreferencesProfile, UserPublic
from app.services import diet_service
from app.services.diet.candidates import create_daily_food_usage_tracker
from app.services.diet.common import resolve_meal_context
from app.services.diet_v2.engine import generate_day_meal_plans_v2
from app.services.diet_v2.families import get_primary_family_id
from app.services.diet_v2.nutrition_validation import summarize_daily_payload_nutrition, summarize_meal_payload_nutrition, summarize_meal_plan_nutrition
from app.services.food_catalog_service import get_internal_food_lookup
from app.services.food_preferences_service import build_user_food_preferences_profile
from app.services.meal_distribution_service import generate_meal_distribution_targets


class _DummyFoodsCatalog:
    def find(self, *args, **kwargs):
        return []

    def find_one(self, *args, **kwargs):
        return None


class _DummyDietsCollection:
    def find(self, *args, **kwargs):
        return []


class _DummyDatabase:
    foods_catalog = _DummyFoodsCatalog()
    diets = _DummyDietsCollection()


def _build_user(
    user_id: str = "user-v2",
    *,
    food_preferences: FoodPreferencesProfile | None = None,
) -> UserPublic:
    return UserPublic(
        id=user_id,
        name="Usuario V2",
        email=f"{user_id}@example.com",
        created_at=datetime(2026, 1, 1),
        age=30,
        sex="Masculino",
        height=180.0,
        current_weight=80.0,
        training_days_per_week=4,
        goal="ganar_masa",
        target_calories=2500.0,
        food_preferences=food_preferences or FoodPreferencesProfile(),
        auth_providers=["password"],
    )


def _build_distribution(user: UserPublic, *, meals_count: int = 4, training_time_of_day: str | None = "tarde") -> tuple[dict, list[dict]]:
    meal_distribution, focus_indexes = generate_meal_distribution_targets(
        user=user,
        meals_count=meals_count,
        custom_percentages=None,
        training_time_of_day=training_time_of_day,
    )
    meals_context: list[dict] = []
    for meal_index, meal in enumerate(meal_distribution["meals"]):
        training_focus = meal_distribution["training_optimization_applied"] and meal_index in focus_indexes
        meal_slot, meal_role = resolve_meal_context(
            DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
        )
        meals_context.append({
            "meal_slot": meal_slot,
            "meal_role": meal_role,
            "training_focus": training_focus,
        })
    return meal_distribution, meals_context


def test_generate_day_meal_plans_v2_generates_complete_day_without_fallback():
    user = _build_user()
    meal_distribution, meals_context = _build_distribution(user, meals_count=4, training_time_of_day="tarde")

    result = generate_day_meal_plans_v2(
        meal_distribution=meal_distribution,
        meals_context=meals_context,
        meals_count=4,
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(user),
        daily_food_usage=create_daily_food_usage_tracker(),
        weekly_food_usage={},
        variety_seed=123,
    )

    assert result["used_legacy_fallback"] is False
    assert len(result["meal_plans"]) == 4
    for meal_plan in result["meal_plans"]:
        assert set(meal_plan["selected_role_codes"]) == {"protein", "carb", "fat"}
        assert meal_plan["foods"]
        assert "applied_blueprint_id" in meal_plan


def test_generate_day_meal_plans_v2_keeps_each_meal_within_strict_tolerance():
    user = _build_user("user-strict-meals")
    meal_distribution, meals_context = _build_distribution(user, meals_count=4, training_time_of_day="tarde")

    result = generate_day_meal_plans_v2(
        meal_distribution=meal_distribution,
        meals_context=meals_context,
        meals_count=4,
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(user),
        daily_food_usage=create_daily_food_usage_tracker(),
        weekly_food_usage={},
        variety_seed=123,
    )

    assert result["used_legacy_fallback"] is False
    assert len(result["meal_plans"]) == 4
    for meal_index, meal_plan in enumerate(result["meal_plans"]):
        meal_model = DietMeal.model_validate(meal_distribution["meals"][meal_index])
        nutrition_summary = summarize_meal_plan_nutrition(
            meal=meal_model,
            meal_plan=meal_plan,
        )
        assert nutrition_summary["within_tolerance"] is True


def test_diet_service_generate_food_based_diet_keeps_public_contract_with_v2(monkeypatch):
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "fibrito_test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    user = _build_user("user-contract")
    generated_diet = diet_service.generate_food_based_diet(
        _DummyDatabase(),
        user=user,
        meals_count=4,
        training_time_of_day="tarde",
    )

    expected_top_level_keys = {
        "meals_count",
        "target_calories",
        "protein_grams",
        "fat_grams",
        "carb_grams",
        "actual_calories",
        "actual_protein_grams",
        "actual_fat_grams",
        "actual_carb_grams",
        "distribution_percentages",
        "training_time_of_day",
        "food_data_source",
        "food_data_sources",
        "meals",
    }
    assert expected_top_level_keys.issubset(generated_diet)
    assert len(generated_diet["meals"]) == 4
    for meal in generated_diet["meals"]:
        assert {
            "meal_number",
            "meal_slot",
            "meal_role",
            "meal_label",
            "target_calories",
            "target_protein_grams",
            "target_fat_grams",
            "target_carb_grams",
            "actual_calories",
            "actual_protein_grams",
            "actual_fat_grams",
            "actual_carb_grams",
            "foods",
        }.issubset(meal)


def test_diet_service_generate_food_based_diet_returns_payload_within_strict_tolerances(monkeypatch):
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "fibrito_test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    user = _build_user("user-strict-day")
    generated_diet = diet_service.generate_food_based_diet(
        _DummyDatabase(),
        user=user,
        meals_count=4,
        training_time_of_day="tarde",
    )

    for meal in generated_diet["meals"]:
        meal_summary = summarize_meal_payload_nutrition(
            target_calories=meal["target_calories"],
            target_protein_grams=meal["target_protein_grams"],
            target_fat_grams=meal["target_fat_grams"],
            target_carb_grams=meal["target_carb_grams"],
            foods=meal["foods"],
            actuals_override={
                "actual_calories": meal["actual_calories"],
                "actual_protein_grams": meal["actual_protein_grams"],
                "actual_fat_grams": meal["actual_fat_grams"],
                "actual_carb_grams": meal["actual_carb_grams"],
            },
        )
        assert meal_summary["within_tolerance"] is True

    daily_summary = summarize_daily_payload_nutrition(
        target_calories=generated_diet["target_calories"],
        target_protein_grams=generated_diet["protein_grams"],
        target_fat_grams=generated_diet["fat_grams"],
        target_carb_grams=generated_diet["carb_grams"],
        meals=generated_diet["meals"],
    )
    assert daily_summary["within_tolerance"] is True


def test_v2_breakfast_blueprints_vary_across_seeds():
    user = _build_user("user-breakfast")
    meal_distribution, meals_context = _build_distribution(user, meals_count=4, training_time_of_day="tarde")
    breakfast_blueprints = {
        generate_day_meal_plans_v2(
            meal_distribution=meal_distribution,
            meals_context=meals_context,
            meals_count=4,
            food_lookup=get_internal_food_lookup(),
            preference_profile=build_user_food_preferences_profile(user),
            daily_food_usage=create_daily_food_usage_tracker(),
            weekly_food_usage={},
            variety_seed=seed,
        )["meal_plans"][0]["applied_blueprint_id"]
        for seed in range(1, 13)
    }

    assert len(breakfast_blueprints) >= 2


def test_v2_avoids_repeating_same_blueprint_in_one_day_when_alternatives_exist():
    user = _build_user("user-diversity")
    meal_distribution, meals_context = _build_distribution(user, meals_count=4, training_time_of_day="tarde")
    result = generate_day_meal_plans_v2(
        meal_distribution=meal_distribution,
        meals_context=meals_context,
        meals_count=4,
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(user),
        daily_food_usage=create_daily_food_usage_tracker(),
        weekly_food_usage={},
        variety_seed=321,
    )

    applied_blueprints = [meal_plan["applied_blueprint_id"] for meal_plan in result["meal_plans"]]
    assert len(set(applied_blueprints)) == len(applied_blueprints)


def test_v2_does_not_mix_redundant_canonical_families_within_a_meal():
    user = _build_user("user-families")
    meal_distribution, meals_context = _build_distribution(user, meals_count=4, training_time_of_day="tarde")
    result = generate_day_meal_plans_v2(
        meal_distribution=meal_distribution,
        meals_context=meals_context,
        meals_count=4,
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(user),
        daily_food_usage=create_daily_food_usage_tracker(),
        weekly_food_usage={},
        variety_seed=999,
    )

    lookup = get_internal_food_lookup()
    for meal_plan in result["meal_plans"]:
        family_ids = [
            get_primary_family_id(lookup[food_code], role=role)
            for role, food_code in meal_plan["selected_role_codes"].items()
        ]
        family_ids.extend(
            get_primary_family_id(lookup[support_food["food_code"]], role=support_food["role"])
            for support_food in meal_plan.get("support_food_specs", [])
            if support_food["food_code"] in lookup
        )
        assert len(family_ids) == len(set(family_ids))


def test_v2_respects_gluten_restrictions_without_fallback():
    user = _build_user(
        "user-sin-gluten",
        food_preferences=FoodPreferencesProfile(dietary_restrictions=["sin_gluten"]),
    )
    meal_distribution, meals_context = _build_distribution(user, meals_count=4, training_time_of_day="tarde")
    result = generate_day_meal_plans_v2(
        meal_distribution=meal_distribution,
        meals_context=meals_context,
        meals_count=4,
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(user),
        daily_food_usage=create_daily_food_usage_tracker(),
        weekly_food_usage={},
        variety_seed=123,
    )

    assert result["used_legacy_fallback"] is False
    forbidden_codes = {"oats", "pasta", "whole_wheat_bread"}
    used_codes = {
        food["food_code"]
        for meal_plan in result["meal_plans"]
        for food in meal_plan["foods"]
    }
    assert used_codes.isdisjoint(forbidden_codes)
