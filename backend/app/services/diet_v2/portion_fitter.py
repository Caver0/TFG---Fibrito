"""Portion fitting utilities for the diet generation v2 engine."""
from __future__ import annotations

import time
from typing import Any

from app.services.diet.common import calculate_difference_summary
from app.services.diet.constants import CORE_MACRO_KEYS
from app.services.diet.solver import (
    build_exact_meal_solution,
    build_food_portion,
    build_precise_food_values,
    calculate_meal_actuals_from_foods,
    get_food_macro_density,
    get_food_visibility_threshold,
    get_role_serving_floor,
    solve_linear_system,
)
from app.services.diet_v2.blueprints import MealBlueprint, blueprint_metadata

STRICT_REGEN_CALORIE_TOLERANCE_RATIO = 0.02
STRICT_REGEN_PROTEIN_TOLERANCE = 2.0
STRICT_REGEN_CARB_TOLERANCE = 3.0
STRICT_REGEN_FAT_TOLERANCE = 1.5

STRICT_REGEN_SEARCH_SCALES = (8.0, 4.0, 2.0, 1.0, 0.5, 0.25)
STRICT_REGEN_DIRECTIONAL_MULTIPLIERS = (-2.0, -1.0, 1.0, 2.0)
STRICT_REGEN_PAIRWISE_MULTIPLIERS = (-1.0, 1.0)


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


def _build_role_quantity_floor(
    food: dict[str, Any],
    *,
    role: str,
    meal_slot: str,
    meal_role: str,
) -> float:
    visibility_floor = get_food_visibility_threshold(food)
    serving_floor = get_role_serving_floor(
        food,
        role=role,
        meal_slot=meal_slot,
        meal_role=meal_role,
    )
    floor = max(
        visibility_floor,
        min(
            max(serving_floor * 0.4, 0.0),
            float(food.get("min_quantity") or serving_floor or visibility_floor or 0.0),
        ),
    )
    if floor <= 0:
        floor = visibility_floor
    return floor


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


def _get_food_calorie_density(food: dict[str, Any]) -> float:
    density = get_food_macro_density(food)
    return (
        (float(density["protein_grams"]) * 4.0)
        + (float(density["fat_grams"]) * 9.0)
        + (float(density["carb_grams"]) * 4.0)
    )


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
        floor = _build_role_quantity_floor(
            food,
            role=role,
            meal_slot=meal_request["meal_slot"],
            meal_role=meal_request["meal_role"],
        )
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


def _score_meal_actuals(
    *,
    calorie_difference: float,
    protein_difference: float,
    fat_difference: float,
    carb_difference: float,
) -> float:
    return (
        abs(calorie_difference)
        + abs(protein_difference) * 1.4
        + abs(fat_difference) * 1.2
        + abs(carb_difference) * 1.2
    )


def _build_regeneration_tolerances(meal) -> dict[str, float]:
    target_calories = max(float(meal.target_calories or 0.0), 0.0)
    return {
        "calories": max(target_calories * STRICT_REGEN_CALORIE_TOLERANCE_RATIO, 1.0),
        "protein_grams": STRICT_REGEN_PROTEIN_TOLERANCE,
        "carb_grams": STRICT_REGEN_CARB_TOLERANCE,
        "fat_grams": STRICT_REGEN_FAT_TOLERANCE,
    }


def _build_regeneration_nutrition_summary(
    *,
    meal,
    actuals: dict[str, float],
    differences: dict[str, float],
) -> dict[str, Any]:
    tolerances = _build_regeneration_tolerances(meal)
    absolute_differences = {
        "calories": abs(float(differences["calorie_difference"])),
        "protein_grams": abs(float(differences["protein_difference"])),
        "carb_grams": abs(float(differences["carb_difference"])),
        "fat_grams": abs(float(differences["fat_difference"])),
    }
    overflow = {
        field_name: max(absolute_differences[field_name] - tolerance, 0.0)
        for field_name, tolerance in tolerances.items()
    }
    overflow_ratios = {
        field_name: overflow[field_name] / max(tolerances[field_name], 1e-6)
        for field_name in tolerances
    }
    error_ratios = {
        field_name: absolute_differences[field_name] / max(tolerances[field_name], 1e-6)
        for field_name in tolerances
    }
    out_of_tolerance_fields = [
        field_name
        for field_name, overflow_value in overflow.items()
        if overflow_value > 1e-6
    ]
    return {
        **actuals,
        **differences,
        "tolerances": tolerances,
        "absolute_differences": absolute_differences,
        "overflow": overflow,
        "overflow_ratios": overflow_ratios,
        "within_tolerance": not out_of_tolerance_fields,
        "out_of_tolerance_fields": out_of_tolerance_fields,
        "normalized_overflow_score": sum(overflow_ratios.values()),
        "normalized_error_score": sum(error_ratios.values()),
        "max_overflow_ratio": max(overflow_ratios.values(), default=0.0),
        "max_error_ratio": max(error_ratios.values(), default=0.0),
    }


def _build_regeneration_nutrition_ranking(
    nutrition_summary: dict[str, Any],
) -> tuple[float, ...]:
    absolute_differences = dict(nutrition_summary.get("absolute_differences") or {})
    tolerances = dict(nutrition_summary.get("tolerances") or {})
    return (
        0.0 if nutrition_summary.get("within_tolerance") else 1.0,
        float(nutrition_summary.get("max_overflow_ratio") or 0.0),
        float(nutrition_summary.get("normalized_overflow_score") or 0.0),
        float(nutrition_summary.get("normalized_error_score") or 0.0),
        absolute_differences.get("calories", 0.0) / max(float(tolerances.get("calories") or 1.0), 1e-6),
        absolute_differences.get("protein_grams", 0.0) / max(float(tolerances.get("protein_grams") or 1.0), 1e-6),
        absolute_differences.get("carb_grams", 0.0) / max(float(tolerances.get("carb_grams") or 1.0), 1e-6),
        absolute_differences.get("fat_grams", 0.0) / max(float(tolerances.get("fat_grams") or 1.0), 1e-6),
    )


def _build_regeneration_evaluation_ranking(
    evaluation: dict[str, Any],
) -> tuple[float, ...]:
    return (
        *_build_regeneration_nutrition_ranking(evaluation["nutrition_summary"]),
        float(evaluation["score"] or 0.0),
    )


def _is_better_regeneration_evaluation(
    candidate_evaluation: dict[str, Any],
    best_evaluation: dict[str, Any],
) -> bool:
    return _build_regeneration_evaluation_ranking(candidate_evaluation) < _build_regeneration_evaluation_ranking(best_evaluation)


def _build_quantity_search_step(food: dict[str, Any]) -> float:
    configured_step = float(food.get("step") or 0.0)
    reference_unit = str(food.get("reference_unit") or "").strip().lower()
    minimum_step = 0.05 if reference_unit == "unidad" else 0.5
    if configured_step > 0:
        return max(configured_step * 0.25, minimum_step)
    return minimum_step


def _evaluate_regeneration_quantities(
    *,
    meal,
    meal_plan: dict[str, Any],
    role_foods: dict[str, dict[str, Any]],
    support_food_specs: list[dict[str, Any]],
    food_lookup: dict[str, dict[str, Any]],
    role_quantities: dict[str, float],
) -> dict[str, Any]:
    rebuilt_foods_by_code: dict[str, dict[str, Any]] = {}
    for role, food in role_foods.items():
        rebuilt_foods_by_code[str(food["code"])] = build_food_portion(food, role_quantities[role])
    for support_food in support_food_specs:
        support_code = str(support_food.get("food_code") or "").strip()
        if support_code not in food_lookup:
            continue
        rebuilt_foods_by_code[support_code] = build_food_portion(
            food_lookup[support_code],
            float(support_food.get("quantity") or 0.0),
        )

    ordered_foods: list[dict[str, Any]] = []
    used_codes: set[str] = set()
    for original_food in meal_plan.get("foods", []):
        food_code = str(original_food.get("food_code") or "").strip()
        if food_code in rebuilt_foods_by_code and food_code not in used_codes:
            ordered_foods.append(rebuilt_foods_by_code[food_code])
            used_codes.add(food_code)
    for support_food in support_food_specs:
        support_code = str(support_food.get("food_code") or "").strip()
        if support_code in rebuilt_foods_by_code and support_code not in used_codes:
            ordered_foods.append(rebuilt_foods_by_code[support_code])
            used_codes.add(support_code)
    for role in ("protein", "carb", "fat"):
        food_code = str(role_foods[role]["code"])
        if food_code in rebuilt_foods_by_code and food_code not in used_codes:
            ordered_foods.append(rebuilt_foods_by_code[food_code])
            used_codes.add(food_code)

    actuals = calculate_meal_actuals_from_foods(ordered_foods)
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
    actuals["score"] = _score_meal_actuals(
        calorie_difference=actuals["calorie_difference"],
        protein_difference=actuals["protein_difference"],
        fat_difference=actuals["fat_difference"],
        carb_difference=actuals["carb_difference"],
    )
    nutrition_summary = _build_regeneration_nutrition_summary(
        meal=meal,
        actuals={
            "actual_calories": actuals["actual_calories"],
            "actual_protein_grams": actuals["actual_protein_grams"],
            "actual_fat_grams": actuals["actual_fat_grams"],
            "actual_carb_grams": actuals["actual_carb_grams"],
        },
        differences={
            "calorie_difference": actuals["calorie_difference"],
            "protein_difference": actuals["protein_difference"],
            "fat_difference": actuals["fat_difference"],
            "carb_difference": actuals["carb_difference"],
        },
    )
    actuals["foods"] = ordered_foods
    actuals["role_quantities"] = dict(role_quantities)
    actuals["nutrition_summary"] = nutrition_summary
    actuals["nutrition_ranking"] = _build_regeneration_nutrition_ranking(nutrition_summary)
    return actuals


def _clamp_regeneration_quantities(
    role_quantities: dict[str, float],
    role_bounds: dict[str, tuple[float, float]],
) -> dict[str, float]:
    return {
        role: min(max(float(quantity), role_bounds[role][0]), role_bounds[role][1])
        for role, quantity in role_quantities.items()
        if role in role_bounds
    }


def _solve_weighted_regeneration_quantities(
    *,
    matrix_rows: list[list[float]],
    target_values: list[float],
    weights: list[float],
) -> list[float] | None:
    normal_matrix: list[list[float]] = []
    normal_values: list[float] = []
    variable_count = len(matrix_rows[0]) if matrix_rows else 0
    if variable_count == 0:
        return None

    for column_index in range(variable_count):
        normal_values.append(
            sum(
                float(weights[row_index]) * float(matrix_rows[row_index][column_index]) * float(target_values[row_index])
                for row_index in range(len(matrix_rows))
            )
        )
        normal_matrix.append([
            sum(
                float(weights[row_index])
                * float(matrix_rows[row_index][column_index])
                * float(matrix_rows[row_index][inner_index])
                for row_index in range(len(matrix_rows))
            )
            for inner_index in range(variable_count)
        ])
    return solve_linear_system(normal_matrix, normal_values)


def apply_regeneration_micro_adjustment(
    *,
    meal,
    meal_plan: dict[str, Any],
    meal_slot: str,
    meal_role: str,
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    selected_role_codes = {
        role: str(food_code or "").strip()
        for role, food_code in dict(meal_plan.get("selected_role_codes", {})).items()
        if str(food_code or "").strip()
    }
    support_food_specs = list(meal_plan.get("support_food_specs", []))
    adjustment_payload = {
        "attempted": False,
        "applied": False,
        "method": "strict_quantity_refit_v2",
        "initial_fit_method": meal_plan.get("portion_fit_method", "exact"),
        "score_before": None,
        "score_after": None,
        "iterations": 0,
        "elapsed_seconds": 0.0,
    }
    if len(selected_role_codes) != 3:
        adjustment_payload["elapsed_seconds"] = time.perf_counter() - started_at
        return {
            **meal_plan,
            "regeneration_micro_adjustment": adjustment_payload,
        }

    role_foods = {
        role: food_lookup[food_code]
        for role, food_code in selected_role_codes.items()
        if food_code in food_lookup
    }
    if len(role_foods) != 3:
        adjustment_payload["elapsed_seconds"] = time.perf_counter() - started_at
        return {
            **meal_plan,
            "regeneration_micro_adjustment": adjustment_payload,
        }

    meal_foods_by_code = {
        str(food.get("food_code") or "").strip(): food
        for food in meal_plan.get("foods", [])
        if str(food.get("food_code") or "").strip()
    }
    role_bounds: dict[str, tuple[float, float]] = {}
    role_quantities: dict[str, float] = {}
    for role in ("protein", "carb", "fat"):
        food = role_foods[role]
        floor = _build_role_quantity_floor(
            food,
            role=role,
            meal_slot=meal_slot,
            meal_role=meal_role,
        )
        max_quantity = max(
            float(food.get("max_quantity") or 0.0),
            floor,
            float(meal_foods_by_code.get(str(food["code"]), {}).get("quantity") or 0.0),
        )
        role_bounds[role] = (floor, max_quantity)
        current_quantity = float(meal_foods_by_code.get(str(food["code"]), {}).get("quantity") or floor)
        role_quantities[role] = min(max(current_quantity, floor), max_quantity)

    current_evaluation = _evaluate_regeneration_quantities(
        meal=meal,
        meal_plan=meal_plan,
        role_foods=role_foods,
        support_food_specs=support_food_specs,
        food_lookup=food_lookup,
        role_quantities=role_quantities,
    )
    adjustment_payload["attempted"] = True
    adjustment_payload["score_before"] = current_evaluation["score"]
    if current_evaluation["nutrition_summary"]["within_tolerance"]:
        adjustment_payload["score_after"] = current_evaluation["score"]
        adjustment_payload["elapsed_seconds"] = time.perf_counter() - started_at
        return {
            **meal_plan,
            "foods": current_evaluation["foods"],
            "actual_calories": current_evaluation["actual_calories"],
            "actual_protein_grams": current_evaluation["actual_protein_grams"],
            "actual_fat_grams": current_evaluation["actual_fat_grams"],
            "actual_carb_grams": current_evaluation["actual_carb_grams"],
            "calorie_difference": current_evaluation["calorie_difference"],
            "protein_difference": current_evaluation["protein_difference"],
            "fat_difference": current_evaluation["fat_difference"],
            "carb_difference": current_evaluation["carb_difference"],
            "score": current_evaluation["score"],
            "regeneration_micro_adjustment": adjustment_payload,
        }

    best_evaluation = current_evaluation
    role_order = ("protein", "carb", "fat")
    macro_matrix = [
        [get_food_macro_density(role_foods[role]).get(macro_key, 0.0) for role in role_order]
        for macro_key in CORE_MACRO_KEYS
    ]
    support_totals = _build_support_totals(support_food_specs, food_lookup)
    macro_target_vector = [
        float(meal.target_protein_grams) - support_totals["protein_grams"],
        float(meal.target_fat_grams) - support_totals["fat_grams"],
        float(meal.target_carb_grams) - support_totals["carb_grams"],
    ]
    candidate_seeds: list[dict[str, float]] = [dict(role_quantities)]

    solved_quantities = solve_linear_system(macro_matrix, macro_target_vector)
    if solved_quantities is not None:
        candidate_seeds.append(_clamp_regeneration_quantities(
            {
                role: float(solved_quantities[index])
                for index, role in enumerate(role_order)
            },
            role_bounds,
        ))

    weighted_matrix = [
        [_get_food_calorie_density(role_foods[role]) for role in role_order],
        [get_food_macro_density(role_foods[role]).get("protein_grams", 0.0) for role in role_order],
        [get_food_macro_density(role_foods[role]).get("carb_grams", 0.0) for role in role_order],
        [get_food_macro_density(role_foods[role]).get("fat_grams", 0.0) for role in role_order],
    ]
    weighted_targets = [
        float(meal.target_calories) - support_totals["calories"],
        float(meal.target_protein_grams) - support_totals["protein_grams"],
        float(meal.target_carb_grams) - support_totals["carb_grams"],
        float(meal.target_fat_grams) - support_totals["fat_grams"],
    ]
    strict_tolerances = _build_regeneration_tolerances(meal)
    weighted_solution = _solve_weighted_regeneration_quantities(
        matrix_rows=weighted_matrix,
        target_values=weighted_targets,
        weights=[
            1.0 / max(strict_tolerances["calories"] ** 2, 1e-6),
            1.0 / max(strict_tolerances["protein_grams"] ** 2, 1e-6),
            1.0 / max(strict_tolerances["carb_grams"] ** 2, 1e-6),
            1.0 / max(strict_tolerances["fat_grams"] ** 2, 1e-6),
        ],
    )
    if weighted_solution is not None:
        candidate_seeds.append(_clamp_regeneration_quantities(
            {
                role: float(weighted_solution[index])
                for index, role in enumerate(role_order)
            },
            role_bounds,
        ))

    seen_quantity_keys: set[tuple[tuple[str, float], ...]] = set()

    def maybe_promote_candidate(candidate_quantities: dict[str, float]) -> None:
        nonlocal best_evaluation
        quantity_key = tuple(
            (role, round(float(candidate_quantities[role]), 6))
            for role in role_order
        )
        if quantity_key in seen_quantity_keys:
            return
        seen_quantity_keys.add(quantity_key)
        candidate_evaluation = _evaluate_regeneration_quantities(
            meal=meal,
            meal_plan=meal_plan,
            role_foods=role_foods,
            support_food_specs=support_food_specs,
            food_lookup=food_lookup,
            role_quantities=candidate_quantities,
        )
        if _is_better_regeneration_evaluation(candidate_evaluation, best_evaluation):
            best_evaluation = candidate_evaluation
            adjustment_payload["iterations"] += 1

    for candidate_seed in candidate_seeds:
        maybe_promote_candidate(candidate_seed)
        if best_evaluation["nutrition_summary"]["within_tolerance"]:
            break

    for _ in range(10):
        if best_evaluation["nutrition_summary"]["within_tolerance"]:
            break
        residual_vector = [
            float(meal.target_protein_grams) - best_evaluation["actual_protein_grams"],
            float(meal.target_fat_grams) - best_evaluation["actual_fat_grams"],
            float(meal.target_carb_grams) - best_evaluation["actual_carb_grams"],
        ]
        delta_quantities = solve_linear_system(macro_matrix, residual_vector)
        if delta_quantities is None:
            break
        improved = False
        for scale in (1.0, 0.75, 0.5, 0.25, 0.1):
            candidate_quantities = _clamp_regeneration_quantities(
                {
                    role: best_evaluation["role_quantities"][role] + float(delta_quantities[index]) * scale
                    for index, role in enumerate(role_order)
                },
                role_bounds,
            )
            previous_ranking = _build_regeneration_evaluation_ranking(best_evaluation)
            maybe_promote_candidate(candidate_quantities)
            improved = _build_regeneration_evaluation_ranking(best_evaluation) < previous_ranking
            if improved:
                break
        if not improved:
            break

    for scale in STRICT_REGEN_SEARCH_SCALES:
        stage_improved = True
        while stage_improved and not best_evaluation["nutrition_summary"]["within_tolerance"]:
            stage_improved = False
            stage_best = best_evaluation
            prioritized_roles = rank_regeneration_problem_roles(
                meal_plan={
                    **meal_plan,
                    "selected_role_codes": selected_role_codes,
                    "foods": best_evaluation["foods"],
                },
                nutrition_summary=best_evaluation["nutrition_summary"],
                food_lookup=food_lookup,
            )
            role_visit_order = [
                role
                for role in (*prioritized_roles, *role_order)
                if role in role_order
            ]
            visited_roles: set[str] = set()
            role_visit_order = [
                role
                for role in role_visit_order
                if not (role in visited_roles or visited_roles.add(role))
            ]

            def maybe_stage_promote(candidate_quantities: dict[str, float]) -> None:
                nonlocal stage_best
                quantity_key = tuple(
                    (role, round(float(candidate_quantities[role]), 6))
                    for role in role_order
                )
                if quantity_key in seen_quantity_keys:
                    return
                seen_quantity_keys.add(quantity_key)
                candidate_evaluation = _evaluate_regeneration_quantities(
                    meal=meal,
                    meal_plan=meal_plan,
                    role_foods=role_foods,
                    support_food_specs=support_food_specs,
                    food_lookup=food_lookup,
                    role_quantities=candidate_quantities,
                )
                if _is_better_regeneration_evaluation(candidate_evaluation, stage_best):
                    stage_best = candidate_evaluation

            for role in role_visit_order:
                search_step = _build_quantity_search_step(role_foods[role]) * scale
                for direction in STRICT_REGEN_DIRECTIONAL_MULTIPLIERS:
                    candidate_quantities = dict(best_evaluation["role_quantities"])
                    candidate_quantities[role] = candidate_quantities[role] + (search_step * direction)
                    maybe_stage_promote(_clamp_regeneration_quantities(candidate_quantities, role_bounds))

            if len(role_visit_order) >= 2:
                primary_role, secondary_role = role_visit_order[:2]
                primary_step = _build_quantity_search_step(role_foods[primary_role]) * scale
                secondary_step = _build_quantity_search_step(role_foods[secondary_role]) * scale
                for primary_direction in STRICT_REGEN_PAIRWISE_MULTIPLIERS:
                    for secondary_direction in STRICT_REGEN_PAIRWISE_MULTIPLIERS:
                        candidate_quantities = dict(best_evaluation["role_quantities"])
                        candidate_quantities[primary_role] = candidate_quantities[primary_role] + (primary_step * primary_direction)
                        candidate_quantities[secondary_role] = candidate_quantities[secondary_role] + (secondary_step * secondary_direction)
                        maybe_stage_promote(_clamp_regeneration_quantities(candidate_quantities, role_bounds))

            if _is_better_regeneration_evaluation(stage_best, best_evaluation):
                best_evaluation = stage_best
                adjustment_payload["iterations"] += 1
                stage_improved = True

    adjustment_payload["score_after"] = best_evaluation["score"]
    adjustment_payload["applied"] = _is_better_regeneration_evaluation(best_evaluation, current_evaluation)
    adjustment_payload["elapsed_seconds"] = time.perf_counter() - started_at
    if not adjustment_payload["applied"]:
        return {
            **meal_plan,
            "foods": current_evaluation["foods"],
            "actual_calories": current_evaluation["actual_calories"],
            "actual_protein_grams": current_evaluation["actual_protein_grams"],
            "actual_fat_grams": current_evaluation["actual_fat_grams"],
            "actual_carb_grams": current_evaluation["actual_carb_grams"],
            "calorie_difference": current_evaluation["calorie_difference"],
            "protein_difference": current_evaluation["protein_difference"],
            "fat_difference": current_evaluation["fat_difference"],
            "carb_difference": current_evaluation["carb_difference"],
            "score": current_evaluation["score"],
            "regeneration_micro_adjustment": adjustment_payload,
        }

    return {
        **meal_plan,
        "foods": best_evaluation["foods"],
        "actual_calories": best_evaluation["actual_calories"],
        "actual_protein_grams": best_evaluation["actual_protein_grams"],
        "actual_fat_grams": best_evaluation["actual_fat_grams"],
        "actual_carb_grams": best_evaluation["actual_carb_grams"],
        "calorie_difference": best_evaluation["calorie_difference"],
        "protein_difference": best_evaluation["protein_difference"],
        "fat_difference": best_evaluation["fat_difference"],
        "carb_difference": best_evaluation["carb_difference"],
        "score": best_evaluation["score"],
        "regeneration_micro_adjustment": adjustment_payload,
    }

def summarize_regeneration_nutrition(
    *,
    meal,
    meal_plan: dict[str, Any],
) -> dict[str, Any]:
    foods = list(meal_plan.get("foods", []))
    if foods:
        actuals = calculate_meal_actuals_from_foods(foods)
        differences = calculate_difference_summary(
            target_calories=meal.target_calories,
            target_protein_grams=meal.target_protein_grams,
            target_fat_grams=meal.target_fat_grams,
            target_carb_grams=meal.target_carb_grams,
            actual_calories=actuals["actual_calories"],
            actual_protein_grams=actuals["actual_protein_grams"],
            actual_fat_grams=actuals["actual_fat_grams"],
            actual_carb_grams=actuals["actual_carb_grams"],
        )
    else:
        actuals = {
            "actual_calories": float(meal_plan.get("actual_calories") or 0.0),
            "actual_protein_grams": float(meal_plan.get("actual_protein_grams") or 0.0),
            "actual_fat_grams": float(meal_plan.get("actual_fat_grams") or 0.0),
            "actual_carb_grams": float(meal_plan.get("actual_carb_grams") or 0.0),
        }
        differences = calculate_difference_summary(
            target_calories=meal.target_calories,
            target_protein_grams=meal.target_protein_grams,
            target_fat_grams=meal.target_fat_grams,
            target_carb_grams=meal.target_carb_grams,
            actual_calories=actuals["actual_calories"],
            actual_protein_grams=actuals["actual_protein_grams"],
            actual_fat_grams=actuals["actual_fat_grams"],
            actual_carb_grams=actuals["actual_carb_grams"],
        )
    return _build_regeneration_nutrition_summary(
        meal=meal,
        actuals=actuals,
        differences=differences,
    )


def rank_regeneration_problem_roles(
    *,
    meal_plan: dict[str, Any],
    nutrition_summary: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    selected_role_codes = {
        role: str(food_code or "").strip()
        for role, food_code in dict(meal_plan.get("selected_role_codes", {})).items()
        if str(food_code or "").strip()
    }
    role_foods = {
        role: food_lookup[food_code]
        for role, food_code in selected_role_codes.items()
        if food_code in food_lookup
    }
    if len(role_foods) != 3:
        return [role for role in ("protein", "carb", "fat") if role in selected_role_codes]

    macro_by_role = {
        "protein": "protein_grams",
        "carb": "carb_grams",
        "fat": "fat_grams",
    }
    macro_field_order = ("protein_grams", "carb_grams", "fat_grams")
    role_scores = {role: 0.0 for role in ("protein", "carb", "fat")}
    normalized_error = {
        macro_field: float(nutrition_summary["absolute_differences"][macro_field]) / max(
            float(nutrition_summary["tolerances"][macro_field]),
            1e-6,
        )
        for macro_field in macro_field_order
    }
    for role in ("protein", "carb", "fat"):
        food_density = get_food_macro_density(role_foods[role])
        dominant_macro = macro_by_role[role]
        dominant_density = max(float(food_density.get(dominant_macro, 0.0)), 1e-6)
        for macro_field in macro_field_order:
            macro_density = max(float(food_density.get(macro_field, 0.0)), 0.0)
            dominance_weight = 1.7 if macro_field == dominant_macro else min(macro_density / dominant_density, 1.3)
            role_scores[role] += normalized_error[macro_field] * dominance_weight

    sorted_roles = sorted(
        role_scores,
        key=lambda role: (-role_scores[role], ("protein", "carb", "fat").index(role)),
    )
    return [role for role in sorted_roles if role_scores[role] > 0]


def _build_regeneration_bound_signals(
    *,
    meal_plan: dict[str, Any],
    meal_slot: str,
    meal_role: str,
    food_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_role_codes = {
        role: str(food_code or "").strip()
        for role, food_code in dict(meal_plan.get("selected_role_codes", {})).items()
        if str(food_code or "").strip()
    }
    meal_foods_by_code = {
        str(food.get("food_code") or "").strip(): food
        for food in meal_plan.get("foods", [])
        if str(food.get("food_code") or "").strip()
    }
    bound_signals: list[dict[str, Any]] = []
    for role in ("protein", "carb", "fat"):
        food_code = selected_role_codes.get(role)
        if not food_code or food_code not in food_lookup:
            continue
        food = food_lookup[food_code]
        floor = _build_role_quantity_floor(
            food,
            role=role,
            meal_slot=meal_slot,
            meal_role=meal_role,
        )
        max_quantity = max(
            float(food.get("max_quantity") or 0.0),
            floor,
        )
        current_quantity = float(meal_foods_by_code.get(food_code, {}).get("quantity") or 0.0)
        step = _build_quantity_search_step(food)
        if abs(current_quantity - floor) <= max(step, 1e-6):
            bound_signals.append({
                "role": role,
                "bound": "floor",
                "quantity": current_quantity,
            })
        if abs(current_quantity - max_quantity) <= max(step, 1e-6):
            bound_signals.append({
                "role": role,
                "bound": "max",
                "quantity": current_quantity,
            })
    return bound_signals


def finalize_regeneration_candidate(
    *,
    meal,
    meal_plan: dict[str, Any],
    meal_slot: str,
    meal_role: str,
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    adjusted_plan = apply_regeneration_micro_adjustment(
        meal=meal,
        meal_plan=meal_plan,
        meal_slot=meal_slot,
        meal_role=meal_role,
        food_lookup=food_lookup,
    )
    nutrition_summary = summarize_regeneration_nutrition(
        meal=meal,
        meal_plan=adjusted_plan,
    )
    nutrition_summary["problem_roles"] = rank_regeneration_problem_roles(
        meal_plan=adjusted_plan,
        nutrition_summary=nutrition_summary,
        food_lookup=food_lookup,
    )
    nutrition_summary["bound_signals"] = _build_regeneration_bound_signals(
        meal_plan=adjusted_plan,
        meal_slot=meal_slot,
        meal_role=meal_role,
        food_lookup=food_lookup,
    )
    nutrition_summary["fit_method"] = adjusted_plan.get("portion_fit_method", "exact")
    nutrition_summary["accepted_with_residual_error"] = False
    nutrition_summary["residual_reason"] = None
    return {
        **adjusted_plan,
        "actual_calories": nutrition_summary["actual_calories"],
        "actual_protein_grams": nutrition_summary["actual_protein_grams"],
        "actual_fat_grams": nutrition_summary["actual_fat_grams"],
        "actual_carb_grams": nutrition_summary["actual_carb_grams"],
        "calorie_difference": nutrition_summary["calorie_difference"],
        "protein_difference": nutrition_summary["protein_difference"],
        "fat_difference": nutrition_summary["fat_difference"],
        "carb_difference": nutrition_summary["carb_difference"],
        "nutrition_validation": nutrition_summary,
    }
