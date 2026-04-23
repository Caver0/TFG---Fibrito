"""Pure helpers for nutrition calculations."""
from collections.abc import Mapping
from typing import Any

from app.schemas.nutrition import NutritionCalculationInput, NutritionSummary


class NutritionProfileIncompleteError(ValueError):
    def __init__(self, missing_fields: list[str]):
        self.missing_fields = missing_fields
        message = "Faltan datos obligatorios para calcular la nutricion: " + ", ".join(missing_fields)
        super().__init__(message)


def round_nutrition(value: float) -> float:
    return round(value, 1)


def calculate_bmr(age: int, sex: str, height: float, current_weight: float) -> float:
    base = (10 * current_weight) + (6.25 * height) - (5 * age)
    if sex == "Masculino":
        return base + 5
    return base - 161


def get_activity_factor_from_training_days(training_days_per_week: int) -> float:
    if training_days_per_week <= 1:
        return 1.2
    if training_days_per_week <= 3:
        return 1.375
    if training_days_per_week <= 5:
        return 1.55
    return 1.725


def calculate_tdee(bmr: float, training_days_per_week: int) -> float:
    activity_factor = get_activity_factor_from_training_days(training_days_per_week)
    return bmr * activity_factor


def calculate_target_calories(tdee: float, goal: str) -> float:
    goal_factors = {
        "perder_grasa": 0.85,
        "mantener_peso": 1.0,
        "ganar_masa": 1.12,
    }
    return tdee * goal_factors[goal]


_PROTEIN_GRAMS_PER_KG = 2.0
_FAT_GRAMS_PER_KG = 0.8


def calculate_macros(current_weight: float, target_calories: float) -> dict[str, float]:
    protein_grams = current_weight * _PROTEIN_GRAMS_PER_KG
    # Mantenemos la grasa contenida y estable; los reajustes de calorías deben
    # empujar principalmente carbohidratos, no inflar la grasa objetivo.
    fat_grams = current_weight * _FAT_GRAMS_PER_KG
    protein_calories = protein_grams * 4
    fat_calories = fat_grams * 9
    carb_calories = max(0.0, target_calories - protein_calories - fat_calories)
    carb_grams = carb_calories / 4
    return {
        "protein_grams": round_nutrition(protein_grams),
        "fat_grams": round_nutrition(fat_grams),
        "carb_grams": round_nutrition(carb_grams),
    }


def get_missing_nutrition_fields(profile: NutritionCalculationInput | Mapping[str, Any] | Any) -> list[str]:
    if isinstance(profile, NutritionCalculationInput):
        return []

    if hasattr(profile, "model_dump"):
        data = profile.model_dump()
    else:
        data = dict(profile)

    required_fields = [
        "age",
        "sex",
        "height",
        "current_weight",
        "training_days_per_week",
        "goal",
    ]
    return [field_name for field_name in required_fields if data.get(field_name) is None]


def get_default_target_calories(
    profile: NutritionCalculationInput | Mapping[str, Any] | Any,
) -> float:
    missing_fields = get_missing_nutrition_fields(profile)
    if missing_fields:
        raise NutritionProfileIncompleteError(missing_fields)

    if isinstance(profile, NutritionCalculationInput):
        input_data = profile
    elif hasattr(profile, "model_dump"):
        input_data = NutritionCalculationInput.model_validate(profile.model_dump())
    else:
        input_data = NutritionCalculationInput.model_validate(dict(profile))

    bmr = calculate_bmr(
        age=input_data.age,
        sex=input_data.sex,
        height=input_data.height,
        current_weight=input_data.current_weight,
    )
    tdee = calculate_tdee(bmr, input_data.training_days_per_week)
    return calculate_target_calories(tdee, input_data.goal)


def build_nutrition_summary(
    profile: NutritionCalculationInput | Mapping[str, Any] | Any,
    target_calories_override: float | None = None,
) -> NutritionSummary:
    missing_fields = get_missing_nutrition_fields(profile)
    if missing_fields:
        raise NutritionProfileIncompleteError(missing_fields)

    if isinstance(profile, NutritionCalculationInput):
        input_data = profile
    elif hasattr(profile, "model_dump"):
        input_data = NutritionCalculationInput.model_validate(profile.model_dump())
    else:
        input_data = NutritionCalculationInput.model_validate(dict(profile))

    bmr = calculate_bmr(
        age=input_data.age,
        sex=input_data.sex,
        height=input_data.height,
        current_weight=input_data.current_weight,
    )
    activity_factor = get_activity_factor_from_training_days(input_data.training_days_per_week)
    tdee = calculate_tdee(bmr, input_data.training_days_per_week)
    target_calories = (
        target_calories_override
        if target_calories_override is not None
        else calculate_target_calories(tdee, input_data.goal)
    )
    macros = calculate_macros(input_data.current_weight, target_calories)
    aligned_target_calories = round_nutrition(
        (macros["protein_grams"] * 4.0)
        + (macros["fat_grams"] * 9.0)
        + (macros["carb_grams"] * 4.0)
    )

    return NutritionSummary(
        age=input_data.age,
        sex=input_data.sex,
        height=round_nutrition(input_data.height),
        current_weight=round_nutrition(input_data.current_weight),
        training_days_per_week=input_data.training_days_per_week,
        goal=input_data.goal,
        activity_factor=activity_factor,
        bmr=round_nutrition(bmr),
        tdee=round_nutrition(tdee),
        target_calories=aligned_target_calories,
        protein_grams=round_nutrition(macros["protein_grams"]),
        fat_grams=round_nutrition(macros["fat_grams"]),
        carb_grams=round_nutrition(macros["carb_grams"]),
    )
