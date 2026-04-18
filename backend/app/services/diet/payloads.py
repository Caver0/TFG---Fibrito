"""Construccion de payloads y resumenes de dietas."""

from typing import Any

from app.schemas.diet import DailyDiet, DietMeal
from app.services.food_catalog_service import get_food_catalog_version
from app.services.food_preferences_service import count_preferred_food_matches_in_meals

from app.services.diet.candidates import get_food_usage_summary_from_meals
from app.services.diet.common import (
    calculate_difference_summary,
    normalize_diet_food_source,
    resolve_meal_context,
    round_diet_value,
)
from app.services.diet.constants import (
    CACHE_FOOD_DATA_SOURCE,
    DEFAULT_FOOD_DATA_SOURCE,
    SPOONACULAR_FOOD_DATA_SOURCE,
)
from app.services.diet.solver import build_exact_meal_solution


def generate_food_based_meal(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    meal_plan: dict,
    food_lookup: dict[str, dict],
) -> dict:
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    selected_role_codes = meal_plan.get("selected_role_codes", {})
    selected_role_foods = {
        role: food_lookup[food_code]
        for role, food_code in selected_role_codes.items()
    }
    meal_fit = build_exact_meal_solution(
        meal=meal,
        role_foods=selected_role_foods,
        support_food_specs=meal_plan.get("support_food_specs", []),
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=food_lookup,
        training_focus=training_focus,
        meal_slot=meal_slot,
    )
    if meal_fit is None:
        meal_fit = meal_plan

    return {
        "meal_number": meal.meal_number,
        "meal_slot": meal_slot,
        "meal_role": meal_role,
        "meal_label": meal.meal_label,
        "distribution_percentage": round_diet_value(meal.distribution_percentage or 0),
        "target_calories": round_diet_value(meal.target_calories),
        "target_protein_grams": round_diet_value(meal.target_protein_grams),
        "target_fat_grams": round_diet_value(meal.target_fat_grams),
        "target_carb_grams": round_diet_value(meal.target_carb_grams),
        "actual_calories": meal_fit["actual_calories"],
        "actual_protein_grams": meal_fit["actual_protein_grams"],
        "actual_fat_grams": meal_fit["actual_fat_grams"],
        "actual_carb_grams": meal_fit["actual_carb_grams"],
        "calorie_difference": meal_fit["calorie_difference"],
        "protein_difference": meal_fit["protein_difference"],
        "fat_difference": meal_fit["fat_difference"],
        "carb_difference": meal_fit["carb_difference"],
        "foods": meal_fit["foods"],
    }


def collect_selected_food_codes(meal_plans: list[dict]) -> list[str]:
    selected_codes: list[str] = []
    seen_codes: set[str] = set()

    def add_code(food_code: str) -> None:
        if food_code in seen_codes:
            return

        seen_codes.add(food_code)
        selected_codes.append(food_code)

    for meal_plan in meal_plans:
        for food_code in meal_plan.get("selected_role_codes", {}).values():
            add_code(food_code)

        for support_food in meal_plan.get("support_food_specs", []):
            add_code(support_food["food_code"])

    return selected_codes


def summarize_food_sources(meals: list[dict]) -> tuple[str, list[str]]:
    source_order = [DEFAULT_FOOD_DATA_SOURCE, CACHE_FOOD_DATA_SOURCE, SPOONACULAR_FOOD_DATA_SOURCE]
    used_sources = {
        normalize_diet_food_source(food.get("source", DEFAULT_FOOD_DATA_SOURCE))
        for meal in meals
        for food in meal.get("foods", [])
    }
    ordered_sources = [source for source in source_order if source in used_sources]
    if not ordered_sources:
        ordered_sources = [DEFAULT_FOOD_DATA_SOURCE]

    return (
        ordered_sources[0] if len(ordered_sources) == 1 else "mixed",
        ordered_sources,
    )


def calculate_daily_totals_from_meals(
    *,
    target_calories: float,
    target_protein_grams: float,
    target_fat_grams: float,
    target_carb_grams: float,
    meals: list[dict],
) -> dict[str, float]:
    actual_calories = round_diet_value(sum(meal["actual_calories"] for meal in meals))
    actual_protein_grams = round_diet_value(sum(meal["actual_protein_grams"] for meal in meals))
    actual_fat_grams = round_diet_value(sum(meal["actual_fat_grams"] for meal in meals))
    actual_carb_grams = round_diet_value(sum(meal["actual_carb_grams"] for meal in meals))

    return {
        "actual_calories": actual_calories,
        "actual_protein_grams": actual_protein_grams,
        "actual_fat_grams": actual_fat_grams,
        "actual_carb_grams": actual_carb_grams,
        **calculate_difference_summary(
            target_calories=target_calories,
            target_protein_grams=target_protein_grams,
            target_fat_grams=target_fat_grams,
            target_carb_grams=target_carb_grams,
            actual_calories=actual_calories,
            actual_protein_grams=actual_protein_grams,
            actual_fat_grams=actual_fat_grams,
            actual_carb_grams=actual_carb_grams,
        ),
    }


def calculate_resolution_counters_from_meals(meals: list[dict]) -> dict[str, int]:
    unique_food_codes: set[str] = set()
    counters = {
        "spoonacular_hits": 0,
        "cache_hits": 0,
        "internal_fallbacks": 0,
        "resolved_foods_count": 0,
    }

    for meal in meals:
        for food in meal.get("foods", []):
            food_code = str(food.get("food_code") or food.get("name") or "").strip()
            if food_code:
                unique_food_codes.add(food_code)

            source = normalize_diet_food_source(food.get("source", DEFAULT_FOOD_DATA_SOURCE))
            if source == SPOONACULAR_FOOD_DATA_SOURCE:
                counters["spoonacular_hits"] += 1
            elif source == CACHE_FOOD_DATA_SOURCE:
                counters["cache_hits"] += 1
            else:
                counters["internal_fallbacks"] += 1

    counters["resolved_foods_count"] = len(unique_food_codes)
    return counters


def build_updated_diet_payload(
    *,
    existing_diet: DailyDiet,
    meals: list[dict],
    preference_profile: dict | None = None,
    metadata_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata_overrides or {}
    food_data_source, food_data_sources = summarize_food_sources(meals)
    preferred_food_matches = (
        count_preferred_food_matches_in_meals(meals, preference_profile)
        if preference_profile is not None
        else existing_diet.preferred_food_matches
    )
    food_usage_summary = get_food_usage_summary_from_meals(meals)
    daily_totals = calculate_daily_totals_from_meals(
        target_calories=existing_diet.target_calories,
        target_protein_grams=existing_diet.protein_grams,
        target_fat_grams=existing_diet.fat_grams,
        target_carb_grams=existing_diet.carb_grams,
        meals=meals,
    )
    resolution_counters = calculate_resolution_counters_from_meals(meals)

    spoonacular_hits = int(metadata.get("spoonacular_hits", resolution_counters["spoonacular_hits"]))
    cache_hits = int(metadata.get("cache_hits", resolution_counters["cache_hits"]))
    internal_fallbacks = int(metadata.get("internal_fallbacks", resolution_counters["internal_fallbacks"]))
    resolved_foods_count = int(metadata.get("resolved_foods_count", resolution_counters["resolved_foods_count"]))
    spoonacular_attempted = bool(
        metadata.get(
            "spoonacular_attempted",
            existing_diet.spoonacular_attempted or spoonacular_hits > 0,
        )
    )
    spoonacular_attempts = int(
        metadata.get(
            "spoonacular_attempts",
            max(existing_diet.spoonacular_attempts, spoonacular_hits),
        )
    )

    return {
        "meals_count": existing_diet.meals_count,
        "target_calories": existing_diet.target_calories,
        "protein_grams": existing_diet.protein_grams,
        "fat_grams": existing_diet.fat_grams,
        "carb_grams": existing_diet.carb_grams,
        "actual_calories": daily_totals["actual_calories"],
        "actual_protein_grams": daily_totals["actual_protein_grams"],
        "actual_fat_grams": daily_totals["actual_fat_grams"],
        "actual_carb_grams": daily_totals["actual_carb_grams"],
        "calorie_difference": daily_totals["calorie_difference"],
        "protein_difference": daily_totals["protein_difference"],
        "fat_difference": daily_totals["fat_difference"],
        "carb_difference": daily_totals["carb_difference"],
        "distribution_percentages": list(existing_diet.distribution_percentages),
        "training_time_of_day": existing_diet.training_time_of_day,
        "training_optimization_applied": existing_diet.training_optimization_applied,
        "food_data_source": food_data_source,
        "food_data_sources": food_data_sources,
        "food_catalog_version": metadata.get("food_catalog_version", existing_diet.food_catalog_version or get_food_catalog_version()),
        "food_preferences_applied": bool(
            metadata.get(
                "food_preferences_applied",
                preference_profile.get("has_preferences", existing_diet.food_preferences_applied)
                if preference_profile is not None
                else existing_diet.food_preferences_applied,
            )
        ),
        "applied_dietary_restrictions": list(
            metadata.get(
                "applied_dietary_restrictions",
                preference_profile.get("dietary_restrictions", existing_diet.applied_dietary_restrictions)
                if preference_profile is not None
                else existing_diet.applied_dietary_restrictions,
            )
        ),
        "applied_allergies": list(
            metadata.get(
                "applied_allergies",
                preference_profile.get("allergies", existing_diet.applied_allergies)
                if preference_profile is not None
                else existing_diet.applied_allergies,
            )
        ),
        "preferred_food_matches": preferred_food_matches,
        "diversity_strategy_applied": bool(metadata.get("diversity_strategy_applied", existing_diet.diversity_strategy_applied)),
        "food_usage_summary": food_usage_summary,
        "food_filter_warnings": list(
            metadata.get(
                "food_filter_warnings",
                preference_profile.get("warnings", existing_diet.food_filter_warnings)
                if preference_profile is not None
                else existing_diet.food_filter_warnings,
            )
        ),
        "catalog_source_strategy": metadata.get("catalog_source_strategy", existing_diet.catalog_source_strategy),
        "spoonacular_attempted": spoonacular_attempted,
        "spoonacular_attempts": spoonacular_attempts,
        "spoonacular_hits": spoonacular_hits,
        "cache_hits": cache_hits,
        "internal_fallbacks": internal_fallbacks,
        "resolved_foods_count": resolved_foods_count,
        "meals": meals,
    }
