from __future__ import annotations

from datetime import datetime

from app.schemas.diet import DietMeal
from app.schemas.user import FoodPreferencesProfile, UserPublic
from app.services.diet.candidates import create_daily_food_usage_tracker, track_food_usage_across_day
from app.services.diet.common import resolve_meal_context
from app.services.diet_v2.engine import generate_day_meal_plans_v2
from app.services.diet_v2.regenerator import regenerate_meal_plan_v2
from app.services.food_catalog_service import get_internal_food_lookup
from app.services.food_preferences_service import build_user_food_preferences_profile
from app.services.meal_distribution_service import generate_meal_distribution_targets


def _build_user(user_id: str = "user-regen") -> UserPublic:
    return UserPublic(
        id=user_id,
        name="Usuario Regeneration",
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


def _build_day(seed: int = 123) -> tuple[dict, list[dict], list[dict]]:
    user = _build_user()
    meal_distribution, focus_indexes = generate_meal_distribution_targets(
        user=user,
        meals_count=4,
        custom_percentages=None,
        training_time_of_day="tarde",
    )
    meals_context: list[dict] = []
    for meal_index, meal in enumerate(meal_distribution["meals"]):
        training_focus = meal_distribution["training_optimization_applied"] and meal_index in focus_indexes
        meal_slot, meal_role = resolve_meal_context(
            DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=4,
            training_focus=training_focus,
        )
        meals_context.append({
            "meal_slot": meal_slot,
            "meal_role": meal_role,
            "training_focus": training_focus,
        })
    result = generate_day_meal_plans_v2(
        meal_distribution=meal_distribution,
        meals_context=meals_context,
        meals_count=4,
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(user),
        daily_food_usage=create_daily_food_usage_tracker(),
        weekly_food_usage={},
        variety_seed=seed,
    )
    return meal_distribution, meals_context, result["meal_plans"]


def test_regenerate_meal_plan_v2_prefers_a_different_blueprint_when_available():
    meal_distribution, meals_context, meal_plans = _build_day(seed=123)
    meal_index = 0
    meal = DietMeal.model_validate(meal_distribution["meals"][meal_index])
    current_meal_plan = meal_plans[meal_index]
    current_food_codes = {
        food["food_code"]
        for food in current_meal_plan["foods"]
    }
    daily_food_usage = create_daily_food_usage_tracker()
    for index, meal_plan in enumerate(meal_plans):
        if index == meal_index:
            continue
        track_food_usage_across_day(daily_food_usage, meal_plan)

    regenerated_plan = regenerate_meal_plan_v2(
        meal=meal,
        meal_index=meal_index,
        meals_count=4,
        training_focus=meals_context[meal_index]["training_focus"],
        meal_slot=meals_context[meal_index]["meal_slot"],
        meal_role=meals_context[meal_index]["meal_role"],
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(_build_user()),
        daily_food_usage=daily_food_usage,
        weekly_food_usage={},
        current_food_codes=current_food_codes,
        current_meal_plan=current_meal_plan,
        variety_seed=777,
    )

    assert regenerated_plan is not None
    assert regenerated_plan["applied_blueprint_id"] != current_meal_plan["applied_blueprint_id"]
    assert regenerated_plan["regeneration_difference"]["visible_change_count"] >= 2
    assert regenerated_plan["regeneration_difference"]["structure_changed"] is True


def test_regenerate_meal_plan_v2_changes_at_least_two_visible_foods_when_possible():
    meal_distribution, meals_context, meal_plans = _build_day(seed=321)
    meal_index = 3
    meal = DietMeal.model_validate(meal_distribution["meals"][meal_index])
    current_meal_plan = meal_plans[meal_index]
    current_food_codes = {
        food["food_code"]
        for food in current_meal_plan["foods"]
    }
    daily_food_usage = create_daily_food_usage_tracker()
    for index, meal_plan in enumerate(meal_plans):
        if index == meal_index:
            continue
        track_food_usage_across_day(daily_food_usage, meal_plan)

    regenerated_plan = regenerate_meal_plan_v2(
        meal=meal,
        meal_index=meal_index,
        meals_count=4,
        training_focus=meals_context[meal_index]["training_focus"],
        meal_slot=meals_context[meal_index]["meal_slot"],
        meal_role=meals_context[meal_index]["meal_role"],
        food_lookup=get_internal_food_lookup(),
        preference_profile=build_user_food_preferences_profile(_build_user("user-regen-2")),
        daily_food_usage=daily_food_usage,
        weekly_food_usage={},
        current_food_codes=current_food_codes,
        current_meal_plan=current_meal_plan,
        variety_seed=888,
    )

    assert regenerated_plan is not None
    assert regenerated_plan["regeneration_difference"]["visible_change_count"] >= 2
