"""Solver exacto y ajuste cuantitativo de comidas."""

import hashlib
import logging
import time
from itertools import product
from typing import Any

from fastapi import HTTPException, status

from app.schemas.diet import DietMeal
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import FoodPreferenceConflictError, count_food_preference_matches
from app.utils.normalization import normalize_food_name

from app.services.diet.candidates import (
    _food_has_any_token,
    apply_daily_usage_candidate_limits,
    apply_family_repeat_penalty,
    apply_main_family_pair_repeat_penalty,
    apply_main_pair_repeat_penalty,
    apply_meal_structure_repeat_penalty,
    apply_meal_candidate_constraints,
    apply_preference_priority,
    apply_repeat_penalty,
    apply_support_option_constraints,
    apply_user_food_preferences_to_meal_candidates,
    apply_weekly_repeat_penalty,
    get_role_candidate_codes,
    get_food_family_signature,
    get_meal_structure_signature,
    get_support_option_specs,
    is_breakfast_fat,
    is_breakfast_only_protein,
    is_cooking_fat,
    is_concentrated_fruit_candidate,
    is_fast_digesting_carb,
    is_food_allowed_for_role_and_slot,
    is_lean_protein_candidate,
    is_role_combination_coherent,
    is_savory_protein,
    is_savory_starch,
    is_sweet_breakfast_carb,
    sort_codes_by_meal_fit,
)
from app.services.diet.common import (
    calculate_difference_summary,
    calculate_macro_calories,
    normalize_diet_food_source,
    resolve_meal_context,
    rotate_codes,
    round_diet_value,
    round_food_value,
)
from app.services.diet.constants import (
    BONUS_CORRELACION_ALIMENTARIA,
    BREAKFAST_BREAD_TOKENS,
    CANDIDATE_INDEX_WEIGHT,
    CARB_FRUIT_MAX_QUANTITY_G,
    CARB_FRUIT_MAX_QUANTITY_UNIDAD,
    CORRELACIONES_ALIMENTOS_COMPATIBLES,
    CORE_MACRO_KEYS,
    EARLY_SWEET_FAT_CODES,
    EXACT_SOLVER_TOLERANCE,
    FAT_OIL_MAX_QUANTITY_G,
    FOOD_OMIT_THRESHOLD,
    FOOD_SEMANTIC_EQUIVALENCES,
    FRUIT_CARB_TARGET_MULTIPLIER,
    LOW_FAT_MEAL_ROLES,
    MAX_ROLE_CANDIDATES_PER_MEAL,
    NEAR_BEST_SELECTION_WINDOW_BY_SLOT,
    ROLE_DISPLAY_ORDER,
    ROLE_FALLBACK_CODE_POOLS,
    ROLE_QUANTITY_SAFETY_CEILING_G,
    ROLE_QUANTITY_TARGET_MULTIPLIER,
    SAVORY_FAT_CODES,
    SOFT_ROLE_MINIMUMS,
    VALID_MEAL_ROLES,
)

logger = logging.getLogger(__name__)


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


def calculate_meal_actuals_from_foods(foods: list[dict]) -> dict[str, float]:
    actual_calories = round_diet_value(sum(float(food["calories"]) for food in foods))
    actual_protein_grams = round_diet_value(sum(float(food["protein_grams"]) for food in foods))
    actual_fat_grams = round_diet_value(sum(float(food["fat_grams"]) for food in foods))
    actual_carb_grams = round_diet_value(sum(float(food["carb_grams"]) for food in foods))
    return {
        "actual_calories": actual_calories,
        "actual_protein_grams": actual_protein_grams,
        "actual_fat_grams": actual_fat_grams,
        "actual_carb_grams": actual_carb_grams,
    }


def get_soft_role_minimum(food: dict, role: str) -> float:
    unit = food["reference_unit"]
    return SOFT_ROLE_MINIMUMS.get(role, {}).get(unit, 0.0)


def get_food_visibility_threshold(food: dict) -> float:
    return FOOD_OMIT_THRESHOLD.get(food["reference_unit"], 0.0)


def get_role_serving_floor(food: dict[str, Any], *, role: str, meal_slot: str, meal_role: str) -> float:
    del meal_role
    food_code = str(food.get("code") or "").strip().lower()
    base_floor = get_soft_role_minimum(food, role)

    if role == "carb":
        if food["reference_unit"] == "g":
            if _food_has_any_token(food, BREAKFAST_BREAD_TOKENS):
                return max(base_floor, 25.0)
            if is_savory_starch(food):
                return max(base_floor, 35.0)
            if is_sweet_breakfast_carb(food):
                return max(base_floor, 20.0)
        if food["reference_unit"] == "unidad" and derive_functional_group(food) == "fruit":
            return max(base_floor, 0.5)

    if role == "fat":
        if food_code == "olive_oil" or is_cooking_fat(food):
            return max(base_floor, 3.0)
        if food_code == "avocado":
            return max(base_floor, 18.0 if meal_slot == "early" else 25.0)
        if food_code == "mixed_nuts" or is_breakfast_fat(food):
            return max(base_floor, 8.0)

    return base_floor


def build_hidden_fat_penalty(food: dict[str, Any], quantity: float, *, role: str, meal_role: str) -> float:
    if role == "fat":
        if meal_role not in LOW_FAT_MEAL_ROLES:
            return 0.0
        food_code = str(food.get("code") or "").strip().lower()
        if food_code == "olive_oil" or is_cooking_fat(food):
            return 0.0
        return build_precise_food_values(food, quantity)["fat_grams"] * 0.03

    actual_fat_grams = build_precise_food_values(food, quantity)["fat_grams"]
    if actual_fat_grams <= 0:
        return 0.0

    multiplier = 0.12 if role == "protein" else 0.1
    if meal_role in LOW_FAT_MEAL_ROLES:
        multiplier += 0.07 if role == "protein" else 0.1
    elif meal_role == "breakfast":
        multiplier += 0.02

    return actual_fat_grams * multiplier


def _calcular_ajuste_correlacion_alimentaria(
    *,
    role_foods: dict[str, dict[str, Any]],
    support_foods: list[dict[str, Any]],
) -> float:
    """Premia combinaciones compatibles sin sobrevalorar soportes opcionales."""
    alimentos_por_codigo: dict[str, dict[str, Any]] = {}
    rol_por_codigo: dict[str, str] = {}

    for role, food in role_foods.items():
        code = str(food.get("code") or "").strip().lower()
        if not code:
            continue
        alimentos_por_codigo[code] = food
        rol_por_codigo[code] = role

    for support_food in support_foods:
        code = str(support_food.get("code") or support_food.get("food_code") or "").strip().lower()
        if not code:
            continue
        alimentos_por_codigo[code] = support_food
        rol_por_codigo[code] = str(support_food.get("role") or "support")

    codigos = sorted(alimentos_por_codigo)
    roles_soporte = {"fruit", "vegetable", "dairy", "support"}
    score = 0.0

    for index, code in enumerate(codigos):
        compatibles_code = set(CORRELACIONES_ALIMENTOS_COMPATIBLES.get(code, []))
        for partner in codigos[index + 1:]:
            compatibles_partner = set(CORRELACIONES_ALIMENTOS_COMPATIBLES.get(partner, []))
            if partner not in compatibles_code and code not in compatibles_partner:
                continue

            bonus = BONUS_CORRELACION_ALIMENTARIA
            if rol_por_codigo.get(code) in roles_soporte or rol_por_codigo.get(partner) in roles_soporte:
                bonus *= 0.5
            score -= bonus

    return score


def build_culinary_pairing_adjustment(
    *,
    role_foods: dict[str, dict[str, Any]],
    support_foods: list[dict[str, Any]],
    meal_slot: str,
    meal_role: str,
) -> float:
    protein_food = role_foods["protein"]
    carb_food = role_foods["carb"]
    fat_food = role_foods["fat"]
    protein_is_savory = is_savory_protein(protein_food)
    protein_is_dairy = is_breakfast_only_protein(protein_food)
    carb_is_sweet = is_sweet_breakfast_carb(carb_food) or derive_functional_group(carb_food) == "fruit"
    carb_is_bread = _food_has_any_token(carb_food, BREAKFAST_BREAD_TOKENS)
    carb_is_savory = is_savory_starch(carb_food) or carb_is_bread
    fat_code = str(fat_food.get("code") or "").strip().lower()
    fat_is_sweet = fat_code in EARLY_SWEET_FAT_CODES or is_breakfast_fat(fat_food)
    fat_is_savory = fat_code in SAVORY_FAT_CODES or is_cooking_fat(fat_food)
    support_roles = {str(food["role"]) for food in support_foods}
    score = 0.0

    if meal_slot == "early":
        if protein_is_dairy and carb_is_sweet:
            score -= 0.65
        if protein_is_savory and carb_is_bread:
            score -= 0.55
        if protein_is_savory and carb_is_sweet and meal_role not in LOW_FAT_MEAL_ROLES:
            score += 0.55
        if protein_is_dairy and carb_is_bread:
            score += 0.35
        if fat_is_sweet and (protein_is_dairy or carb_is_sweet):
            score -= 0.2
        if fat_code == "avocado" and protein_is_savory and carb_is_bread:
            score -= 0.18
        if fat_is_sweet and protein_is_savory:
            score += 0.25
    else:
        if carb_is_sweet:
            score += 0.8
        if protein_is_dairy:
            score += 0.9
        if protein_is_savory and carb_is_savory:
            score -= 0.45
        if fat_is_savory and protein_is_savory:
            score -= 0.12
        if fat_is_sweet:
            score += 0.45

    if "vegetable" in support_roles and meal_slot != "early":
        score -= 0.08
    if "fruit" in support_roles and meal_role in LOW_FAT_MEAL_ROLES:
        score -= 0.06
    if "dairy" in support_roles and meal_slot == "early":
        score -= 0.04

    score += _calcular_ajuste_correlacion_alimentaria(
        role_foods=role_foods,
        support_foods=support_foods,
    )

    return score


def build_breakfast_support_redundancy_penalty(
    *,
    role_foods: dict[str, dict[str, Any]],
    support_foods: list[dict[str, Any]],
    meal_slot: str,
) -> float:
    if meal_slot != "early":
        return 0.0

    protein_food = role_foods["protein"]
    if not is_breakfast_only_protein(protein_food):
        return 0.0

    penalty = 0.0
    for support_food in support_foods:
        if str(support_food.get("role") or "").strip().lower() != "dairy":
            continue

        support_family = get_food_family_signature(support_food, role="dairy")
        if support_family.endswith("milk"):
            penalty += 0.35
        elif support_family.endswith("fresh_cheese"):
            penalty += 1.05
        elif support_family.endswith("greek_yogurt") or support_family.endswith("yogurt"):
            penalty += 0.95
        else:
            penalty += 0.75

    return penalty


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


def build_solution_score(
    *,
    role_foods: dict[str, dict],
    role_quantities: dict[str, float],
    support_foods: list[dict],
    candidate_indexes: dict[str, int],
    training_focus: bool,
    meal_slot: str,
    meal_role: str,
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
        score += build_hidden_fat_penalty(
            food,
            quantity,
            role=role,
            meal_role=meal_role,
        )
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
        score += apply_family_repeat_penalty(
            food,
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
        serving_floor = get_role_serving_floor(
            food,
            role=role,
            meal_slot=meal_slot,
            meal_role=meal_role,
        )
        if quantity < serving_floor:
            score += ((serving_floor - quantity) / max(serving_floor, 1.0)) * 2.8

        if quantity > float(food["max_quantity"]) * 0.9:
            score += ((quantity - (float(food["max_quantity"]) * 0.9)) / max(float(food["max_quantity"]), 1.0)) * 6.0

        if role == "fat" and food["code"] == "olive_oil":
            score -= 0.15
        if role == "fat" and meal_role in LOW_FAT_MEAL_ROLES:
            if food["code"] == "olive_oil":
                score -= 0.28
            elif food["code"] == "mixed_nuts":
                score += 0.42
            elif food["code"] == "avocado":
                score += 0.14

        if role == "carb" and training_focus and food["code"] in {"rice", "pasta", "oats"}:
            score -= 0.2
        if (
            role == "carb"
            and meal_slot == "early"
            and derive_functional_group(food) == "fruit"
            and is_concentrated_fruit_candidate(food)
        ):
            score += 0.9

        if role == "protein" and meal_slot == "early" and food["code"] in {"egg_whites", "greek_yogurt"}:
            score -= 0.1
        if role == "protein" and meal_role in LOW_FAT_MEAL_ROLES and is_lean_protein_candidate(food):
            score -= 0.18

    score += apply_main_pair_repeat_penalty(
        role_foods,
        daily_food_usage=daily_food_usage,
    )
    score += apply_main_family_pair_repeat_penalty(
        role_foods,
        daily_food_usage=daily_food_usage,
    )

    if support_foods:
        for support_food in support_foods:
            score += {
                "vegetable": 0.22,
                "fruit": 0.32,
                "dairy": 0.28,
            }.get(str(support_food.get("role") or "support"), 0.25)
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
            score += apply_family_repeat_penalty(
                support_food,
                role=support_food["role"],
                daily_food_usage=daily_food_usage,
            )

    score += build_culinary_pairing_adjustment(
        role_foods=role_foods,
        support_foods=support_foods,
        meal_slot=meal_slot,
        meal_role=meal_role,
    )
    score += build_breakfast_support_redundancy_penalty(
        role_foods=role_foods,
        support_foods=support_foods,
        meal_slot=meal_slot,
    )
    score += apply_meal_structure_repeat_penalty(
        role_foods=role_foods,
        support_foods=support_foods,
        daily_food_usage=daily_food_usage,
    )

    return score


def _get_food_semantic_fingerprints(food: dict) -> frozenset[str]:
    """Devuelve un conjunto de tokens normalizados que representan semánticamente al alimento.

    Incluye código, nombres, nombre normalizado y aliases del catálogo.
    También añade equivalencias conocidas (ej: 'banana' ↔ 'platano').
    Se usa para evitar seleccionar dos alimentos que son el mismo con distinto nombre.
    """
    tokens: set[str] = set()
    for field in ("code", "name", "normalized_name", "original_name", "display_name"):
        raw = str(food.get(field) or "").replace("_", " ").strip()
        norm = normalize_food_name(raw).strip()
        if len(norm) >= 4:
            tokens.add(norm)
    for alias in food.get("aliases", []):
        norm = normalize_food_name(str(alias).replace("_", " ")).strip()
        if len(norm) >= 4:
            tokens.add(norm)
    # Añadir equivalencias conocidas entre idiomas o nombres alternativos
    code_norm = normalize_food_name(str(food.get("code") or "").replace("_", " ")).strip()
    for equiv in FOOD_SEMANTIC_EQUIVALENCES.get(code_norm, set()):
        tokens.add(equiv)
    return frozenset(tokens)


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
    meal_role = str(getattr(meal, "meal_role", "") or "").strip().lower()
    if meal_role not in VALID_MEAL_ROLES:
        meal_role = "training_focus" if training_focus else "meal"
    elif training_focus and meal_role == "meal":
        meal_role = "training_focus"
    all_codes = [
        role_foods["protein"]["code"],
        role_foods["carb"]["code"],
        role_foods["fat"]["code"],
        *[support_food["food_code"] for support_food in support_food_specs],
    ]
    if len(set(all_codes)) != len(all_codes):
        return None

    # Evitar duplicados semánticos: alimentos distintos que representan el mismo producto
    # (ej: 'Banana' y 'Plátano' tienen códigos diferentes pero son el mismo alimento)
    all_foods_for_dedup = list(role_foods.values()) + [
        food_lookup[sf["food_code"]]
        for sf in support_food_specs
        if sf["food_code"] in food_lookup
    ]
    seen_fingerprints: set[str] = set()
    seen_family_signatures: set[str] = set()
    for food_item in all_foods_for_dedup:
        fps = _get_food_semantic_fingerprints(food_item)
        if fps & seen_fingerprints:
            return None
        seen_fingerprints.update(fps)
        family_signature = get_food_family_signature(food_item)
        if family_signature in seen_family_signatures:
            return None
        seen_family_signatures.add(family_signature)

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
        serving_floor = get_role_serving_floor(
            role_foods[role],
            role=role,
            meal_slot=meal_slot,
            meal_role=meal_role,
        )
        if serving_floor > 0:
            floor_ratio = 0.45
            if role == "fat" and not is_cooking_fat(role_foods[role]):
                floor_ratio = 0.6
            if quantity + EXACT_SOLVER_TOLERANCE < serving_floor * floor_ratio:
                return None

        # Límites de cantidad: dinámicos para proteínas, almidones y grasas principales;
        # fijos solo donde el tipo de alimento lo justifica (frutas, aceites).
        food_item = role_foods[role]
        unit = food_item["reference_unit"]

        if unit == "g":
            # Límite dinámico: la cantidad no debe superar N× el objetivo macro del rol.
            # Al derivarse de target_*_grams de la comida, escala con el peso corporal
            # del usuario sin necesidad de conocerlo directamente.
            role_macro_target = {
                "protein": float(meal.target_protein_grams),
                "carb": float(meal.target_carb_grams),
                "fat": float(meal.target_fat_grams),
            }[role]
            role_macro_key = {
                "protein": "protein_grams",
                "carb": "carb_grams",
                "fat": "fat_grams",
            }[role]
            macro_density = get_food_macro_density(food_item).get(role_macro_key, 0.0)
            if macro_density > 0.01 and role_macro_target > 0:
                is_fruit_carb = role == "carb" and derive_functional_group(food_item) == "fruit"
                multiplier = FRUIT_CARB_TARGET_MULTIPLIER if is_fruit_carb else ROLE_QUANTITY_TARGET_MULTIPLIER
                if quantity > (role_macro_target / macro_density) * multiplier:
                    return None
            # Techo de seguridad absoluto: red de última instancia si la densidad macro
            # es muy baja y el límite dinámico resultara en un valor imposible.
            if quantity > ROLE_QUANTITY_SAFETY_CEILING_G.get(role, 1000.0):
                return None

        # Límite fijo para frutas como carbohidrato principal: evitar que suplan toda
        # la cuota de carbohidratos de comidas con objetivos altos (el solver elegirá
        # almidones en ese caso, que es la elección nutricionalmente correcta).
        if role == "carb" and derive_functional_group(food_item) == "fruit":
            if unit == "unidad" and quantity > CARB_FRUIT_MAX_QUANTITY_UNIDAD:
                return None
            if unit == "g" and quantity > CARB_FRUIT_MAX_QUANTITY_G:
                return None

        # Límite fijo para aceites y grasas de cocina: su uso es culinario y no escala
        # con el peso corporal del usuario.
        if role == "fat" and is_cooking_fat(food_item):
            if unit in {"g", "ml"} and quantity > FAT_OIL_MAX_QUANTITY_G:
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

    resolved_support_foods = [
        {
            **food_lookup[support_food["food_code"]],
            "role": support_food["role"],
        }
        for support_food in support_food_specs
    ]
    exact_actuals = calculate_meal_actuals_from_foods(foods)
    exact_actuals.update(
        calculate_difference_summary(
            target_calories=meal.target_calories,
            target_protein_grams=meal.target_protein_grams,
            target_fat_grams=meal.target_fat_grams,
            target_carb_grams=meal.target_carb_grams,
            actual_calories=exact_actuals["actual_calories"],
            actual_protein_grams=exact_actuals["actual_protein_grams"],
            actual_fat_grams=exact_actuals["actual_fat_grams"],
            actual_carb_grams=exact_actuals["actual_carb_grams"],
        )
    )

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
            meal_role=meal_role,
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
    variety_seed: int | None = None,
    preferred_support_candidates: list[dict] | None = None,
    expand_candidate_pool: bool = False,
    regeneration_context: dict[str, Any] | None = None,
) -> dict:
    # Calcular contexto de comida al inicio para reutilizarlo en toda la función
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )

    regeneration_context = dict(regeneration_context or {})
    original_food_codes = {
        str(code).strip()
        for code in regeneration_context.get("original_food_codes", set())
        if str(code).strip()
    }
    original_selected_role_codes = {
        role: str(food_code).strip()
        for role, food_code in regeneration_context.get("original_selected_role_codes", {}).items()
        if str(food_code).strip()
    }
    prefer_visible_difference = bool(regeneration_context.get("prefer_visible_difference"))
    min_visual_difference = max(int(regeneration_context.get("min_visual_difference", 2) or 0), 1)
    target_distinct_calorie_ratio = float(regeneration_context.get("min_distinct_calorie_ratio", 0.45) or 0.0)
    actual_expand_candidate_pool = expand_candidate_pool or bool(regeneration_context.get("expand_candidate_pool"))

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
        food_lookup=food_lookup,
        expand_candidate_pool=actual_expand_candidate_pool,
    )

    # Inyectar alimentos de soporte preferidos como opciones adicionales.
    # Se añaden antes del filtrado de preferencias para que el sistema de puntuación
    # los priorice correctamente (los alimentos preferidos reciben bonus en el score).
    # Solo se inyectan si no hay forced_support_foods que ya reemplacen todo el soporte.
    if preferred_support_candidates and forced_support_foods is None:
        for candidato in reversed(preferred_support_candidates):
            if candidato["food_code"] in food_lookup:
                support_options = [[{
                    "role": candidato["role"],
                    "food_code": candidato["food_code"],
                    "quantity": candidato["quantity"],
                }]] + support_options

    if preference_profile and preference_profile.get("has_preferences"):
        try:
            candidate_codes, support_options = apply_user_food_preferences_to_meal_candidates(
                candidate_codes=candidate_codes,
                support_options=support_options,
                food_lookup=food_lookup,
                preference_profile=preference_profile,
            )
        except FoodPreferenceConflictError:
            # Las preferencias positivas son blandas: si el filtro falla sin ancla forzada
            # pero no hay restricciones duras activas (alergias/disgustos/restricciones),
            # continuamos con el pool original en lugar de abortar.
            # Solo re-lanzamos si hay restricciones duras que justifiquen el bloqueo.
            if not forced_role_codes and preference_profile.get("has_negative_preferences"):
                raise
            # Ancla forzada o solo preferencias positivas: continuar con pool sin filtrar.

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

    # Variedad en regeneración: rotar el orden de candidatos para explorar combinaciones
    # distintas en cada llamada. Solo se aplica sin alimentos forzados para no desplazar
    # el alimento preferido del usuario de la posición 0.
    if variety_seed is not None and not forced_role_codes:
        candidate_codes = {
            role: rotate_codes(codes, variety_seed + idx)
            for idx, (role, codes) in enumerate(candidate_codes.items())
        }

    solver_started_at = time.perf_counter()
    near_best_window = NEAR_BEST_SELECTION_WINDOW_BY_SLOT.get(meal_slot, 0.9)
    best_solution: dict | None = None
    best_selection_score: float | None = None
    best_base_score: float | None = None
    near_best_candidates: list[tuple[float, dict[str, Any]]] = []
    evaluated_combinations = 0
    valid_combinations = 0

    def build_candidate_fingerprint(candidate_solution: dict[str, Any]) -> str:
        fingerprint_parts = [
            str(candidate_solution.get("selected_role_codes", {}).get(role) or "").strip()
            for role in ("protein", "carb", "fat")
        ]
        fingerprint_parts.extend(
            sorted(
                str(support_food.get("food_code") or "").strip()
                for support_food in candidate_solution.get("support_food_specs", [])
                if str(support_food.get("food_code") or "").strip()
            )
        )
        return "|".join(part for part in fingerprint_parts if part)

    def build_variety_selection_adjustment(candidate_solution: dict[str, Any]) -> float:
        if variety_seed is None:
            return 0.0

        fingerprint = build_candidate_fingerprint(candidate_solution)
        if not fingerprint:
            return 0.0

        digest = hashlib.blake2b(
            f"{variety_seed}:{fingerprint}".encode("utf-8"),
            digest_size=8,
        ).digest()
        normalized_value = int.from_bytes(digest, "big") / float(2**64 - 1)
        max_adjustment = 0.18 if prefer_visible_difference else 0.12
        return normalized_value * max_adjustment

    def build_regeneration_selection_penalty(candidate_solution: dict[str, Any]) -> float:
        if not prefer_visible_difference or not original_food_codes:
            return 0.0

        candidate_codes = {
            str(food.get("food_code") or "").strip()
            for food in candidate_solution.get("foods", [])
            if str(food.get("food_code") or "").strip()
        }
        changed_visible_food_count = max(
            len(original_food_codes - candidate_codes),
            len(candidate_codes - original_food_codes),
        )
        penalty = 0.0

        if changed_visible_food_count < min_visual_difference:
            penalty += (min_visual_difference - changed_visible_food_count) * 4.5

        candidate_role_codes = {
            role: str(food_code).strip()
            for role, food_code in candidate_solution.get("selected_role_codes", {}).items()
            if str(food_code).strip()
        }
        if original_selected_role_codes:
            same_carb = original_selected_role_codes.get("carb") == candidate_role_codes.get("carb")
            same_protein = original_selected_role_codes.get("protein") == candidate_role_codes.get("protein")
            same_fat = original_selected_role_codes.get("fat") == candidate_role_codes.get("fat")

            if same_carb:
                penalty += 2.4
            if same_protein:
                penalty += 1.8
            if same_fat:
                penalty += 0.6
            if same_carb and same_protein:
                penalty += 4.0

        total_calories = max(float(candidate_solution.get("actual_calories") or 0.0), 1.0)
        distinct_calories = sum(
            float(food.get("calories") or 0.0)
            for food in candidate_solution.get("foods", [])
            if str(food.get("food_code") or "").strip() not in original_food_codes
        )
        distinct_calorie_ratio = distinct_calories / total_calories
        if distinct_calorie_ratio < target_distinct_calorie_ratio:
            penalty += (target_distinct_calorie_ratio - distinct_calorie_ratio) * 5.0

        return penalty

    def register_candidate_solution(candidate_solution: dict[str, Any]) -> None:
        nonlocal best_base_score, best_selection_score, best_solution, valid_combinations, near_best_candidates

        valid_combinations += 1
        base_selection_score = (
            float(candidate_solution["score"])
            + build_regeneration_selection_penalty(candidate_solution)
        )
        if best_base_score is None or base_selection_score < best_base_score:
            best_base_score = base_selection_score
            near_best_candidates = [
                (score, solution)
                for score, solution in near_best_candidates
                if score <= best_base_score + near_best_window
            ]

        if best_base_score is None or base_selection_score <= best_base_score + near_best_window:
            near_best_candidates.append((base_selection_score, candidate_solution))
            near_best_candidates.sort(key=lambda item: item[0])
            near_best_candidates = near_best_candidates[:48]

        selection_score = base_selection_score + build_variety_selection_adjustment(candidate_solution)
        if best_solution is None or best_selection_score is None or selection_score < best_selection_score:
            best_solution = candidate_solution
            best_selection_score = selection_score

    def select_best_solution() -> dict[str, Any] | None:
        if not near_best_candidates:
            return best_solution
        if variety_seed is None:
            return min(near_best_candidates, key=lambda item: item[0])[1]

        best_by_structure: dict[str, tuple[float, dict[str, Any]]] = {}
        for base_score, candidate_solution in near_best_candidates:
            structure_signature = get_meal_structure_signature(
                selected_role_codes={
                    role: str(food_code).strip()
                    for role, food_code in candidate_solution.get("selected_role_codes", {}).items()
                },
                support_food_specs=candidate_solution.get("support_food_specs", []),
            )
            existing_candidate = best_by_structure.get(structure_signature)
            if existing_candidate is None or base_score < existing_candidate[0]:
                best_by_structure[structure_signature] = (base_score, candidate_solution)

        ranked_candidates: list[tuple[tuple[float, float, str], dict[str, Any]]] = []
        for structure_signature, (base_score, candidate_solution) in best_by_structure.items():
            fingerprint = build_candidate_fingerprint(candidate_solution) or structure_signature
            digest = hashlib.blake2b(
                f"{variety_seed}:{structure_signature}:{fingerprint}".encode("utf-8"),
                digest_size=8,
            ).digest()
            normalized_value = int.from_bytes(digest, "big") / float(2**64 - 1)
            ranked_candidates.append(((normalized_value, base_score, fingerprint), candidate_solution))

        return min(ranked_candidates, key=lambda item: item[0])[1]

    def finalize_solution(solution: dict[str, Any] | None, *, strategy: str) -> dict[str, Any] | None:
        if solution is None:
            return None

        logger.debug(
            "Diet solver solved meal=%s slot=%s role=%s strategy=%s elapsed=%.4fs evaluated=%s valid=%s role_pool=%s support_options=%s structure=%s",
            getattr(meal, "meal_number", None),
            meal_slot,
            meal_role,
            strategy,
            time.perf_counter() - solver_started_at,
            evaluated_combinations,
            valid_combinations,
            {role: len(codes) for role, codes in candidate_codes.items()},
            len(support_options),
            get_meal_structure_signature(
                selected_role_codes=solution.get("selected_role_codes", {}),
                support_food_specs=solution.get("support_food_specs", []),
            ),
        )
        return solution

    def evaluate_candidate_sets(role_codes: dict[str, list[str]], extra_support_options: list[list[dict]]) -> None:
        nonlocal evaluated_combinations

        evaluated_combinations += (
            len(role_codes["protein"])
            * len(role_codes["carb"])
            * len(role_codes["fat"])
            * len(extra_support_options)
        )

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

                register_candidate_solution(candidate_solution)

    def build_expanded_role_codes() -> dict[str, list[str]]:
        excluded = excluded_food_codes or set()
        expanded_codes: dict[str, list[str]] = {}

        for role in ("protein", "carb", "fat"):
            compatible_codes = [
                code
                for code, food in food_lookup.items()
                if code not in excluded
                and is_food_allowed_for_role_and_slot(food, role=role, meal_slot=meal_slot)
            ]
            sorted_codes = sort_codes_by_meal_fit(
                compatible_codes,
                role=role,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
                food_lookup=food_lookup,
            )
            expansion_multiplier = 3 if meal_slot == "early" else 2
            expanded_limit = max(
                len(candidate_codes[role]),
                MAX_ROLE_CANDIDATES_PER_MEAL[role] * expansion_multiplier,
            )
            expanded_codes[role] = sorted_codes[:expanded_limit]

        expanded_codes = apply_daily_usage_candidate_limits(
            expanded_codes,
            daily_food_usage=daily_food_usage,
        )
        expanded_codes = apply_meal_candidate_constraints(
            expanded_codes,
            food_lookup=food_lookup,
            forced_role_codes=forced_role_codes,
            excluded_food_codes=excluded_food_codes,
        )

        if variety_seed is not None and not forced_role_codes:
            expanded_codes = {
                role: rotate_codes(codes, variety_seed + idx)
                for idx, (role, codes) in enumerate(expanded_codes.items())
            }

        return expanded_codes

    evaluate_candidate_sets(candidate_codes, support_options)
    selected_solution = finalize_solution(select_best_solution(), strategy="base_pool")
    if selected_solution:
        return selected_solution

    if actual_expand_candidate_pool:
        expanded_role_codes = build_expanded_role_codes()
        if expanded_role_codes != candidate_codes:
            evaluate_candidate_sets(expanded_role_codes, support_options)
            selected_solution = finalize_solution(select_best_solution(), strategy="expanded_pool")
            if selected_solution:
                return selected_solution

    # ── Estrategia A: pool ampliado para alimentos forzados por el usuario vía API ────────
    # Cuando forced_role_codes está presente, el alimento forzado queda al frente de su rol
    # pero los otros dos roles pueden no tener candidatos suficientes para complementarlo.
    # Ampliamos el pool de esos roles con todos los alimentos compatibles del catálogo.
    if forced_role_codes:
        excluded = excluded_food_codes or set()
        expanded_forced: dict[str, list[str]] = {}
        for role in ("protein", "carb", "fat"):
            if role in forced_role_codes:
                expanded_forced[role] = candidate_codes[role]
            else:
                all_compatible = [
                    code
                    for code, food in food_lookup.items()
                    if code not in excluded
                    and is_food_allowed_for_role_and_slot(food, role=role, meal_slot=meal_slot)
                ]
                expanded_forced[role] = sort_codes_by_meal_fit(
                    all_compatible,
                    role=role,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                    training_focus=training_focus,
                    food_lookup=food_lookup,
                )[:MAX_ROLE_CANDIDATES_PER_MEAL[role] * 2]
        expanded_forced = apply_meal_candidate_constraints(
            expanded_forced,
            food_lookup=food_lookup,
            forced_role_codes=forced_role_codes,
            excluded_food_codes=excluded_food_codes,
        )
        evaluate_candidate_sets(expanded_forced, [[]])
        selected_solution = finalize_solution(select_best_solution(), strategy="forced_pool")
        if selected_solution:
            return selected_solution

    # ── Estrategia B: alimentos preferidos como ancla de la comida ────────────────────────
    # Solo se activa cuando el usuario indicó alimentos que QUIERE ver (preferencias positivas).
    # Los disgustos o restricciones sin preferencias positivas no justifican esta búsqueda.
    if not forced_role_codes and preference_profile and preference_profile.get("has_positive_preferences"):
        excluded = excluded_food_codes or set()
        for anchor_role in ("protein", "carb", "fat"):
            if best_solution:
                break
            # Identificar qué alimentos preferidos del usuario pueden ocupar este rol
            # en el slot de comida actual (desayuno, comida, cena…)
            preferred_anchors = [
                code
                for code, food in food_lookup.items()
                if code not in excluded
                and is_food_allowed_for_role_and_slot(food, role=anchor_role, meal_slot=meal_slot)
                and count_food_preference_matches(food, preference_profile) > 0
            ]
            if not preferred_anchors:
                continue

            # Construir pool: preferidos al frente del rol ancla,
            # todos los compatibles del catálogo para los roles complementarios.
            anchor_candidate_codes: dict[str, list[str]] = {}
            for role in ("protein", "carb", "fat"):
                all_role_compatible = [
                    code
                    for code, food in food_lookup.items()
                    if code not in excluded
                    and is_food_allowed_for_role_and_slot(food, role=role, meal_slot=meal_slot)
                ]
                sorted_compatible = sort_codes_by_meal_fit(
                    all_role_compatible,
                    role=role,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                    training_focus=training_focus,
                    food_lookup=food_lookup,
                )
                if role == anchor_role:
                    anchors_set = set(preferred_anchors)
                    rest = [c for c in sorted_compatible if c not in anchors_set]
                    # Preferidos al frente + top N del resto para no explotar combinaciones
                    anchor_candidate_codes[role] = (
                        preferred_anchors + rest[:MAX_ROLE_CANDIDATES_PER_MEAL[role]]
                    )
                else:
                    anchor_candidate_codes[role] = sorted_compatible[
                        :MAX_ROLE_CANDIDATES_PER_MEAL[role] * 2
                    ]
            evaluate_candidate_sets(anchor_candidate_codes, [[]])

    selected_solution = finalize_solution(select_best_solution(), strategy="preferred_anchor")
    if selected_solution:
        return selected_solution

    # ── Estrategia C: pool de seguridad con alimentos básicos garantizados ────────────────
    # Se ejecuta para TODOS los usuarios, incluidos los que tienen preferencias.
    # Antes este bloque era inalcanzable para usuarios con has_preferences=True porque el
    # error se lanzaba antes. Ahora es la última oportunidad antes del error definitivo.
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
    fallback_role_codes = {
        role: sort_codes_by_meal_fit(
            codes,
            role=role,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )[:MAX_ROLE_CANDIDATES_PER_MEAL[role]]
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

    selected_solution = finalize_solution(select_best_solution(), strategy="fallback_pool")
    if selected_solution:
        return selected_solution

    # ── Estrategia D: relajación completa de preferencias positivas ──────────────────────────
    # Preferencias positivas = prioridad blanda. Si todas las estrategias anteriores
    # fallaron con ellas activas, se reintenta ignorándolas por completo y manteniendo
    # solo restricciones duras (alergias, disgustos, restricciones dietéticas).
    # Esto garantiza que "quiero cornflakes" nunca bloquea la generación de la dieta.
    if preference_profile and preference_profile.get("has_positive_preferences"):
        relaxed_profile = {
            **preference_profile,
            "has_positive_preferences": False,
            "has_preferences": preference_profile.get("has_negative_preferences", False),
            "preferred_foods": [],
            "normalized_preferred_foods": set(),
        }
        relaxed_candidate_codes = get_role_candidate_codes(
            meal=meal,
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )
        relaxed_support_options = get_support_option_specs(
            meal=meal,
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
            food_lookup=food_lookup,
            expand_candidate_pool=actual_expand_candidate_pool,
        )
        if relaxed_profile.get("has_preferences"):
            # Solo restricciones duras: si esto falla, el error sí es real
            relaxed_candidate_codes, relaxed_support_options = apply_user_food_preferences_to_meal_candidates(
                candidate_codes=relaxed_candidate_codes,
                support_options=relaxed_support_options,
                food_lookup=food_lookup,
                preference_profile=relaxed_profile,
            )
        relaxed_candidate_codes = apply_daily_usage_candidate_limits(
            relaxed_candidate_codes,
            daily_food_usage=daily_food_usage,
        )
        relaxed_candidate_codes = apply_meal_candidate_constraints(
            relaxed_candidate_codes,
            food_lookup=food_lookup,
            forced_role_codes=forced_role_codes,
            excluded_food_codes=excluded_food_codes,
        )
        relaxed_support_options = apply_support_option_constraints(
            relaxed_support_options,
            food_lookup=food_lookup,
            forced_support_foods=forced_support_foods,
            excluded_food_codes=excluded_food_codes,
        )
        evaluate_candidate_sets(relaxed_candidate_codes, relaxed_support_options)
        selected_solution = finalize_solution(select_best_solution(), strategy="relaxed_preferences")
        if selected_solution:
            return selected_solution

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
