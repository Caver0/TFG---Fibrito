"""Utilidades comunes de redondeo y contexto para dietas."""

import hashlib
import json

from app.schemas.diet import DietMeal
from app.services.meal_distribution_service import round_distribution_value
from app.utils.meal_roles import get_meal_slot as _resolve_meal_slot

from app.services.diet.constants import (
    DEFAULT_FOOD_DATA_SOURCE,
    DIET_SOURCE_MAP,
    FOOD_VALUE_PRECISION,
    MACRO_CALORIE_FACTORS,
    VALID_MEAL_ROLES,
    VALID_MEAL_SLOTS,
)


def normalize_diet_food_source(value: str | None) -> str:
    return DIET_SOURCE_MAP.get(str(value or "").strip(), DEFAULT_FOOD_DATA_SOURCE)


def round_diet_value(value: float) -> float:
    rounded_value = round_distribution_value(value)
    return 0.0 if abs(rounded_value) < 0.05 else rounded_value


def round_food_value(value: float) -> float:
    rounded_value = round(value, FOOD_VALUE_PRECISION)
    return 0.0 if abs(rounded_value) < 10 ** (-FOOD_VALUE_PRECISION) else rounded_value


def calculate_macro_calories(protein_grams: float, fat_grams: float, carb_grams: float) -> float:
    return (
        (protein_grams * MACRO_CALORIE_FACTORS["protein_grams"])
        + (fat_grams * MACRO_CALORIE_FACTORS["fat_grams"])
        + (carb_grams * MACRO_CALORIE_FACTORS["carb_grams"])
    )


def calculate_difference(actual_value: float, target_value: float) -> float:
    return round_diet_value(actual_value - target_value)


def calculate_difference_summary(
    *,
    target_calories: float,
    target_protein_grams: float,
    target_fat_grams: float,
    target_carb_grams: float,
    actual_calories: float,
    actual_protein_grams: float,
    actual_fat_grams: float,
    actual_carb_grams: float,
) -> dict[str, float]:
    return {
        "calorie_difference": calculate_difference(actual_calories, target_calories),
        "protein_difference": calculate_difference(actual_protein_grams, target_protein_grams),
        "fat_difference": calculate_difference(actual_fat_grams, target_fat_grams),
        "carb_difference": calculate_difference(actual_carb_grams, target_carb_grams),
    }


def get_meal_slot(meal_index: int, meals_count: int) -> str:
    return _resolve_meal_slot(meal_index, meals_count)


def normalize_meal_slot(meal_slot: str | None, *, meal_index: int, meals_count: int) -> str:
    normalized_slot = str(meal_slot or "").strip().lower()
    if normalized_slot in VALID_MEAL_SLOTS:
        return normalized_slot

    return get_meal_slot(meal_index, meals_count)


def normalize_meal_role(
    meal_role: str | None,
    *,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
) -> str:
    normalized_role = str(meal_role or "").strip().lower()
    if normalized_role in VALID_MEAL_ROLES:
        if training_focus and normalized_role == "meal":
            return "training_focus"
        return normalized_role

    if training_focus:
        return "training_focus"
    if meal_index == 0:
        return "breakfast"
    if meal_index == meals_count - 1:
        return "dinner"
    return "meal"


def resolve_meal_context(
    meal: DietMeal,
    *,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
) -> tuple[str, str]:
    return (
        normalize_meal_slot(getattr(meal, "meal_slot", None), meal_index=meal_index, meals_count=meals_count),
        normalize_meal_role(
            getattr(meal, "meal_role", None),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
        ),
    )


def rotate_codes(codes: list[str], rotation_seed: int) -> list[str]:
    if not codes:
        return []

    shift = rotation_seed % len(codes)
    return codes[shift:] + codes[:shift]


def _normalize_seed_part(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _normalize_seed_part(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_seed_part(item) for item in value]
    if isinstance(value, set):
        return [_normalize_seed_part(item) for item in sorted(value, key=lambda item: str(item))]
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_variety_seed(*parts: object) -> int:
    serialized_parts = json.dumps(
        [_normalize_seed_part(part) for part in parts],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.blake2b(
        serialized_parts.encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") % 1_000_000_000
