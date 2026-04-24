"""Shared strict nutrition validation helpers for diet generation and regeneration."""
from __future__ import annotations

from typing import Any

from app.services.diet.common import calculate_difference_summary, calculate_macro_calories, round_diet_value
from app.services.diet.solver import calculate_meal_actuals_from_foods

STRICT_MEAL_NUTRITION_TOLERANCES: dict[str, float] = {
    "calories": 10.0,
    "protein_grams": 1.0,
    "carb_grams": 1.0,
    "fat_grams": 1.0,
}

STRICT_DAILY_NUTRITION_TOLERANCES: dict[str, float] = {
    "calories": 20.0,
    "protein_grams": 2.0,
    "carb_grams": 2.0,
    "fat_grams": 2.0,
}


def build_nutrition_validation_summary(
    *,
    actuals: dict[str, float],
    differences: dict[str, float],
    tolerances: dict[str, float],
) -> dict[str, Any]:
    absolute_differences = {
        "calories": abs(float(differences["calorie_difference"])),
        "protein_grams": abs(float(differences["protein_difference"])),
        "carb_grams": abs(float(differences["carb_difference"])),
        "fat_grams": abs(float(differences["fat_difference"])),
    }
    overflow = {
        field_name: max(absolute_differences[field_name] - float(tolerance), 0.0)
        for field_name, tolerance in tolerances.items()
    }
    overflow_ratios = {
        field_name: overflow[field_name] / max(float(tolerances[field_name]), 1e-6)
        for field_name in tolerances
    }
    error_ratios = {
        field_name: absolute_differences[field_name] / max(float(tolerances[field_name]), 1e-6)
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
        "tolerances": {
            field_name: float(tolerance)
            for field_name, tolerance in tolerances.items()
        },
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


def build_strict_meal_tolerances(_meal: Any | None = None) -> dict[str, float]:
    return dict(STRICT_MEAL_NUTRITION_TOLERANCES)


def build_strict_daily_tolerances() -> dict[str, float]:
    return dict(STRICT_DAILY_NUTRITION_TOLERANCES)


def summarize_meal_payload_nutrition(
    *,
    target_calories: float,
    target_protein_grams: float,
    target_fat_grams: float,
    target_carb_grams: float,
    foods: list[dict[str, Any]] | None = None,
    actuals_override: dict[str, float] | None = None,
    tolerances: dict[str, float] | None = None,
) -> dict[str, Any]:
    if foods:
        actuals = calculate_meal_actuals_from_foods(foods)
    else:
        actuals = {
            "actual_calories": float((actuals_override or {}).get("actual_calories") or 0.0),
            "actual_protein_grams": float((actuals_override or {}).get("actual_protein_grams") or 0.0),
            "actual_fat_grams": float((actuals_override or {}).get("actual_fat_grams") or 0.0),
            "actual_carb_grams": float((actuals_override or {}).get("actual_carb_grams") or 0.0),
        }

    differences = calculate_difference_summary(
        target_calories=target_calories,
        target_protein_grams=target_protein_grams,
        target_fat_grams=target_fat_grams,
        target_carb_grams=target_carb_grams,
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
    )
    return build_nutrition_validation_summary(
        actuals=actuals,
        differences=differences,
        tolerances=tolerances or build_strict_meal_tolerances(),
    )


def summarize_meal_plan_nutrition(
    *,
    meal,
    meal_plan: dict[str, Any],
    tolerances: dict[str, float] | None = None,
) -> dict[str, Any]:
    return summarize_meal_payload_nutrition(
        target_calories=float(meal.target_calories),
        target_protein_grams=float(meal.target_protein_grams),
        target_fat_grams=float(meal.target_fat_grams),
        target_carb_grams=float(meal.target_carb_grams),
        foods=list(meal_plan.get("foods", [])),
        actuals_override={
            "actual_calories": float(meal_plan.get("actual_calories") or 0.0),
            "actual_protein_grams": float(meal_plan.get("actual_protein_grams") or 0.0),
            "actual_fat_grams": float(meal_plan.get("actual_fat_grams") or 0.0),
            "actual_carb_grams": float(meal_plan.get("actual_carb_grams") or 0.0),
        },
        tolerances=tolerances or build_strict_meal_tolerances(meal),
    )


def summarize_daily_payload_nutrition(
    *,
    target_calories: float,
    target_protein_grams: float,
    target_fat_grams: float,
    target_carb_grams: float,
    meals: list[dict[str, Any]],
    tolerances: dict[str, float] | None = None,
) -> dict[str, Any]:
    actual_protein_grams = round_diet_value(sum(float(meal["actual_protein_grams"]) for meal in meals))
    actual_fat_grams = round_diet_value(sum(float(meal["actual_fat_grams"]) for meal in meals))
    actual_carb_grams = round_diet_value(sum(float(meal["actual_carb_grams"]) for meal in meals))
    actual_calories = round_diet_value(
        calculate_macro_calories(
            actual_protein_grams,
            actual_fat_grams,
            actual_carb_grams,
        )
    )
    daily_totals = calculate_difference_summary(
        target_calories=target_calories,
        target_protein_grams=target_protein_grams,
        target_fat_grams=target_fat_grams,
        target_carb_grams=target_carb_grams,
        actual_calories=actual_calories,
        actual_protein_grams=actual_protein_grams,
        actual_fat_grams=actual_fat_grams,
        actual_carb_grams=actual_carb_grams,
    )
    return build_nutrition_validation_summary(
        actuals={
            "actual_calories": float(actual_calories),
            "actual_protein_grams": float(actual_protein_grams),
            "actual_fat_grams": float(actual_fat_grams),
            "actual_carb_grams": float(actual_carb_grams),
        },
        differences={
            "calorie_difference": float(daily_totals["calorie_difference"]),
            "protein_difference": float(daily_totals["protein_difference"]),
            "fat_difference": float(daily_totals["fat_difference"]),
            "carb_difference": float(daily_totals["carb_difference"]),
        },
        tolerances=tolerances or build_strict_daily_tolerances(),
    )
