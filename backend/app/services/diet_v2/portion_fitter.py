"""Portion fitting utilities for the diet generation v2 engine."""
from __future__ import annotations

from typing import Any

from app.services.diet.common import calculate_difference_summary
from app.services.diet.solver import (
    build_exact_meal_solution,
    build_food_portion,
    build_precise_food_values,
    calculate_meal_actuals_from_foods,
    get_food_macro_density,
    get_food_visibility_threshold,
    get_role_serving_floor,
)
from app.services.diet_v2.blueprints import MealBlueprint, blueprint_metadata


def _build_support_variants(support_food_specs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not support_food_specs:
        return [[]]

    variants = [support_food_specs]
    halved_supports = [
        {
            **support_food,
            "quantity": max(float(support_food.get("quantity") or 0.0) * 0.5, 0.0),
        }
        for support_food in support_food_specs
        if float(support_food.get("quantity") or 0.0) > 0.0
    ]
    if halved_supports and halved_supports != support_food_specs:
        variants.append(halved_supports)
    variants.append([])
    return variants


def _build_support_totals(
    support_food_specs: list[dict[str, Any]],
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, float]:
    totals = {
        "calories": 0.0,
        "protein_grams": 0.0,
        "fat_grams": 0.0,
        "carb_grams": 0.0,
    }
    for support_food in support_food_specs:
        food_code = str(support_food.get("food_code") or "").strip()
        if food_code not in food_lookup:
            continue
        precise_values = build_precise_food_values(
            food_lookup[food_code],
            float(support_food.get("quantity") or 0.0),
        )
        for key in totals:
            totals[key] += precise_values[key]
    return totals


def _build_approximate_meal_solution(
    *,
    blueprint: MealBlueprint,
    meal,
    meal_request: dict[str, Any],
    selected_role_codes: dict[str, str],
    support_food_specs: list[dict[str, Any]],
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    role_foods = {
        role: food_lookup[food_code]
        for role, food_code in selected_role_codes.items()
        if food_code in food_lookup
    }
    if len(role_foods) != 3:
        return None

    support_totals = _build_support_totals(support_food_specs, food_lookup)
    remaining_targets = {
        "protein": max(float(meal.target_protein_grams) - support_totals["protein_grams"], 0.0),
        "fat": max(float(meal.target_fat_grams) - support_totals["fat_grams"], 0.0),
        "carb": max(float(meal.target_carb_grams) - support_totals["carb_grams"], 0.0),
    }
    role_macro_key = {
        "protein": "protein_grams",
        "fat": "fat_grams",
        "carb": "carb_grams",
    }
    role_quantities: dict[str, float] = {}
    floors: dict[str, float] = {}
    max_quantities: dict[str, float] = {}

    for role, food in role_foods.items():
        food_density = get_food_macro_density(food)
        macro_density = max(float(food_density.get(role_macro_key[role], 0.0)), 1e-6)
        visibility_floor = get_food_visibility_threshold(food)
        serving_floor = get_role_serving_floor(
            food,
            role=role,
            meal_slot=meal_request["meal_slot"],
            meal_role=meal_request["meal_role"],
        )
        floor = max(visibility_floor, min(max(serving_floor * 0.4, 0.0), float(food.get("min_quantity") or serving_floor or visibility_floor or 0.0)))
        if floor <= 0:
            floor = visibility_floor
        target_quantity = remaining_targets[role] / macro_density if remaining_targets[role] > 0 else floor
        max_quantity = float(food.get("max_quantity") or target_quantity or floor)
        role_quantities[role] = min(max(target_quantity, floor), max_quantity)
        floors[role] = floor
        max_quantities[role] = max_quantity

    for _iteration in range(4):
        provisional_foods = [
            {
                "role": role,
                **build_food_portion(role_foods[role], quantity),
            }
            for role, quantity in role_quantities.items()
        ]
        provisional_foods.extend(
            {
                "role": support_food["role"],
                **build_food_portion(
                    food_lookup[support_food["food_code"]],
                    float(support_food["quantity"]),
                ),
            }
            for support_food in support_food_specs
            if support_food["food_code"] in food_lookup
        )
        actuals = calculate_meal_actuals_from_foods(provisional_foods)
        diffs = {
            "protein": float(meal.target_protein_grams) - actuals["actual_protein_grams"],
            "fat": float(meal.target_fat_grams) - actuals["actual_fat_grams"],
            "carb": float(meal.target_carb_grams) - actuals["actual_carb_grams"],
        }
        for role in ("protein", "carb", "fat"):
            macro_density = max(float(get_food_macro_density(role_foods[role]).get(role_macro_key[role], 0.0)), 1e-6)
            adjustment = (diffs[role] / macro_density) * 0.7
            role_quantities[role] = min(
                max(role_quantities[role] + adjustment, floors[role]),
                max_quantities[role],
            )

    foods = [
        {
            "role": role,
            **build_food_portion(role_foods[role], quantity),
        }
        for role, quantity in role_quantities.items()
    ]
    foods.extend(
        {
            "role": support_food["role"],
            **build_food_portion(
                food_lookup[support_food["food_code"]],
                float(support_food["quantity"]),
            ),
        }
        for support_food in support_food_specs
        if support_food["food_code"] in food_lookup
    )
    foods.sort(key=lambda food: food["role"])
    actuals = calculate_meal_actuals_from_foods(foods)
    actuals.update(
        calculate_difference_summary(
            target_calories=meal.target_calories,
            target_protein_grams=meal.target_protein_grams,
            target_fat_grams=meal.target_fat_grams,
            target_carb_grams=meal.target_carb_grams,
            actual_calories=actuals["actual_calories"],
            actual_protein_grams=actuals["actual_protein_grams"],
            actual_fat_grams=actuals["actual_fat_grams"],
            actual_carb_grams=actuals["actual_carb_grams"],
        ),
    )
    score = (
        abs(actuals["calorie_difference"])
        + abs(actuals["protein_difference"]) * 1.4
        + abs(actuals["fat_difference"]) * 1.2
        + abs(actuals["carb_difference"]) * 1.2
    )
    return {
        "foods": [{key: value for key, value in food.items() if key != "role"} for food in foods],
        "selected_role_codes": dict(selected_role_codes),
        "support_food_specs": list(support_food_specs),
        "score": score,
        "portion_fit_method": "approximate_v2",
        **actuals,
        **blueprint_metadata(
            blueprint,
            meal_slot=meal_request["meal_slot"],
        ),
    }


def fit_meal_portions(
    *,
    blueprint: MealBlueprint,
    meal,
    meal_request: dict[str, Any],
    selected_role_codes: dict[str, str],
    support_food_specs: list[dict[str, Any]],
    role_candidate_pool: dict[str, list[str]],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
) -> dict[str, Any] | None:
    role_foods = {
        role: food_lookup[food_code]
        for role, food_code in selected_role_codes.items()
        if food_code in food_lookup
    }
    if len(role_foods) != 3:
        return None

    candidate_indexes = {
        role: max(0, role_candidate_pool.get(role, [selected_role_codes[role]]).index(selected_role_codes[role]))
        if selected_role_codes[role] in role_candidate_pool.get(role, [])
        else 0
        for role in ("protein", "carb", "fat")
    }

    for support_variant in _build_support_variants(support_food_specs):
        solution = build_exact_meal_solution(
            meal=meal,
            role_foods=role_foods,
            support_food_specs=support_variant,
            candidate_indexes=candidate_indexes,
            food_lookup=food_lookup,
            training_focus=meal_request["training_focus"],
            meal_slot=meal_request["meal_slot"],
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            weekly_food_usage=weekly_food_usage,
        )
        if solution is None:
            continue
        solution.update(blueprint_metadata(
            blueprint,
            meal_slot=meal_request["meal_slot"],
        ))
        solution["support_food_specs"] = support_variant
        return solution

    return _build_approximate_meal_solution(
        blueprint=blueprint,
        meal=meal,
        meal_request=meal_request,
        selected_role_codes=selected_role_codes,
        support_food_specs=support_food_specs,
        food_lookup=food_lookup,
    )
