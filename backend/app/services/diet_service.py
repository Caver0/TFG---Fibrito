"""Food-based diet generation and persistence."""
from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietListItem, DietMeal, TrainingTimeOfDay, serialize_daily_diet, serialize_diet_list_item
from app.schemas.user import UserPublic
from app.services.food_classifier_service import predict_meal_slot_scores
from app.services.food_catalog_service import get_food_catalog_version, get_internal_food_lookup, resolve_foods_by_codes
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import (
    FoodPreferenceConflictError,
    apply_user_food_preferences,
    build_user_food_preferences_profile,
    count_food_preference_matches,
    count_preferred_food_matches_in_meals,
    prioritize_preferred_foods,
)
from app.services.meal_distribution_service import generate_meal_distribution_targets, round_distribution_value
from app.utils.normalization import normalize_food_name

DEFAULT_FOOD_DATA_SOURCE = "internal"
CACHE_FOOD_DATA_SOURCE = "cache"
SPOONACULAR_FOOD_DATA_SOURCE = "spoonacular"
CATALOG_SOURCE_STRATEGY_DEFAULT = "internal_catalog_with_optional_spoonacular_enrichment"
DIET_SOURCE_MAP = {
    "internal_catalog": DEFAULT_FOOD_DATA_SOURCE,
    "local_cache": CACHE_FOOD_DATA_SOURCE,
    "spoonacular": SPOONACULAR_FOOD_DATA_SOURCE,
    DEFAULT_FOOD_DATA_SOURCE: DEFAULT_FOOD_DATA_SOURCE,
    CACHE_FOOD_DATA_SOURCE: CACHE_FOOD_DATA_SOURCE,
    SPOONACULAR_FOOD_DATA_SOURCE: SPOONACULAR_FOOD_DATA_SOURCE,
}
EXACT_SOLVER_TOLERANCE = 1e-6
FOOD_VALUE_PRECISION = 2
FOOD_OMIT_THRESHOLD = {
    "g": 0.5,
    "ml": 1.0,
    "unidad": 0.05,
}
SOFT_ROLE_MINIMUMS = {
    "protein": {"g": 55.0, "ml": 125.0, "unidad": 0.5},
    "carb": {"g": 15.0, "ml": 50.0, "unidad": 0.2},
    "fat": {"g": 3.0, "ml": 3.0, "unidad": 0.1},
}
ROLE_DISPLAY_ORDER = {
    "protein": 0,
    "carb": 1,
    "fruit": 2,
    "vegetable": 3,
    "dairy": 4,
    "fat": 5,
}
ROLE_LABELS = {
    "protein": "proteina",
    "carb": "carbohidrato",
    "fat": "grasa",
}
ROLE_FALLBACK_CODE_POOLS = {
    "protein": [
        "chicken_breast",
        "turkey_breast",
        "tuna",
        "egg_whites",
        "greek_yogurt",
        "eggs",
    ],
    "carb": [
        "rice",
        "potato",
        "pasta",
        "whole_wheat_bread",
        "banana",
        "oats",
    ],
    "fat": ["olive_oil", "avocado", "mixed_nuts"],
}
CORE_MACRO_KEYS = ("protein_grams", "fat_grams", "carb_grams")
MACRO_CALORIE_FACTORS = {
    "protein_grams": 4.0,
    "fat_grams": 9.0,
    "carb_grams": 4.0,
}
CANDIDATE_INDEX_WEIGHT = 0.08
# Bonus must exceed CANDIDATE_INDEX_WEIGHT * typical_list_depth so that a preferred food
# always wins against a non-preferred one regardless of its position in the candidate list.
PREFERRED_FOOD_BONUS_BY_ROLE = {
    "protein": 1.20,
    "carb": 0.95,
    "fat": 0.45,
    "fruit": 0.55,
    "vegetable": 0.45,
    "dairy": 0.70,
}
REPEAT_PENALTY_BY_ROLE = {
    "protein": 0.85,
    "carb": 0.72,
    "fat": 0.28,
    "fruit": 0.18,
    "vegetable": 0.12,
    "dairy": 0.24,
}
REPEAT_ESCALATION_BY_ROLE = {
    "protein": 0.75,
    "carb": 0.55,
    "fat": 0.18,
    "fruit": 0.12,
    "vegetable": 0.08,
    "dairy": 0.18,
}
REPEATED_MAIN_PAIR_PENALTY = 0.5
# Penalización suave por repetir el mismo alimento a lo largo de la semana.
# Mucho más baja que la diaria para desincentivar sin prohibir.
WEEKLY_REPEAT_PENALTY_BY_ROLE = {
    "protein": 0.12,
    "carb": 0.08,
    "fat": 0.0,      # Las grasas (aceite, aguacate) se repiten siempre y está bien
    "fruit": 0.04,
    "vegetable": 0.02,
    "dairy": 0.06,
}
WEEKLY_DIVERSITY_WINDOW_DAYS = 6  # Días hacia atrás para calcular la ventana semanal
DEFAULT_PROTEIN_ROLE_DAILY_MAX_USAGE = 1
PROTEIN_ROLE_DAILY_MAX_USAGE_BY_CODE = {
    "egg_whites": 1,
    "eggs": 1,
    "greek_yogurt": 2,
}
SWEET_BREAKFAST_CARB_TOKENS = (
    "avena",
    "oats",
    "muesli",
    "granola",
    "cereal",
    "cornflakes",
    "flakes",
    "porridge",
)
SAVORY_STARCH_TOKENS = (
    "arroz",
    "rice",
    "pasta",
    "patata",
    "potato",
    "quinoa",
    "couscous",
    "boniato",
    "batata",
    "lentil",
    "lenteja",
    "garbanzo",
    "chickpea",
    "judia",
    "bean",
    "tortilla",
)
SAVORY_PROTEIN_TOKENS = (
    "chicken",
    "pollo",
    "turkey",
    "pavo",
    "tuna",
    "atun",
    "beef",
    "ternera",
    "pork",
    "cerdo",
    "salmon",
    "merluza",
    "bacalao",
    "fish",
    "gamba",
    "shrimp",
    "prawn",
    "marisco",
    "sepia",
    "sausage",
    "salchicha",
)
BREAKFAST_PROTEIN_TOKENS = (
    "egg",
    "huevo",
    "claras",
    "yogur",
    "yogurt",
    "cottage",
    "skyr",
    "quark",
)
BREAKFAST_ONLY_DAIRY_TOKENS = (
    "yogur",
    "yogurt",
    "cottage",
    "skyr",
    "quark",
    "leche",
    "milk",
)
BREAKFAST_FAT_TOKENS = (
    "almendra",
    "almond",
    "nueces",
    "walnut",
    "peanut",
    "cacahuete",
    "chia",
    "lino",
    "flax",
    "seed",
)
COOKING_FAT_TOKENS = ("aceite", "olive oil", "oil")
BREAKFAST_BREAD_TOKENS = ("pan", "bread", "toast", "tostada")


def normalize_diet_food_source(value: str | None) -> str:
    return DIET_SOURCE_MAP.get(str(value or "").strip(), DEFAULT_FOOD_DATA_SOURCE)


def _dedupe_foods_by_code(foods: list[dict]) -> list[dict]:
    deduped_foods: list[dict] = []
    seen_codes: set[str] = set()

    for food in foods:
        food_code = str(food["code"])
        if food_code in seen_codes:
            continue

        seen_codes.add(food_code)
        deduped_foods.append(food)

    return deduped_foods


def _build_preference_filtered_role_codes(
    *,
    role: str,
    candidate_codes: list[str],
    food_lookup: dict[str, dict],
    preference_profile: dict,
) -> list[str]:
    candidate_codes_set = set(candidate_codes)
    compatible_candidate_foods = [food_lookup[code] for code in candidate_codes if code in food_lookup]
    compatible_candidate_foods.extend(
        food_lookup[code]
        for code in ROLE_FALLBACK_CODE_POOLS[role]
        if code in food_lookup and code not in candidate_codes_set
    )
    filtered_result = apply_user_food_preferences(compatible_candidate_foods, preference_profile)
    # Preferred foods go to the front so the scoring naturally selects them first.
    compatible_foods = prioritize_preferred_foods(
        _dedupe_foods_by_code(filtered_result["foods"]),
        preference_profile,
    )

    if compatible_foods:
        return [food["code"] for food in compatible_foods]

    blocked_food_labels = sorted(
        {
            blocked_food["name"]
            for blocked_food in filtered_result["blocked_foods"]
        }
    )
    detail = (
        f"No hay suficientes alimentos compatibles para cubrir el rol de {ROLE_LABELS[role]} "
        "con tus preferencias y restricciones actuales."
    )
    if blocked_food_labels:
        detail += " Alimentos descartados: " + ", ".join(blocked_food_labels[:6]) + "."

    detail += " Revisa alimentos no deseados, restricciones dieteticas o alergias."
    raise FoodPreferenceConflictError(detail)


def _build_preference_filtered_support_options(
    *,
    support_options: list[list[dict]],
    food_lookup: dict[str, dict],
    preference_profile: dict,
) -> list[list[dict]]:
    prioritized_options: list[tuple[int, list[dict]]] = []
    seen_keys: set[tuple[str, ...]] = set()

    for support_option in support_options:
        support_foods = [
            food_lookup[support_food["food_code"]]
            for support_food in support_option
            if support_food["food_code"] in food_lookup
        ]
        filtered_support_result = apply_user_food_preferences(support_foods, preference_profile)
        allowed_codes = {food["code"] for food in filtered_support_result["foods"]}
        filtered_support_option = [
            support_food
            for support_food in support_option
            if support_food["food_code"] in allowed_codes
        ]
        option_key = tuple(sorted(support_food["food_code"] for support_food in filtered_support_option))
        if option_key in seen_keys:
            continue

        seen_keys.add(option_key)
        prioritized_options.append((filtered_support_result["preferred_matches"], filtered_support_option))

    if not prioritized_options:
        return [[]]

    # Options with preferred food matches first, then prefer options with more foods.
    prioritized_options.sort(key=lambda item: (-item[0], -len(item[1])))
    normalized_options = [support_option for _, support_option in prioritized_options]
    if [] not in normalized_options:
        normalized_options.append([])

    return normalized_options


def apply_user_food_preferences_to_meal_candidates(
    *,
    candidate_codes: dict[str, list[str]],
    support_options: list[list[dict]],
    food_lookup: dict[str, dict],
    preference_profile: dict,
) -> tuple[dict[str, list[str]], list[list[dict]]]:
    if not preference_profile.get("has_preferences"):
        return candidate_codes, support_options

    filtered_candidate_codes = {
        role: _build_preference_filtered_role_codes(
            role=role,
            candidate_codes=role_codes,
            food_lookup=food_lookup,
            preference_profile=preference_profile,
        )
        for role, role_codes in candidate_codes.items()
    }
    filtered_support_options = _build_preference_filtered_support_options(
        support_options=support_options,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
    )
    return filtered_candidate_codes, filtered_support_options


def apply_meal_candidate_constraints(
    candidate_codes: dict[str, list[str]],
    *,
    food_lookup: dict[str, dict],
    forced_role_codes: dict[str, str] | None = None,
    excluded_food_codes: set[str] | None = None,
) -> dict[str, list[str]]:
    excluded_codes = set(excluded_food_codes or set())
    constrained_candidate_codes: dict[str, list[str]] = {}

    for role, role_codes in candidate_codes.items():
        filtered_codes = [
            code
            for code in role_codes
            if code in food_lookup and code not in excluded_codes
        ]
        forced_code = forced_role_codes.get(role) if forced_role_codes else None
        if forced_code:
            if forced_code not in food_lookup:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Forced food code '{forced_code}' is not available in the current food lookup",
                )

            filtered_codes = [forced_code] + [
                code for code in filtered_codes if code != forced_code
            ]

        constrained_candidate_codes[role] = filtered_codes

    return constrained_candidate_codes


def apply_support_option_constraints(
    support_options: list[list[dict]],
    *,
    food_lookup: dict[str, dict],
    forced_support_foods: list[dict] | None = None,
    excluded_food_codes: set[str] | None = None,
) -> list[list[dict]]:
    if forced_support_foods is not None:
        if not forced_support_foods:
            return [[]]

        for support_food in forced_support_foods:
            if support_food["food_code"] not in food_lookup:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Support food '{support_food['food_code']}' is not available in the current food lookup",
                )

        return [[
            {
                "role": support_food["role"],
                "food_code": support_food["food_code"],
                "quantity": float(support_food["quantity"]),
            }
            for support_food in forced_support_foods
        ]]

    excluded_codes = set(excluded_food_codes or set())
    filtered_support_options: list[list[dict]] = []

    for support_option in support_options:
        if any(
            support_food["food_code"] not in food_lookup or support_food["food_code"] in excluded_codes
            for support_food in support_option
        ):
            continue

        filtered_support_options.append([
            {
                "role": support_food["role"],
                "food_code": support_food["food_code"],
                "quantity": float(support_food["quantity"]),
            }
            for support_food in support_option
        ])

    if [] not in filtered_support_options:
        filtered_support_options.insert(0, [])

    return filtered_support_options or [[]]


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
    if meal_index == 0 or (meals_count >= 5 and meal_index == 1):
        return "early"
    if meal_index == meals_count - 1:
        return "late"
    return "main"


def rotate_codes(codes: list[str], rotation_seed: int) -> list[str]:
    if not codes:
        return []

    shift = rotation_seed % len(codes)
    return codes[shift:] + codes[:shift]


def get_food_text_signature(food: dict[str, Any]) -> str:
    aliases = " ".join(str(alias) for alias in food.get("aliases", []))
    return normalize_food_name(" ".join(
        value
        for value in (
            str(food.get("code", "")).replace("_", " "),
            str(food.get("name", "")),
            str(food.get("display_name", "")),
            str(food.get("original_name", "")),
            str(food.get("category", "")),
            aliases,
        )
        if value
    ))


def _food_has_any_token(food: dict[str, Any], tokens: tuple[str, ...]) -> bool:
    food_text = get_food_text_signature(food)
    return any(token in food_text for token in tokens)


def get_allowed_meal_slots_for_food(food: dict[str, Any]) -> set[str]:
    slots = {
        str(slot).strip().lower()
        for slot in food.get("suitable_meals", [])
        if str(slot).strip()
    }

    if not slots:
        functional_group = derive_functional_group(food)
        if functional_group in {"protein", "carb", "fat", "vegetable"}:
            slots.update({"main", "late"})
        elif functional_group in {"fruit", "dairy"}:
            slots.update({"early", "snack"})

    if "main" in slots:
        slots.add("late")
    if "snack" in slots and "early" not in slots and "main" not in slots and "late" not in slots:
        slots.add("early")

    return slots


def is_sweet_breakfast_carb(food: dict[str, Any]) -> bool:
    category = str(food.get("category") or "").strip().lower()
    if category in {"frutas", "cereales"}:
        return True

    return _food_has_any_token(food, SWEET_BREAKFAST_CARB_TOKENS)


def is_savory_starch(food: dict[str, Any]) -> bool:
    if _food_has_any_token(food, SAVORY_STARCH_TOKENS):
        return True

    functional_group = derive_functional_group(food)
    category = str(food.get("category") or "").strip().lower()
    if functional_group != "carb" or category == "cereales":
        return False
    if _food_has_any_token(food, BREAKFAST_BREAD_TOKENS):
        return False

    allowed_slots = get_allowed_meal_slots_for_food(food)
    return "main" in allowed_slots or "late" in allowed_slots


def is_breakfast_only_protein(food: dict[str, Any]) -> bool:
    category = str(food.get("category") or "").strip().lower()
    if category == "lacteos":
        return True

    return _food_has_any_token(food, BREAKFAST_ONLY_DAIRY_TOKENS)


def is_savory_protein(food: dict[str, Any]) -> bool:
    if _food_has_any_token(food, SAVORY_PROTEIN_TOKENS):
        return True

    if derive_functional_group(food) != "protein":
        return False
    if is_breakfast_only_protein(food):
        return False
    if _food_has_any_token(food, BREAKFAST_PROTEIN_TOKENS):
        return False

    return True


def is_breakfast_fat(food: dict[str, Any]) -> bool:
    return _food_has_any_token(food, BREAKFAST_FAT_TOKENS)


def is_cooking_fat(food: dict[str, Any]) -> bool:
    return str(food.get("code") or "").strip().lower() == "olive_oil" or _food_has_any_token(food, COOKING_FAT_TOKENS)


def get_candidate_role_for_food(food: dict[str, Any], meal_slot: str) -> str | None:
    functional_group = derive_functional_group(food)
    if functional_group == "protein":
        return "protein"
    if functional_group == "carb":
        return "carb"
    if functional_group == "fat":
        return "fat"
    if meal_slot == "early" and functional_group == "fruit":
        return "carb"

    return None


def is_food_allowed_for_role_and_slot(food: dict[str, Any], *, role: str, meal_slot: str) -> bool:
    if meal_slot not in get_allowed_meal_slots_for_food(food):
        return False

    functional_group = derive_functional_group(food)
    if role == "protein":
        if functional_group != "protein":
            return False

        if meal_slot == "early":
            return not is_savory_protein(food)

        return not is_breakfast_only_protein(food)

    if role == "carb":
        if meal_slot == "early":
            return functional_group in {"carb", "fruit"} and not is_savory_starch(food)

        return functional_group == "carb" and not is_sweet_breakfast_carb(food)

    if role == "fat":
        if functional_group != "fat":
            return False

        if meal_slot == "early":
            return not is_cooking_fat(food)

        return not is_breakfast_fat(food)

    return False


def get_food_slot_affinity_score(food: dict[str, Any], meal_slot: str) -> float:
    slot_scores = predict_meal_slot_scores(food)
    score = float(slot_scores.get(meal_slot, 0.0))
    if meal_slot == "late":
        score = max(score, float(slot_scores.get("main", 0.0)) * 0.9)

    allowed_slots = get_allowed_meal_slots_for_food(food)
    if meal_slot in allowed_slots:
        score += 1.0
    elif meal_slot == "late" and "main" in allowed_slots:
        score += 0.75

    if meal_slot == "early":
        if is_sweet_breakfast_carb(food) or is_breakfast_only_protein(food):
            score += 0.12
        if is_breakfast_fat(food):
            score += 0.08
    else:
        if is_savory_starch(food) or is_savory_protein(food) or is_cooking_fat(food):
            score += 0.14
        if derive_functional_group(food) == "carb" and _food_has_any_token(food, BREAKFAST_BREAD_TOKENS):
            score -= 0.05

    return score


def sort_codes_by_slot_affinity(
    codes: list[str],
    *,
    meal_slot: str,
    food_lookup: dict[str, dict],
) -> list[str]:
    return sorted(
        codes,
        key=lambda code: -get_food_slot_affinity_score(food_lookup[code], meal_slot),
    )


def apply_daily_usage_candidate_limits(
    candidate_codes: dict[str, list[str]],
    *,
    daily_food_usage: dict | None,
) -> dict[str, list[str]]:
    if not daily_food_usage:
        return candidate_codes

    protein_role_counts = daily_food_usage.get("role_counts", {}).get("protein", {})
    limited_candidate_codes: dict[str, list[str]] = {}

    for role, codes in candidate_codes.items():
        if role != "protein":
            limited_candidate_codes[role] = codes
            continue

        filtered_codes = [
            code
            for code in codes
            if int(protein_role_counts.get(code, 0)) < PROTEIN_ROLE_DAILY_MAX_USAGE_BY_CODE.get(
                code,
                DEFAULT_PROTEIN_ROLE_DAILY_MAX_USAGE,
            )
        ]
        limited_candidate_codes[role] = filtered_codes or codes

    return limited_candidate_codes


def is_role_combination_coherent(role_foods: dict[str, dict], *, meal_slot: str) -> bool:
    protein_food = role_foods["protein"]
    carb_food = role_foods["carb"]
    fat_food = role_foods["fat"]

    if meal_slot == "early":
        return not (
            is_savory_protein(protein_food)
            or is_savory_starch(carb_food)
            or is_cooking_fat(fat_food)
        )

    if is_sweet_breakfast_carb(carb_food):
        return False
    if is_breakfast_only_protein(protein_food):
        return False
    if is_breakfast_fat(fat_food) and is_savory_protein(protein_food):
        return False

    return True


def create_daily_food_usage_tracker() -> dict[str, dict]:
    return {
        "food_counts": {},
        "role_counts": {},
        "main_pair_counts": {},
    }


def build_weekly_food_usage(database, user_id: str) -> dict[str, int]:
    """Construye un contador de food_code → nº de apariciones en los últimos WEEKLY_DIVERSITY_WINDOW_DAYS días.

    Consulta el historial de dietas del usuario para penalizar suavemente
    los alimentos que ya han aparecido mucho durante la semana.
    Devuelve un dict vacío si no hay historial o si la consulta falla.
    """
    try:
        since = datetime.now(UTC) - timedelta(days=WEEKLY_DIVERSITY_WINDOW_DAYS)
        cursor = database.diets.find(
            {"user_id": ObjectId(user_id), "created_at": {"$gte": since}},
            {"meals.foods.food_code": 1, "_id": 0},
        )
        weekly_counts: dict[str, int] = {}
        for diet in cursor:
            for meal in diet.get("meals", []):
                for food in meal.get("foods", []):
                    code = food.get("food_code")
                    if code:
                        weekly_counts[code] = weekly_counts.get(code, 0) + 1
        return weekly_counts
    except Exception:
        return {}


def apply_weekly_repeat_penalty(food_code: str, *, role: str, weekly_food_usage: dict | None) -> float:
    """Penalización suave (semanal) por repetir el mismo alimento.

    Se acumula por encima de la penalización diaria para fomentar variedad
    a lo largo de la semana sin forzar cambios rígidos.
    """
    if not weekly_food_usage:
        return 0.0
    weekly_count = int(weekly_food_usage.get(food_code, 0))
    if weekly_count <= 0:
        return 0.0
    return WEEKLY_REPEAT_PENALTY_BY_ROLE.get(role, 0.0) * weekly_count


def track_food_usage_across_day(daily_food_usage: dict[str, dict], meal_plan: dict) -> None:
    selected_role_codes = meal_plan.get("selected_role_codes", {})
    protein_code = selected_role_codes.get("protein")
    carb_code = selected_role_codes.get("carb")

    def add_usage(food_code: str | None, role: str) -> None:
        if not food_code:
            return

        daily_food_usage["food_counts"][food_code] = daily_food_usage["food_counts"].get(food_code, 0) + 1
        role_counts = daily_food_usage["role_counts"].setdefault(role, {})
        role_counts[food_code] = role_counts.get(food_code, 0) + 1

    for role, food_code in selected_role_codes.items():
        add_usage(food_code, role)

    for support_food in meal_plan.get("support_food_specs", []):
        add_usage(support_food.get("food_code"), support_food.get("role", "support"))

    if protein_code and carb_code:
        pair_key = f"{protein_code}::{carb_code}"
        daily_food_usage["main_pair_counts"][pair_key] = daily_food_usage["main_pair_counts"].get(pair_key, 0) + 1


def get_food_usage_summary_from_meals(meals: list[dict]) -> dict[str, int]:
    food_usage_summary: dict[str, int] = {}

    for meal in meals:
        for food in meal.get("foods", []):
            food_name = str(food.get("name") or "").strip()
            if not food_name:
                continue

            food_usage_summary[food_name] = food_usage_summary.get(food_name, 0) + 1

    return dict(sorted(food_usage_summary.items()))


def apply_preference_priority(
    food: dict,
    *,
    role: str,
    preference_profile: dict | None,
    daily_food_usage: dict | None,
) -> float:
    if not preference_profile or not preference_profile.get("normalized_preferred_foods"):
        return 0.0

    preferred_matches = count_food_preference_matches(food, preference_profile)
    if preferred_matches <= 0:
        return 0.0

    usage_count = 0
    if daily_food_usage:
        usage_count = int(daily_food_usage.get("food_counts", {}).get(food["code"], 0))

    usage_modifier = max(0.35, 1.0 - (0.45 * usage_count))
    return PREFERRED_FOOD_BONUS_BY_ROLE.get(role, 0.16) * preferred_matches * usage_modifier


def apply_repeat_penalty(
    food_code: str,
    *,
    role: str,
    daily_food_usage: dict | None,
) -> float:
    if not daily_food_usage:
        return 0.0

    usage_count = int(daily_food_usage.get("food_counts", {}).get(food_code, 0))
    if usage_count <= 0:
        return 0.0

    base_penalty = REPEAT_PENALTY_BY_ROLE.get(role, 0.15) * usage_count
    escalation_penalty = REPEAT_ESCALATION_BY_ROLE.get(role, 0.08) * max(0, usage_count - 1)
    return base_penalty + escalation_penalty


def apply_main_pair_repeat_penalty(
    role_foods: dict[str, dict],
    *,
    daily_food_usage: dict | None,
) -> float:
    if not daily_food_usage:
        return 0.0

    protein_code = role_foods["protein"]["code"]
    carb_code = role_foods["carb"]["code"]
    pair_key = f"{protein_code}::{carb_code}"
    pair_count = int(daily_food_usage.get("main_pair_counts", {}).get(pair_key, 0))
    return pair_count * REPEATED_MAIN_PAIR_PENALTY


def get_role_candidate_codes(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict] | None = None,
) -> dict[str, list[str]]:
    meal_slot = get_meal_slot(meal_index, meals_count)
    rotation_seed = meal_index + meals_count

    protein_codes = []
    carb_codes = []
    fat_codes = []

    # Primero filtramos por reglas duras del slot y luego ordenamos por afinidad del modelo.
    if food_lookup:
        for code, f_data in food_lookup.items():
            candidate_role = get_candidate_role_for_food(f_data, meal_slot)
            if not candidate_role or not is_food_allowed_for_role_and_slot(f_data, role=candidate_role, meal_slot=meal_slot):
                continue

            if candidate_role == "protein" and code not in protein_codes:
                protein_codes.append(code)
            elif candidate_role == "carb" and code not in carb_codes:
                carb_codes.append(code)
            elif candidate_role == "fat" and code not in fat_codes:
                fat_codes.append(code)

    # Fallbacks seguros en caso de que la búsqueda dinámica encuentre muy pocas opciones.
    if len(protein_codes) < 2:
        if meal_slot == "early":
            protein_codes.extend(["greek_yogurt", "eggs", "egg_whites"])
        else:
            protein_codes.extend(["chicken_breast", "turkey_breast", "tuna", "eggs", "egg_whites"])

    if len(carb_codes) < 2:
        if meal_slot == "early":
            carb_codes.extend(["oats", "whole_wheat_bread", "banana"])
        else:
            carb_codes.extend(["rice", "pasta", "potato", "whole_wheat_bread"])

    if len(fat_codes) < 2:
        if meal_slot == "early":
            fat_codes.extend(["avocado", "mixed_nuts"])
        else:
            fat_codes.extend(["olive_oil", "avocado"])

    protein_codes = [
        code
        for code in dict.fromkeys(protein_codes)
        if not food_lookup or (
            code in food_lookup
            and is_food_allowed_for_role_and_slot(food_lookup[code], role="protein", meal_slot=meal_slot)
        )
    ]
    carb_codes = [
        code
        for code in dict.fromkeys(carb_codes)
        if not food_lookup or (
            code in food_lookup
            and is_food_allowed_for_role_and_slot(food_lookup[code], role="carb", meal_slot=meal_slot)
        )
    ]
    fat_codes = [
        code
        for code in dict.fromkeys(fat_codes)
        if not food_lookup or (
            code in food_lookup
            and is_food_allowed_for_role_and_slot(food_lookup[code], role="fat", meal_slot=meal_slot)
        )
    ]

    if food_lookup:
        protein_codes = sort_codes_by_slot_affinity(
            rotate_codes(protein_codes, rotation_seed),
            meal_slot=meal_slot,
            food_lookup=food_lookup,
        )
        carb_codes = sort_codes_by_slot_affinity(
            rotate_codes(carb_codes, rotation_seed + 1),
            meal_slot=meal_slot,
            food_lookup=food_lookup,
        )
        fat_codes = sort_codes_by_slot_affinity(
            rotate_codes(fat_codes, rotation_seed + 2),
            meal_slot=meal_slot,
            food_lookup=food_lookup,
        )
    else:
        protein_codes = rotate_codes(protein_codes, rotation_seed)
        carb_codes = rotate_codes(carb_codes, rotation_seed + 1)
        fat_codes = rotate_codes(fat_codes, rotation_seed + 2)

    return {
        "protein": protein_codes,
        "carb": carb_codes,
        "fat": fat_codes,
    }


def get_support_option_specs(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
) -> list[list[dict]]:
    meal_slot = get_meal_slot(meal_index, meals_count)
    support_options: list[list[dict]] = [[]]

    if meal_slot != "early" and meal.target_calories >= 320 and meal.target_carb_grams >= 15:
        support_options.append(
            [
                {
                    "role": "vegetable",
                    "food_code": "mixed_vegetables",
                    "quantity": 80.0 if meal.target_calories < 520 else 120.0,
                }
            ]
        )

    if (meal_slot == "early" or training_focus) and meal.target_carb_grams >= 40:
        support_options.append(
            [
                {
                    "role": "fruit",
                    "food_code": "banana",
                    "quantity": 0.5 if meal.target_carb_grams < 80 else 1.0,
                }
            ]
        )

    if meal_slot == "early" and meal.target_calories <= 260 and meal.target_protein_grams <= 26:
        support_options.append(
            [
                {
                    "role": "dairy",
                    "food_code": "greek_yogurt",
                    "quantity": 1.0,
                }
            ]
        )

    return support_options


def get_food_macro_density(food: dict) -> dict[str, float]:
    reference_amount = float(food["reference_amount"])
    return {
        macro_key: float(food[macro_key]) / reference_amount
        for macro_key in CORE_MACRO_KEYS
    }


def build_precise_food_values(food: dict, quantity: float) -> dict[str, float]:
    scale = quantity / float(food["reference_amount"])
    grams = float(food["grams_per_reference"]) * scale
    protein_grams = float(food["protein_grams"]) * scale
    fat_grams = float(food["fat_grams"]) * scale
    carb_grams = float(food["carb_grams"]) * scale

    return {
        "quantity": quantity,
        "grams": grams,
        "protein_grams": protein_grams,
        "fat_grams": fat_grams,
        "carb_grams": carb_grams,
        "calories": calculate_macro_calories(protein_grams, fat_grams, carb_grams),
    }


def build_food_portion(food: dict, quantity: float) -> dict:
    precise_values = build_precise_food_values(food, quantity)
    food_source = normalize_diet_food_source(food.get("source"))
    origin_source = normalize_diet_food_source(food.get("origin_source", food.get("source")))
    return {
        "food_code": food["code"],
        "source": food_source,
        "origin_source": origin_source,
        "spoonacular_id": food.get("spoonacular_id"),
        "name": food["name"],
        "category": food["category"],
        "quantity": round_food_value(precise_values["quantity"]),
        "unit": food["reference_unit"],
        "grams": round_food_value(precise_values["grams"]),
        "calories": round_food_value(precise_values["calories"]),
        "protein_grams": round_food_value(precise_values["protein_grams"]),
        "fat_grams": round_food_value(precise_values["fat_grams"]),
        "carb_grams": round_food_value(precise_values["carb_grams"]),
    }


def calculate_support_totals(
    support_food_specs: list[dict],
    food_lookup: dict[str, dict],
) -> dict[str, float]:
    totals = {
        "calories": 0.0,
        "protein_grams": 0.0,
        "fat_grams": 0.0,
        "carb_grams": 0.0,
    }
    for support_food in support_food_specs:
        precise_values = build_precise_food_values(
            food_lookup[support_food["food_code"]],
            float(support_food["quantity"]),
        )
        for field_name in totals:
            totals[field_name] += precise_values[field_name]

    return totals


def solve_linear_system(matrix: list[list[float]], values: list[float]) -> list[float] | None:
    size = len(values)
    augmented = [row[:] + [values[index]] for index, row in enumerate(matrix)]

    for column in range(size):
        pivot_row = max(
            range(column, size),
            key=lambda row_index: abs(augmented[row_index][column]),
        )
        if abs(augmented[pivot_row][column]) <= EXACT_SOLVER_TOLERANCE:
            return None

        if pivot_row != column:
            augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]

        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]

        for row_index in range(size):
            if row_index == column:
                continue

            factor = augmented[row_index][column]
            augmented[row_index] = [
                current_value - (factor * pivot_component)
                for current_value, pivot_component in zip(augmented[row_index], augmented[column], strict=True)
            ]

    return [augmented[row_index][-1] for row_index in range(size)]


def get_soft_role_minimum(food: dict, role: str) -> float:
    unit = food["reference_unit"]
    return SOFT_ROLE_MINIMUMS.get(role, {}).get(unit, 0.0)


def get_food_visibility_threshold(food: dict) -> float:
    return FOOD_OMIT_THRESHOLD.get(food["reference_unit"], 0.0)


def build_solution_score(
    *,
    role_foods: dict[str, dict],
    role_quantities: dict[str, float],
    support_foods: list[dict],
    candidate_indexes: dict[str, int],
    training_focus: bool,
    meal_slot: str,
    preference_profile: dict | None = None,
    daily_food_usage: dict | None = None,
    weekly_food_usage: dict | None = None,
) -> float:
    score = 0.0

    for role, food in role_foods.items():
        quantity = role_quantities[role]
        preferred_quantity = float(food["default_quantity"])
        soft_minimum = get_soft_role_minimum(food, role)

        score += candidate_indexes[role] * CANDIDATE_INDEX_WEIGHT
        score += abs(quantity - preferred_quantity) / max(preferred_quantity, 1.0) * 0.3
        score -= apply_preference_priority(
            food,
            role=role,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
        )
        score += apply_repeat_penalty(
            food["code"],
            role=role,
            daily_food_usage=daily_food_usage,
        )
        score += apply_weekly_repeat_penalty(
            food["code"],
            role=role,
            weekly_food_usage=weekly_food_usage,
        )

        if quantity < soft_minimum:
            score += ((soft_minimum - quantity) / max(soft_minimum, 1.0)) * 2.2

        if quantity > float(food["max_quantity"]) * 0.9:
            score += ((quantity - (float(food["max_quantity"]) * 0.9)) / max(float(food["max_quantity"]), 1.0)) * 6.0

        if role == "fat" and food["code"] == "olive_oil":
            score -= 0.15

        if role == "carb" and training_focus and food["code"] in {"rice", "pasta", "oats"}:
            score -= 0.2

        if role == "protein" and meal_slot == "early" and food["code"] in {"egg_whites", "greek_yogurt"}:
            score -= 0.1

    score += apply_main_pair_repeat_penalty(
        role_foods,
        daily_food_usage=daily_food_usage,
    )

    if support_foods:
        score += 0.15 * len(support_foods)

        if meal_slot != "early" and support_foods[0]["role"] == "vegetable":
            score -= 0.05
        if training_focus and support_foods[0]["role"] == "fruit":
            score -= 0.05

        for support_food in support_foods:
            score -= apply_preference_priority(
                support_food,
                role=support_food["role"],
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
            )
            score += apply_repeat_penalty(
                support_food["code"],
                role=support_food["role"],
                daily_food_usage=daily_food_usage,
            )

    return score


def build_exact_meal_solution(
    *,
    meal: DietMeal,
    role_foods: dict[str, dict],
    support_food_specs: list[dict],
    candidate_indexes: dict[str, int],
    food_lookup: dict[str, dict],
    training_focus: bool,
    meal_slot: str,
    preference_profile: dict | None = None,
    daily_food_usage: dict | None = None,
    weekly_food_usage: dict | None = None,
) -> dict | None:
    all_codes = [
        role_foods["protein"]["code"],
        role_foods["carb"]["code"],
        role_foods["fat"]["code"],
        *[support_food["food_code"] for support_food in support_food_specs],
    ]
    if len(set(all_codes)) != len(all_codes):
        return None
    if not is_role_combination_coherent(role_foods, meal_slot=meal_slot):
        return None

    support_totals = calculate_support_totals(support_food_specs, food_lookup)
    remaining_targets = {
        "protein_grams": meal.target_protein_grams - support_totals["protein_grams"],
        "fat_grams": meal.target_fat_grams - support_totals["fat_grams"],
        "carb_grams": meal.target_carb_grams - support_totals["carb_grams"],
    }

    if any(target_value < -EXACT_SOLVER_TOLERANCE for target_value in remaining_targets.values()):
        return None

    matrix = [
        [
            get_food_macro_density(role_foods["protein"])[macro_key],
            get_food_macro_density(role_foods["carb"])[macro_key],
            get_food_macro_density(role_foods["fat"])[macro_key],
        ]
        for macro_key in CORE_MACRO_KEYS
    ]
    target_vector = [remaining_targets[macro_key] for macro_key in CORE_MACRO_KEYS]
    solved_quantities = solve_linear_system(matrix, target_vector)
    if solved_quantities is None:
        return None

    role_quantities = {
        "protein": max(0.0, solved_quantities[0]),
        "carb": max(0.0, solved_quantities[1]),
        "fat": max(0.0, solved_quantities[2]),
    }

    for role, quantity in role_quantities.items():
        if quantity - float(role_foods[role]["max_quantity"]) > EXACT_SOLVER_TOLERANCE:
            return None

        visibility_threshold = get_food_visibility_threshold(role_foods[role])
        if role == "protein" and quantity < visibility_threshold:
            return None

    foods: list[dict] = []
    for role, food in role_foods.items():
        quantity = role_quantities[role]
        if quantity >= get_food_visibility_threshold(food):
            foods.append(
                {
                    "role": role,
                    **build_food_portion(food, quantity),
                }
            )

    for support_food in support_food_specs:
        foods.append(
            {
                "role": support_food["role"],
                **build_food_portion(
                    food_lookup[support_food["food_code"]],
                    float(support_food["quantity"]),
                ),
            }
        )

    foods.sort(key=lambda food: (ROLE_DISPLAY_ORDER.get(food["role"], 99), food["name"]))

    exact_actuals = {
        "actual_calories": round_diet_value(calculate_macro_calories(
            meal.target_protein_grams,
            meal.target_fat_grams,
            meal.target_carb_grams,
        )),
        "actual_protein_grams": round_diet_value(meal.target_protein_grams),
        "actual_fat_grams": round_diet_value(meal.target_fat_grams),
        "actual_carb_grams": round_diet_value(meal.target_carb_grams),
        "calorie_difference": 0.0,
        "protein_difference": 0.0,
        "fat_difference": 0.0,
        "carb_difference": 0.0,
    }
    resolved_support_foods = [
        {
            **food_lookup[support_food["food_code"]],
            "role": support_food["role"],
        }
        for support_food in support_food_specs
    ]

    return {
        "foods": [{key: value for key, value in food.items() if key != "role"} for food in foods],
        "selected_role_codes": {role: food["code"] for role, food in role_foods.items()},
        "support_food_specs": [
            {
                "role": support_food["role"],
                "food_code": support_food["food_code"],
                "quantity": float(support_food["quantity"]),
            }
            for support_food in support_food_specs
        ],
        "score": build_solution_score(
            role_foods=role_foods,
            role_quantities=role_quantities,
            support_foods=resolved_support_foods,
            candidate_indexes=candidate_indexes,
            training_focus=training_focus,
            meal_slot=meal_slot,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            weekly_food_usage=weekly_food_usage,
        ),
        **exact_actuals,
    }


def find_exact_solution_for_meal(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict],
    preference_profile: dict | None = None,
    daily_food_usage: dict | None = None,
    weekly_food_usage: dict | None = None,
    forced_role_codes: dict[str, str] | None = None,
    forced_support_foods: list[dict] | None = None,
    excluded_food_codes: set[str] | None = None,
) -> dict:
    candidate_codes = get_role_candidate_codes(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )
    support_options = get_support_option_specs(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    if preference_profile and preference_profile.get("has_preferences"):
        candidate_codes, support_options = apply_user_food_preferences_to_meal_candidates(
            candidate_codes=candidate_codes,
            support_options=support_options,
            food_lookup=food_lookup,
            preference_profile=preference_profile,
        )
    candidate_codes = apply_daily_usage_candidate_limits(
        candidate_codes,
        daily_food_usage=daily_food_usage,
    )
    candidate_codes = apply_meal_candidate_constraints(
        candidate_codes,
        food_lookup=food_lookup,
        forced_role_codes=forced_role_codes,
        excluded_food_codes=excluded_food_codes,
    )
    support_options = apply_support_option_constraints(
        support_options,
        food_lookup=food_lookup,
        forced_support_foods=forced_support_foods,
        excluded_food_codes=excluded_food_codes,
    )
    meal_slot = get_meal_slot(meal_index, meals_count)

    best_solution: dict | None = None

    def evaluate_candidate_sets(role_codes: dict[str, list[str]], extra_support_options: list[list[dict]]) -> None:
        nonlocal best_solution

        for support_food_specs in extra_support_options:
            for protein_index, carb_index, fat_index in product(
                range(len(role_codes["protein"])),
                range(len(role_codes["carb"])),
                range(len(role_codes["fat"])),
            ):
                role_foods = {
                    "protein": food_lookup[role_codes["protein"][protein_index]],
                    "carb": food_lookup[role_codes["carb"][carb_index]],
                    "fat": food_lookup[role_codes["fat"][fat_index]],
                }
                candidate_indexes = {
                    "protein": protein_index,
                    "carb": carb_index,
                    "fat": fat_index,
                }
                candidate_solution = build_exact_meal_solution(
                    meal=meal,
                    role_foods=role_foods,
                    support_food_specs=support_food_specs,
                    candidate_indexes=candidate_indexes,
                    food_lookup=food_lookup,
                    training_focus=training_focus,
                    meal_slot=meal_slot,
                    preference_profile=preference_profile,
                    daily_food_usage=daily_food_usage,
                    weekly_food_usage=weekly_food_usage,
                )
                if not candidate_solution:
                    continue

                if best_solution is None or candidate_solution["score"] < best_solution["score"]:
                    best_solution = candidate_solution

    evaluate_candidate_sets(candidate_codes, support_options)
    if best_solution:
        return best_solution

    if preference_profile and preference_profile.get("has_preferences"):
        raise FoodPreferenceConflictError(
            "No hay suficientes combinaciones de alimentos compatibles para generar esta comida "
            "con tus preferencias actuales. Ajusta restricciones, alergias o alimentos no deseados."
        )

    fallback_role_codes = {
        "protein": ROLE_FALLBACK_CODE_POOLS["protein"],
        "carb": ROLE_FALLBACK_CODE_POOLS["carb"],
        "fat": ROLE_FALLBACK_CODE_POOLS["fat"],
    }
    fallback_role_codes = {
        role: [
            code
            for code in codes
            if code in food_lookup and is_food_allowed_for_role_and_slot(food_lookup[code], role=role, meal_slot=meal_slot)
        ]
        for role, codes in fallback_role_codes.items()
    }
    fallback_role_codes = apply_daily_usage_candidate_limits(
        fallback_role_codes,
        daily_food_usage=daily_food_usage,
    )
    fallback_role_codes = apply_meal_candidate_constraints(
        fallback_role_codes,
        food_lookup=food_lookup,
        forced_role_codes=forced_role_codes,
        excluded_food_codes=excluded_food_codes,
    )
    fallback_support_options = apply_support_option_constraints(
        [[]],
        food_lookup=food_lookup,
        forced_support_foods=forced_support_foods,
        excluded_food_codes=excluded_food_codes,
    )
    evaluate_candidate_sets(fallback_role_codes, fallback_support_options)

    if best_solution:
        return best_solution

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to fit meal exactly with current food catalog",
    )


def calculate_meal_totals_from_foods(foods: list[dict]) -> dict[str, float]:
    actual_protein_grams = round_diet_value(sum(float(food["protein_grams"]) for food in foods))
    actual_fat_grams = round_diet_value(sum(float(food["fat_grams"]) for food in foods))
    actual_carb_grams = round_diet_value(sum(float(food["carb_grams"]) for food in foods))
    actual_calories = round_diet_value(calculate_macro_calories(
        actual_protein_grams,
        actual_fat_grams,
        actual_carb_grams,
    ))

    return {
        "actual_calories": actual_calories,
        "actual_protein_grams": actual_protein_grams,
        "actual_fat_grams": actual_fat_grams,
        "actual_carb_grams": actual_carb_grams,
    }


def generate_food_based_meal(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    meal_plan: dict,
    food_lookup: dict[str, dict],
) -> dict:
    meal_slot = get_meal_slot(meal_index, meals_count)
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


def generate_food_based_diet(
    database,
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    preference_profile = build_user_food_preferences_profile(user)
    meal_distribution, focus_indexes = generate_meal_distribution_targets(
        user=user,
        meals_count=meals_count,
        custom_percentages=custom_percentages,
        training_time_of_day=training_time_of_day,
    )
    internal_food_lookup = get_internal_food_lookup()
    
    from app.schemas.food import serialize_food_catalog_item
    from copy import deepcopy
    full_food_lookup = deepcopy(internal_food_lookup)
    local_foods_cursor = database.foods_catalog.find({"suitable_meals": {"$exists": True, "$not": {"$size": 0}}})
    for doc in local_foods_cursor:
        serialized_dict = serialize_food_catalog_item(doc).model_dump()
        full_food_lookup[serialized_dict["code"]] = serialized_dict
        
    daily_food_usage = create_daily_food_usage_tracker()
    weekly_food_usage = build_weekly_food_usage(database, user.id)
    planned_meals: list[dict] = []
    for meal_index, meal in enumerate(meal_distribution["meals"]):
        planned_meal = find_exact_solution_for_meal(
            meal=DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=meal_distribution["training_optimization_applied"] and meal_index in focus_indexes,
            food_lookup=full_food_lookup,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            weekly_food_usage=weekly_food_usage,
        )
        planned_meals.append(planned_meal)
        track_food_usage_across_day(daily_food_usage, planned_meal)
        
    selected_food_codes = collect_selected_food_codes(planned_meals)
    internal_codes_to_resolve = [c for c in selected_food_codes if c in internal_food_lookup]
    resolved_food_lookup, lookup_metadata = resolve_foods_by_codes(
        database,
        internal_codes_to_resolve,
    )
    
    # We must mock some metadata properties if no internal codes were resolved 
    if not internal_codes_to_resolve:
        lookup_metadata["resolved_foods_count"] = len(selected_food_codes)
    food_lookup = {
        **full_food_lookup,
        **resolved_food_lookup,
    }
    generated_meals = [
        generate_food_based_meal(
            meal=DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=meal_distribution["training_optimization_applied"] and meal_index in focus_indexes,
            meal_plan=planned_meals[meal_index],
            food_lookup=food_lookup,
        )
        for meal_index, meal in enumerate(meal_distribution["meals"])
    ]
    food_data_source, food_data_sources = summarize_food_sources(generated_meals)
    preferred_food_matches = count_preferred_food_matches_in_meals(generated_meals, preference_profile)
    food_usage_summary = get_food_usage_summary_from_meals(generated_meals)
    daily_totals = calculate_daily_totals_from_meals(
        target_calories=meal_distribution["target_calories"],
        target_protein_grams=meal_distribution["protein_grams"],
        target_fat_grams=meal_distribution["fat_grams"],
        target_carb_grams=meal_distribution["carb_grams"],
        meals=generated_meals,
    )

    return {
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
        "food_catalog_version": lookup_metadata.get("food_catalog_version", get_food_catalog_version()),
        "food_preferences_applied": preference_profile.get("has_preferences", False),
        "applied_dietary_restrictions": preference_profile.get("dietary_restrictions", []),
        "applied_allergies": preference_profile.get("allergies", []),
        "preferred_food_matches": preferred_food_matches,
        "diversity_strategy_applied": True,
        "food_usage_summary": food_usage_summary,
        "food_filter_warnings": preference_profile.get("warnings", []),
        "catalog_source_strategy": lookup_metadata.get("catalog_source_strategy", CATALOG_SOURCE_STRATEGY_DEFAULT),
        "spoonacular_attempted": lookup_metadata.get("spoonacular_attempted", False),
        "spoonacular_attempts": lookup_metadata.get("spoonacular_attempts", 0),
        "spoonacular_hits": lookup_metadata.get("spoonacular_hits", 0),
        "cache_hits": lookup_metadata.get("cache_hits", 0),
        "internal_fallbacks": lookup_metadata.get("internal_fallbacks", 0),
        "resolved_foods_count": lookup_metadata.get("resolved_foods_count", len(selected_food_codes)),
        "meals": generated_meals,
    }


def generate_daily_diet(
    database,
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    return generate_food_based_diet(
        database,
        user=user,
        meals_count=meals_count,
        custom_percentages=custom_percentages,
        training_time_of_day=training_time_of_day,
    )


def _build_persistable_food_payload(food: dict) -> dict[str, Any]:
    return {
        "food_code": food.get("food_code"),
        "source": normalize_diet_food_source(food.get("source", DEFAULT_FOOD_DATA_SOURCE)),
        "origin_source": normalize_diet_food_source(
            food.get("origin_source", food.get("source", DEFAULT_FOOD_DATA_SOURCE))
        ),
        "spoonacular_id": food.get("spoonacular_id"),
        "name": food["name"],
        "category": food["category"],
        "quantity": round_food_value(float(food["quantity"])),
        "unit": food["unit"],
        "grams": round_food_value(float(food["grams"])) if food.get("grams") is not None else None,
        "calories": round_food_value(float(food["calories"])),
        "protein_grams": round_food_value(float(food["protein_grams"])),
        "fat_grams": round_food_value(float(food["fat_grams"])),
        "carb_grams": round_food_value(float(food["carb_grams"])),
    }


def _build_persistable_meal_payload(meal: dict) -> dict[str, Any]:
    return {
        "meal_number": meal["meal_number"],
        "distribution_percentage": round_diet_value(meal["distribution_percentage"]),
        "target_calories": round_diet_value(meal["target_calories"]),
        "target_protein_grams": round_diet_value(meal["target_protein_grams"]),
        "target_fat_grams": round_diet_value(meal["target_fat_grams"]),
        "target_carb_grams": round_diet_value(meal["target_carb_grams"]),
        "actual_calories": round_diet_value(meal["actual_calories"]),
        "actual_protein_grams": round_diet_value(meal["actual_protein_grams"]),
        "actual_fat_grams": round_diet_value(meal["actual_fat_grams"]),
        "actual_carb_grams": round_diet_value(meal["actual_carb_grams"]),
        "calorie_difference": round_diet_value(meal["calorie_difference"]),
        "protein_difference": round_diet_value(meal["protein_difference"]),
        "fat_difference": round_diet_value(meal["fat_difference"]),
        "carb_difference": round_diet_value(meal["carb_difference"]),
        "foods": [
            _build_persistable_food_payload(food)
            for food in meal.get("foods", [])
        ],
    }


def _build_persistable_diet_fields(diet_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "meals_count": diet_payload["meals_count"],
        "target_calories": round_diet_value(diet_payload["target_calories"]),
        "protein_grams": round_diet_value(diet_payload["protein_grams"]),
        "fat_grams": round_diet_value(diet_payload["fat_grams"]),
        "carb_grams": round_diet_value(diet_payload["carb_grams"]),
        "actual_calories": round_diet_value(diet_payload["actual_calories"]),
        "actual_protein_grams": round_diet_value(diet_payload["actual_protein_grams"]),
        "actual_fat_grams": round_diet_value(diet_payload["actual_fat_grams"]),
        "actual_carb_grams": round_diet_value(diet_payload["actual_carb_grams"]),
        "calorie_difference": round_diet_value(diet_payload["calorie_difference"]),
        "protein_difference": round_diet_value(diet_payload["protein_difference"]),
        "fat_difference": round_diet_value(diet_payload["fat_difference"]),
        "carb_difference": round_diet_value(diet_payload["carb_difference"]),
        "distribution_percentages": [
            round_diet_value(value) for value in diet_payload["distribution_percentages"]
        ],
        "training_time_of_day": diet_payload["training_time_of_day"],
        "training_optimization_applied": diet_payload["training_optimization_applied"],
        "food_data_source": diet_payload.get("food_data_source", DEFAULT_FOOD_DATA_SOURCE),
        "food_data_sources": diet_payload.get(
            "food_data_sources",
            [diet_payload.get("food_data_source", DEFAULT_FOOD_DATA_SOURCE)],
        ),
        "food_catalog_version": diet_payload.get("food_catalog_version"),
        "food_preferences_applied": diet_payload.get("food_preferences_applied", False),
        "applied_dietary_restrictions": diet_payload.get("applied_dietary_restrictions", []),
        "applied_allergies": diet_payload.get("applied_allergies", []),
        "preferred_food_matches": diet_payload.get("preferred_food_matches", 0),
        "diversity_strategy_applied": diet_payload.get("diversity_strategy_applied", False),
        "food_usage_summary": diet_payload.get("food_usage_summary", {}),
        "food_filter_warnings": diet_payload.get("food_filter_warnings", []),
        "catalog_source_strategy": diet_payload.get("catalog_source_strategy", CATALOG_SOURCE_STRATEGY_DEFAULT),
        "spoonacular_attempted": diet_payload.get("spoonacular_attempted", False),
        "spoonacular_attempts": diet_payload.get("spoonacular_attempts", 0),
        "spoonacular_hits": diet_payload.get("spoonacular_hits", 0),
        "cache_hits": diet_payload.get("cache_hits", 0),
        "internal_fallbacks": diet_payload.get("internal_fallbacks", 0),
        "resolved_foods_count": diet_payload.get("resolved_foods_count", 0),
        "meals": [
            _build_persistable_meal_payload(meal)
            for meal in diet_payload["meals"]
        ],
    }


def save_diet(database, user_id: str, diet_payload: dict) -> DailyDiet:
    diet_document = {
        "user_id": ObjectId(user_id),
        "created_at": datetime.now(UTC),
        **_build_persistable_diet_fields(diet_payload),
    }
    inserted = database.diets.insert_one(diet_document)
    created_diet = database.diets.find_one({"_id": inserted.inserted_id})
    return serialize_daily_diet(created_diet)


def list_user_diets(database, user_id: str) -> list[DietListItem]:
    documents = database.diets.find({"user_id": ObjectId(user_id)}).sort([("created_at", -1)])
    return [serialize_diet_list_item(document) for document in documents]


def get_user_diet_document_by_id(database, user_id: str, diet_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(diet_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet not found",
        )

    document = database.diets.find_one(
        {
            "_id": ObjectId(diet_id),
            "user_id": ObjectId(user_id),
        }
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet not found",
        )

    return document


def update_diet(database, user_id: str, diet_id: str, diet_payload: dict[str, Any]) -> DailyDiet:
    existing_document = get_user_diet_document_by_id(database, user_id, diet_id)
    database.diets.update_one(
        {
            "_id": existing_document["_id"],
            "user_id": ObjectId(user_id),
        },
        {
            "$set": _build_persistable_diet_fields(diet_payload),
        },
    )
    updated_document = database.diets.find_one({"_id": existing_document["_id"]})
    return serialize_daily_diet(updated_document)


def get_user_diet_by_id(database, user_id: str, diet_id: str) -> DailyDiet:
    return serialize_daily_diet(get_user_diet_document_by_id(database, user_id, diet_id))


def get_latest_user_diet(database, user_id: str) -> DailyDiet | None:
    document = database.diets.find_one(
        {"user_id": ObjectId(user_id)},
        sort=[("created_at", -1)],
    )
    if not document:
        return None

    return serialize_daily_diet(document)
