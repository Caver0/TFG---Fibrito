"""Seleccion, filtrado y priorizacion de candidatos para dietas."""

from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DietMeal
from app.services.food_classifier_service import predict_meal_slot_scores
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import (
    FoodPreferenceConflictError,
    apply_user_food_preferences,
    count_food_preference_matches,
    filter_allowed_foods,
    prioritize_preferred_foods,
)
from app.utils.normalization import normalize_food_name

from app.services.diet.common import resolve_meal_context, rotate_codes
from app.services.diet.constants import (
    BREAKFAST_BREAD_TOKENS,
    BREAKFAST_FAT_TOKENS,
    BREAKFAST_ONLY_DAIRY_TOKENS,
    BREAKFAST_PROTEIN_TOKENS,
    COOKING_FAT_TOKENS,
    DEFAULT_PROTEIN_ROLE_DAILY_MAX_USAGE,
    EARLY_SWEET_FAT_CODES,
    FAST_DIGESTING_CARB_CODES,
    LEAN_PROTEIN_CODES,
    LOW_FAT_MEAL_ROLES,
    MAX_ROLE_CANDIDATES_PER_MEAL,
    MAX_SUPPORT_CANDIDATES_PER_ROLE,
    PREFERRED_FOOD_BONUS_BY_ROLE,
    PROTEIN_ROLE_DAILY_MAX_USAGE_BY_CODE,
    REPEATED_MAIN_PAIR_PENALTY,
    REPEAT_ESCALATION_BY_ROLE,
    REPEAT_PENALTY_BY_ROLE,
    ROLE_FALLBACK_CODE_POOLS,
    ROLE_LABELS,
    SAVORY_FAT_CODES,
    SAVORY_PROTEIN_TOKENS,
    SAVORY_STARCH_TOKENS,
    SWEET_BREAKFAST_CARB_TOKENS,
    WEEKLY_DIVERSITY_WINDOW_DAYS,
    WEEKLY_REPEAT_PENALTY_BY_ROLE,
    CORE_MACRO_KEYS,
)


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

    # ── Ruta con preferencias positivas (el usuario especificó alimentos deseados) ──
    # Filtrado completo con priorización de preferidos y posible FoodPreferenceConflictError
    # si el pool de un rol queda vacío tras aplicar restricciones.
    if preference_profile.get("has_positive_preferences"):
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

    # ── Ruta con solo preferencias negativas (disgustos, restricciones, alergias) ──
    # Excluir alimentos no permitidos sin restringir el pool innecesariamente.
    # Si el filtro vaciara un rol, se conserva el pool original para que el solver
    # pueda recurrir a la Estrategia C sin lanzar error prematuro.
    filtered_codes: dict[str, list[str]] = {}
    for role, role_codes in candidate_codes.items():
        role_foods = [food_lookup[code] for code in role_codes if code in food_lookup]
        allowed_foods, _ = filter_allowed_foods(role_foods, preference_profile)
        filtered_pool = [food["code"] for food in allowed_foods]
        filtered_codes[role] = filtered_pool if filtered_pool else role_codes

    filtered_support_options = _build_preference_filtered_support_options(
        support_options=support_options,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
    )
    return filtered_codes, filtered_support_options


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
        # Heurística por tokens antes de usar el grupo funcional genérico.
        # Permite clasificar correctamente cereales, lácteos de desayuno y frutos secos
        # sin depender de un campo 'suitable_meals' en el catálogo.
        if is_sweet_breakfast_carb(food) or is_breakfast_only_protein(food):
            # Cereales, copos, yogures, leche → típicamente desayuno o merienda
            slots.update({"early"})
        elif is_breakfast_fat(food):
            # Frutos secos, semillas → válidos en cualquier comida
            slots.update({"early", "main", "late"})
        else:
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


def get_food_macro_mass_profile(food: dict) -> dict[str, float]:
    grams_base = max(float(food.get("grams_per_reference") or food["reference_amount"]), 1.0)
    return {
        macro_key: float(food[macro_key]) / grams_base
        for macro_key in CORE_MACRO_KEYS
    }


def get_food_fat_density(food: dict) -> float:
    return get_food_macro_mass_profile(food)["fat_grams"]


def is_lean_protein_candidate(food: dict) -> bool:
    food_code = str(food.get("code") or "").strip().lower()
    if food_code in LEAN_PROTEIN_CODES:
        return True

    return get_food_fat_density(food) <= 0.035


def is_fast_digesting_carb(food: dict) -> bool:
    food_code = str(food.get("code") or "").strip().lower()
    if food_code in FAST_DIGESTING_CARB_CODES:
        return True

    return (
        is_savory_starch(food)
        or is_sweet_breakfast_carb(food)
        or _food_has_any_token(food, BREAKFAST_BREAD_TOKENS)
        or derive_functional_group(food) == "fruit"
    )


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


def get_food_role_fit_score(
    food: dict[str, Any],
    *,
    role: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> float:
    score = get_food_slot_affinity_score(food, meal_slot)
    macro_density = get_food_macro_mass_profile(food)
    fat_density = macro_density["fat_grams"]
    food_code = str(food.get("code") or "").strip().lower()

    if role == "protein":
        score += macro_density["protein_grams"] * 1.6
        score -= fat_density * (18.0 if meal_role in LOW_FAT_MEAL_ROLES else 10.0)
        if is_lean_protein_candidate(food):
            score += 0.3
        if meal_role in LOW_FAT_MEAL_ROLES and is_lean_protein_candidate(food):
            score += 0.45
        if meal_role == "breakfast":
            if is_breakfast_only_protein(food):
                score += 0.35
            elif is_savory_protein(food):
                score += 0.18
        elif meal_slot != "early" and is_savory_protein(food):
            score += 0.15

    elif role == "carb":
        score += macro_density["carb_grams"] * 1.2
        score -= fat_density * (20.0 if meal_role in LOW_FAT_MEAL_ROLES else 9.0)
        if meal_slot == "early":
            if is_sweet_breakfast_carb(food) or _food_has_any_token(food, BREAKFAST_BREAD_TOKENS):
                score += 0.22
        elif is_savory_starch(food):
            score += 0.24
        if meal_role in LOW_FAT_MEAL_ROLES and is_fast_digesting_carb(food):
            score += 0.42

    elif role == "fat":
        score += macro_density["fat_grams"] * 2.1
        if meal_role in LOW_FAT_MEAL_ROLES:
            if food_code == "olive_oil" or is_cooking_fat(food):
                score += 0.48
            elif food_code == "avocado":
                score -= 0.12
            elif food_code == "mixed_nuts" or is_breakfast_fat(food):
                score -= 0.45
        elif meal_slot == "early":
            if food_code == "avocado":
                score += 0.24
            if food_code in EARLY_SWEET_FAT_CODES or is_breakfast_fat(food):
                score += 0.18
        elif food_code in SAVORY_FAT_CODES or is_cooking_fat(food):
            score += 0.2

    if training_focus and meal_role in LOW_FAT_MEAL_ROLES and fat_density <= 0.02 and role != "fat":
        score += 0.12

    return score


def sort_codes_by_meal_fit(
    codes: list[str],
    *,
    role: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    food_lookup: dict[str, dict],
) -> list[str]:
    return sorted(
        codes,
        key=lambda code: -get_food_role_fit_score(
            food_lookup[code],
            role=role,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
        ),
    )


def is_support_food_allowed(
    food: dict[str, Any],
    *,
    support_role: str,
    meal_slot: str,
    meal_role: str,
) -> bool:
    functional_group = derive_functional_group(food)
    if functional_group != support_role:
        return False

    allowed_slots = get_allowed_meal_slots_for_food(food)
    if meal_slot in allowed_slots:
        return True
    if support_role == "vegetable" and meal_slot == "late" and "main" in allowed_slots:
        return True
    if support_role in {"fruit", "dairy"} and meal_role in {"breakfast", "pre_workout", "post_workout", "training_focus"}:
        return bool(allowed_slots & {"early", "snack"})

    return False


def get_support_food_fit_score(
    food: dict[str, Any],
    *,
    support_role: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> float:
    fallback_slot = meal_slot
    if support_role in {"fruit", "dairy"} and meal_slot not in get_allowed_meal_slots_for_food(food):
        fallback_slot = "early"

    score = get_food_slot_affinity_score(food, fallback_slot)
    macro_density = get_food_macro_mass_profile(food)
    fat_density = macro_density["fat_grams"]
    protein_density = macro_density["protein_grams"]

    if support_role == "vegetable":
        score += 0.45 if meal_slot != "early" else -0.2
        score -= fat_density * 10.0
    elif support_role == "fruit":
        if meal_slot == "early" or meal_role in LOW_FAT_MEAL_ROLES:
            score += 0.42
        score += macro_density["carb_grams"] * 0.45
        score -= fat_density * 8.0
    elif support_role == "dairy":
        score += protein_density * 1.1
        if meal_slot == "early":
            score += 0.35
        score -= fat_density * (14.0 if meal_role in LOW_FAT_MEAL_ROLES else 9.0)

    if training_focus and meal_role in LOW_FAT_MEAL_ROLES and fat_density <= 0.02:
        score += 0.08

    return score


def get_support_candidate_foods(
    food_lookup: dict[str, dict[str, Any]],
    *,
    support_role: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> list[dict[str, Any]]:
    ranked_candidates = sorted(
        (
            food
            for food in food_lookup.values()
            if is_support_food_allowed(
                food,
                support_role=support_role,
                meal_slot=meal_slot,
                meal_role=meal_role,
            )
        ),
        key=lambda food: -get_support_food_fit_score(
            food,
            support_role=support_role,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
        ),
    )
    return _dedupe_foods_by_code(ranked_candidates)[:MAX_SUPPORT_CANDIDATES_PER_ROLE]


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
    """Cuenta repeticiones semanales para suavizar la diversidad."""
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
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    rotation_seed = meal_index + meals_count

    protein_codes = []
    carb_codes = []
    fat_codes = []

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
        protein_codes = sort_codes_by_meal_fit(
            rotate_codes(protein_codes, rotation_seed),
            role="protein",
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )
        carb_codes = sort_codes_by_meal_fit(
            rotate_codes(carb_codes, rotation_seed + 1),
            role="carb",
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )
        fat_codes = sort_codes_by_meal_fit(
            rotate_codes(fat_codes, rotation_seed + 2),
            role="fat",
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )
    else:
        protein_codes = rotate_codes(protein_codes, rotation_seed)
        carb_codes = rotate_codes(carb_codes, rotation_seed + 1)
        fat_codes = rotate_codes(fat_codes, rotation_seed + 2)

    return {
        "protein": protein_codes[:MAX_ROLE_CANDIDATES_PER_MEAL["protein"]],
        "carb": carb_codes[:MAX_ROLE_CANDIDATES_PER_MEAL["carb"]],
        "fat": fat_codes[:MAX_ROLE_CANDIDATES_PER_MEAL["fat"]],
    }


def get_support_option_specs(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict] | None = None,
) -> list[list[dict]]:
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    support_options: list[list[dict]] = [[]]
    seen_keys: set[tuple[tuple[str, float], ...]] = {tuple()}

    def add_support_option(role: str, food_code: str, quantity: float) -> None:
        option = [{
            "role": role,
            "food_code": food_code,
            "quantity": float(quantity),
        }]
        option_key = tuple(sorted((item["food_code"], float(item["quantity"])) for item in option))
        if option_key in seen_keys:
            return

        support_options.append(option)
        seen_keys.add(option_key)

    def iter_support_foods(role: str, fallback_codes: list[str]) -> list[dict]:
        if food_lookup:
            ranked_foods = get_support_candidate_foods(
                food_lookup,
                support_role=role,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            )
            if ranked_foods:
                return ranked_foods

        if not food_lookup:
            return [{"code": code} for code in fallback_codes]

        return [food_lookup[code] for code in fallback_codes if code in food_lookup]

    if meal_slot != "early" and meal.target_calories >= 320 and meal.target_carb_grams >= 15:
        vegetable_quantity = 80.0 if meal.target_calories < 520 else 120.0
        for vegetable_food in iter_support_foods("vegetable", ["mixed_vegetables"]):
            add_support_option("vegetable", vegetable_food["code"], vegetable_quantity)

    if (meal_slot == "early" or meal_role in LOW_FAT_MEAL_ROLES) and meal.target_carb_grams >= 35:
        fruit_quantity = 0.5 if meal.target_carb_grams < 80 else 1.0
        for fruit_food in iter_support_foods("fruit", ["banana"]):
            add_support_option("fruit", fruit_food["code"], fruit_quantity)

    if meal_slot == "early" and meal.target_calories <= 320 and meal.target_protein_grams <= 28:
        for dairy_food in iter_support_foods("dairy", ["greek_yogurt"]):
            default_quantity = float(dairy_food.get("default_quantity") or 1.0)
            add_support_option("dairy", dairy_food["code"], default_quantity)

    return support_options
