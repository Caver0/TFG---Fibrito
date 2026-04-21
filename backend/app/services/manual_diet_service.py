"""Helpers to build manual diets on top of the shared diet model."""

from typing import Any

from fastapi import HTTPException, status

from app.schemas.diet import ManualDietCreateRequest, ManualDietFoodInput
from app.schemas.user import UserPublic
from app.services.diet.candidates import get_food_usage_summary_from_meals
from app.services.diet.common import calculate_difference_summary, normalize_diet_food_source, round_diet_value, round_food_value
from app.services.diet.payloads import calculate_daily_totals_from_meals, calculate_resolution_counters_from_meals, summarize_food_sources
from app.services.diet.persistence import get_user_diet_document_by_id
from app.services.food_catalog_service import get_food_by_code, get_food_catalog_version
from app.services.meal_distribution_service import generate_meal_distribution_targets

MANUAL_CATALOG_SOURCE_STRATEGY = "manual_food_selection"


def _sum_food_field(foods: list[dict[str, Any]], field_name: str) -> float:
    return round_diet_value(sum(float(food.get(field_name) or 0.0) for food in foods))


def _validate_manual_diet_request(payload: ManualDietCreateRequest) -> None:
    if len(payload.meals) != payload.meals_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The provided meals do not match the selected meals_count",
        )

    sorted_meal_numbers = sorted(meal.meal_number for meal in payload.meals)
    expected_meal_numbers = list(range(1, payload.meals_count + 1))
    if sorted_meal_numbers != expected_meal_numbers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Manual diet meals must be sequential and start at meal 1",
        )

    for meal in payload.meals:
        if not meal.foods:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Meal {meal.meal_number} must include at least one food",
            )


def _build_manual_food_payload(
    database,
    food_input: ManualDietFoodInput,
) -> dict[str, Any]:
    catalog_food = get_food_by_code(database, food_input.food_code)
    if catalog_food is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Food '{food_input.food_code}' was not found in the catalog",
        )

    reference_amount = float(catalog_food.get("reference_amount") or 0.0)
    if reference_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Food '{food_input.food_code}' does not have a valid reference amount",
        )

    quantity = float(food_input.quantity)
    scale_ratio = quantity / reference_amount
    grams_per_reference = float(catalog_food.get("grams_per_reference") or reference_amount)

    return {
        "food_code": catalog_food.get("code") or food_input.food_code,
        "source": normalize_diet_food_source(catalog_food.get("source")),
        "origin_source": normalize_diet_food_source(catalog_food.get("origin_source", catalog_food.get("source"))),
        "spoonacular_id": catalog_food.get("spoonacular_id"),
        "name": str(
            catalog_food.get("display_name")
            or catalog_food.get("name")
            or catalog_food.get("original_name")
            or food_input.food_code
        ),
        "category": str(catalog_food.get("category") or "otros"),
        "quantity": round_food_value(quantity),
        "unit": str(catalog_food.get("reference_unit") or "g"),
        "grams": round_food_value(grams_per_reference * scale_ratio),
        "calories": round_food_value(float(catalog_food.get("calories") or 0.0) * scale_ratio),
        "protein_grams": round_food_value(float(catalog_food.get("protein_grams") or 0.0) * scale_ratio),
        "fat_grams": round_food_value(float(catalog_food.get("fat_grams") or 0.0) * scale_ratio),
        "carb_grams": round_food_value(float(catalog_food.get("carb_grams") or 0.0) * scale_ratio),
    }


def build_manual_diet_payload(
    database,
    user: UserPublic,
    payload: ManualDietCreateRequest,
) -> dict[str, Any]:
    _validate_manual_diet_request(payload)

    if payload.base_diet_id:
        get_user_diet_document_by_id(database, user.id, payload.base_diet_id)

    meal_distribution, _ = generate_meal_distribution_targets(
        user=user,
        meals_count=payload.meals_count,
    )
    base_meals_by_number = {
        int(meal["meal_number"]): meal
        for meal in meal_distribution["meals"]
    }

    meals: list[dict[str, Any]] = []
    for meal_input in sorted(payload.meals, key=lambda item: item.meal_number):
        base_meal = base_meals_by_number[meal_input.meal_number]
        foods = [
            _build_manual_food_payload(database, food_input)
            for food_input in meal_input.foods
        ]
        actual_calories = _sum_food_field(foods, "calories")
        actual_protein_grams = _sum_food_field(foods, "protein_grams")
        actual_fat_grams = _sum_food_field(foods, "fat_grams")
        actual_carb_grams = _sum_food_field(foods, "carb_grams")
        differences = calculate_difference_summary(
            target_calories=float(base_meal["target_calories"]),
            target_protein_grams=float(base_meal["target_protein_grams"]),
            target_fat_grams=float(base_meal["target_fat_grams"]),
            target_carb_grams=float(base_meal["target_carb_grams"]),
            actual_calories=actual_calories,
            actual_protein_grams=actual_protein_grams,
            actual_fat_grams=actual_fat_grams,
            actual_carb_grams=actual_carb_grams,
        )
        meals.append({
            **base_meal,
            "actual_calories": actual_calories,
            "actual_protein_grams": actual_protein_grams,
            "actual_fat_grams": actual_fat_grams,
            "actual_carb_grams": actual_carb_grams,
            **differences,
            "foods": foods,
        })

    daily_totals = calculate_daily_totals_from_meals(
        target_calories=meal_distribution["target_calories"],
        target_protein_grams=meal_distribution["protein_grams"],
        target_fat_grams=meal_distribution["fat_grams"],
        target_carb_grams=meal_distribution["carb_grams"],
        meals=meals,
    )
    food_data_source, food_data_sources = summarize_food_sources(meals)
    resolution_counters = calculate_resolution_counters_from_meals(meals)

    return {
        "diet_mode": "manual",
        "meals_count": meal_distribution["meals_count"],
        "target_calories": meal_distribution["target_calories"],
        "protein_grams": meal_distribution["protein_grams"],
        "fat_grams": meal_distribution["fat_grams"],
        "carb_grams": meal_distribution["carb_grams"],
        "actual_calories": daily_totals["actual_calories"],
        "actual_protein_grams": daily_totals["actual_protein_grams"],
        "actual_fat_grams": daily_totals["actual_fat_grams"],
        "actual_carb_grams": daily_totals["actual_carb_grams"],
        "calorie_difference": daily_totals["calorie_difference"],
        "protein_difference": daily_totals["protein_difference"],
        "fat_difference": daily_totals["fat_difference"],
        "carb_difference": daily_totals["carb_difference"],
        "distribution_percentages": meal_distribution["distribution_percentages"],
        "training_time_of_day": meal_distribution["training_time_of_day"],
        "training_optimization_applied": meal_distribution["training_optimization_applied"],
        "food_data_source": food_data_source,
        "food_data_sources": food_data_sources,
        "food_catalog_version": get_food_catalog_version(),
        "food_preferences_applied": False,
        "applied_dietary_restrictions": [],
        "applied_allergies": [],
        "preferred_food_matches": 0,
        "diversity_strategy_applied": False,
        "food_usage_summary": get_food_usage_summary_from_meals(meals),
        "food_filter_warnings": [],
        "catalog_source_strategy": MANUAL_CATALOG_SOURCE_STRATEGY,
        "spoonacular_attempted": resolution_counters["spoonacular_hits"] > 0,
        "spoonacular_attempts": resolution_counters["spoonacular_hits"],
        "spoonacular_hits": resolution_counters["spoonacular_hits"],
        "cache_hits": resolution_counters["cache_hits"],
        "internal_fallbacks": resolution_counters["internal_fallbacks"],
        "resolved_foods_count": resolution_counters["resolved_foods_count"],
        "meals": meals,
    }
