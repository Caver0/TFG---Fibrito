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
    CORE_MACRO_KEYS,
    COOKING_FAT_TOKENS,
    DEFAULT_PROTEIN_ROLE_DAILY_MAX_USAGE,
    EARLY_SWEET_FAT_CODES,
    FAMILY_REPEAT_PENALTY_BY_ROLE,
    FAST_DIGESTING_CARB_CODES,
    FOOD_OMIT_THRESHOLD,
    LEAN_PROTEIN_CODES,
    LOW_FAT_MEAL_ROLES,
    MAX_ROLE_CANDIDATES_PER_MEAL,
    MAX_SUPPORT_CANDIDATES_PER_ROLE,
    PREFERRED_FOOD_BONUS_BY_ROLE,
    PROTEIN_ROLE_DAILY_MAX_USAGE_BY_CODE,
    REPEATED_MAIN_FAMILY_PAIR_PENALTY,
    REPEATED_MEAL_STRUCTURE_PENALTY,
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
)

CONCENTRATED_FRUIT_TOKENS = (
    "date",
    "dates",
    "datil",
    "datiles",
    "raisin",
    "raisins",
    "pasa",
    "pasas",
    "prune",
    "prunes",
    "ciruela pasa",
    "dried",
    "deshidrat",
    "dehydrated",
    "fig",
    "figs",
    "higo",
    "higos",
)
CONCENTRATED_FRUIT_CARB_DENSITY_THRESHOLD = 0.45
CONCENTRATED_FRUIT_CALORIE_DENSITY_THRESHOLD = 2.1
CONCENTRATED_FRUIT_MAIN_CARB_PENALTY = 0.8
BREAKFAST_CONCENTRATED_FRUIT_MAIN_CARB_EXTRA_PENALTY = 0.24
CONCENTRATED_FRUIT_SUPPORT_PENALTY = 0.55
BREAKFAST_CONCENTRATED_FRUIT_SUPPORT_EXTRA_PENALTY = 0.18
FAMILY_VARIANT_NOISE_TOKENS = {
    "natural",
    "normal",
    "clasico",
    "clasica",
    "plain",
    "light",
    "zero",
    "fat",
    "free",
    "low",
    "skimmed",
    "semi",
    "reduced",
    "desnatado",
    "desnatada",
    "semidesnatado",
    "semidesnatada",
    "entero",
    "entera",
    "al",
    "la",
    "de",
    "sin",
    "con",
    "azucar",
    "sugar",
    "added",
    "proteico",
    "proteina",
    "fresh",
}


def _canonical_food_sort_key(
    food: dict[str, Any],
    *,
    fallback_code: str = "",
) -> tuple[str, str, str, str]:
    normalized_code = str(food.get("code") or fallback_code or "").strip().lower()
    normalized_internal_code = str(food.get("internal_code") or "").strip().lower()
    normalized_name = normalize_food_name(
        str(food.get("display_name") or food.get("name") or food.get("original_name") or normalized_code)
    ).strip()
    category = normalize_food_name(str(food.get("category") or "")).strip()
    return (
        normalized_internal_code or normalized_code,
        normalized_code,
        normalized_name,
        category,
    )


def iter_canonical_food_items(
    food_lookup: dict[str, dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    return sorted(
        food_lookup.items(),
        key=lambda item: _canonical_food_sort_key(item[1], fallback_code=item[0]),
    )


def iter_canonical_foods(
    food_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [food for _code, food in iter_canonical_food_items(food_lookup)]
FOOD_FAMILY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("greek_yogurt", ("greek yogurt", "yogur griego", "yogurt griego")),
    ("yogurt", ("yogur", "yogurt", "skyr")),
    ("fresh_cheese", ("queso fresco batido", "queso fresco", "cottage", "quark")),
    ("milk", ("leche", "milk", "bebida vegetal")),
    ("egg_whites", ("claras de huevo", "egg whites", "claras")),
    ("eggs", ("huevo", "huevos", "egg", "eggs")),
    ("chicken", ("pechuga de pollo", "pollo", "chicken")),
    ("turkey", ("pechuga de pavo", "pavo", "turkey")),
    ("tuna", ("atun", "tuna")),
    ("salmon", ("salmon",)),
    ("rice_cake", ("tortitas de arroz", "rice cake", "rice cakes", "corn cake")),
    ("cornflakes", ("cornflakes", "copos de maiz")),
    ("cereal", ("cereal", "cereales", "granola", "muesli")),
    ("oats", ("avena", "oats", "rolled oats")),
    ("bread", ("pan integral", "pan tostado", "tostada", "tostadas", "bread", "toast", "pan")),
    ("wrap", ("wrap", "tortilla")),
    ("rice", ("arroz", "rice")),
    ("pasta", ("pasta", "macarron", "espagueti")),
    ("potato", ("patata", "potato", "boniato", "batata", "sweet potato")),
    ("banana", ("platano", "banana", "banano")),
    ("apple", ("manzana", "apple")),
    ("mixed_vegetables", ("verduras", "vegetables", "ensalada", "salad")),
    ("olive_oil", ("aceite de oliva", "olive oil", "aceite", "oil")),
    ("avocado", ("aguacate", "avocado")),
    ("mixed_nuts", ("frutos secos", "mixed nuts", "nuts", "almendra", "walnut")),
    ("peanut_butter", ("crema de cacahuete", "mantequilla de cacahuete", "peanut butter")),
    ("jam", ("mermelada", "jam")),
)
STRUCTURE_BUCKET_PATTERNS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "protein": (
        ("dairy", ("greek yogurt", "yogur", "yogurt", "skyr", "queso fresco", "milk", "leche")),
        ("egg", ("egg whites", "claras", "egg", "eggs", "huevo", "huevos")),
        ("poultry", ("chicken", "pollo", "turkey", "pavo")),
        ("fish", ("tuna", "atun", "salmon", "fish")),
    ),
    "carb": (
        ("wrap", ("wrap", "tortilla")),
        ("bread", ("bread", "toast", "pan", "tostada")),
        ("cereal", ("cornflakes", "cereal", "granola", "muesli")),
        ("oats", ("oats", "avena")),
        ("rice_cake", ("rice cake", "rice cakes", "tortitas de arroz", "corn cake")),
        ("rice", ("rice", "arroz")),
        ("pasta", ("pasta", "macarron", "espagueti")),
        ("potato", ("potato", "patata", "boniato", "batata")),
        ("fruit", ("banana", "platano", "manzana", "apple", "fruta", "fruit")),
    ),
    "fat": (
        ("spread", ("peanut butter", "crema de cacahuete", "mantequilla de cacahuete")),
        ("avocado", ("avocado", "aguacate")),
        ("oil", ("olive oil", "aceite", "oil")),
        ("nuts", ("nuts", "frutos secos", "almendra", "walnut", "cacahuete")),
    ),
}


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


def _normalize_food_like_text(food_or_code: dict[str, Any] | str) -> str:
    if isinstance(food_or_code, dict):
        return get_food_text_signature(food_or_code)
    return normalize_food_name(str(food_or_code or "").replace("_", " "))


def _strip_variant_noise_tokens(normalized_text: str) -> str:
    tokens = [
        token
        for token in normalized_text.split()
        if token
        and token not in FAMILY_VARIANT_NOISE_TOKENS
        and not token.isdigit()
    ]
    return " ".join(tokens).strip()


def _match_family_pattern(normalized_text: str) -> str | None:
    for family_name, patterns in FOOD_FAMILY_PATTERNS:
        if any(pattern in normalized_text for pattern in patterns):
            return family_name
    return None


def get_food_family_signature(
    food_or_code: dict[str, Any] | str,
    *,
    role: str | None = None,
) -> str:
    normalized_text = _normalize_food_like_text(food_or_code)
    if not normalized_text:
        return f"{role or 'food'}:unknown"

    family_name = _match_family_pattern(normalized_text)
    if not family_name:
        stripped_text = _strip_variant_noise_tokens(normalized_text)
        family_name = " ".join(stripped_text.split()[:3]).strip() or normalized_text

    if role:
        family_role = role
    elif isinstance(food_or_code, dict):
        family_role = derive_functional_group(food_or_code)
    else:
        family_role = "food"

    return f"{family_role}:{family_name}"


def get_food_structure_bucket(
    food_or_code: dict[str, Any] | str,
    *,
    role: str,
) -> str:
    normalized_text = _normalize_food_like_text(food_or_code)
    for bucket_name, patterns in STRUCTURE_BUCKET_PATTERNS.get(role, ()):
        if any(pattern in normalized_text for pattern in patterns):
            return bucket_name

    if isinstance(food_or_code, dict):
        functional_group = derive_functional_group(food_or_code)
        if role == "protein" and functional_group == "dairy":
            return "dairy"
        if role == "carb" and functional_group == "fruit":
            return "fruit"
        if role == "fat" and functional_group == "fat":
            return "fat"

    return role


def get_meal_structure_signature(
    *,
    selected_role_codes: dict[str, str],
    support_food_specs: list[dict[str, Any]],
) -> str:
    protein_bucket = get_food_structure_bucket(selected_role_codes.get("protein", ""), role="protein")
    carb_bucket = get_food_structure_bucket(selected_role_codes.get("carb", ""), role="carb")
    fat_bucket = get_food_structure_bucket(selected_role_codes.get("fat", ""), role="fat")
    support_signatures = sorted({
        get_food_family_signature(
            str(support_food.get("food_code") or "").strip(),
            role=str(support_food.get("role") or "support").strip().lower(),
        )
        for support_food in support_food_specs
        if str(support_food.get("food_code") or "").strip()
    })
    return f"P:{protein_bucket}|C:{carb_bucket}|F:{fat_bucket}|S:{','.join(support_signatures)}"


def _dedupe_codes_by_family(
    codes: list[str],
    *,
    food_lookup: dict[str, dict[str, Any]] | None,
    role: str,
) -> list[str]:
    deduped_codes: list[str] = []
    seen_signatures: set[str] = set()

    for code in codes:
        food_entry = food_lookup.get(code) if food_lookup else code
        family_signature = get_food_family_signature(food_entry, role=role)
        if family_signature in seen_signatures:
            continue
        seen_signatures.add(family_signature)
        deduped_codes.append(code)

    return deduped_codes


def _dedupe_foods_by_family(
    foods: list[dict[str, Any]],
    *,
    role: str,
) -> list[dict[str, Any]]:
    deduped_foods: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    for food in foods:
        family_signature = get_food_family_signature(food, role=role)
        if family_signature in seen_signatures:
            continue
        seen_signatures.add(family_signature)
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

        constrained_candidate_codes[role] = _dedupe_codes_by_family(
            filtered_codes,
            food_lookup=food_lookup,
            role=role,
        )

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
    seen_option_signatures: set[tuple[tuple[str, str], ...]] = set()

    for support_option in support_options:
        if any(
            support_food["food_code"] not in food_lookup or support_food["food_code"] in excluded_codes
            for support_food in support_option
        ):
            continue

        normalized_option = [
            {
                "role": support_food["role"],
                "food_code": support_food["food_code"],
                "quantity": float(support_food["quantity"]),
            }
            for support_food in support_option
        ]
        option_signature = tuple(sorted(
            (
                str(support_food["role"]),
                get_food_family_signature(
                    food_lookup[support_food["food_code"]],
                    role=str(support_food["role"]),
                ),
            )
            for support_food in normalized_option
        ))
        if option_signature in seen_option_signatures:
            continue
        seen_option_signatures.add(option_signature)
        filtered_support_options.append(normalized_option)

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

    # Algunos alimentos externos quedan clasificados como "main/late" aunque
    # su texto describe claramente un desayuno dulce (ej. "corn cereal").
    # Corregimos el slot sin eliminar los slots ya guardados.
    if is_sweet_breakfast_carb(food) or is_breakfast_only_protein(food):
        slots.add("early")
    if is_breakfast_fat(food):
        slots.add("early")

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

    if is_sweet_breakfast_carb(food):
        return False

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


def is_concentrated_fruit_candidate(food: dict[str, Any]) -> bool:
    if derive_functional_group(food) != "fruit":
        return False

    if _food_has_any_token(food, CONCENTRATED_FRUIT_TOKENS):
        return True

    reference_amount = max(float(food.get("reference_amount") or 1.0), 1.0)
    carb_density = max(float(food.get("carb_grams") or 0.0), 0.0) / reference_amount
    calorie_density = max(float(food.get("calories") or 0.0), 0.0) / reference_amount
    return (
        carb_density >= CONCENTRATED_FRUIT_CARB_DENSITY_THRESHOLD
        and calorie_density >= CONCENTRATED_FRUIT_CALORIE_DENSITY_THRESHOLD
    )


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
            if derive_functional_group(food) == "fruit" and is_concentrated_fruit_candidate(food):
                score -= CONCENTRATED_FRUIT_MAIN_CARB_PENALTY
                if meal_role == "breakfast":
                    score -= BREAKFAST_CONCENTRATED_FRUIT_MAIN_CARB_EXTRA_PENALTY
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
        key=lambda code: (
            -get_food_role_fit_score(
                food_lookup[code],
                role=role,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            ),
            get_food_family_signature(food_lookup[code], role=role),
            _canonical_food_sort_key(food_lookup[code], fallback_code=code),
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
        if is_concentrated_fruit_candidate(food):
            score -= CONCENTRATED_FRUIT_SUPPORT_PENALTY
            if meal_slot == "early" or meal_role == "breakfast":
                score -= BREAKFAST_CONCENTRATED_FRUIT_SUPPORT_EXTRA_PENALTY
    elif support_role == "dairy":
        score += protein_density * 1.1
        if meal_slot == "early":
            score += 0.35
        score -= fat_density * (14.0 if meal_role in LOW_FAT_MEAL_ROLES else 9.0)

    if training_focus and meal_role in LOW_FAT_MEAL_ROLES and fat_density <= 0.02:
        score += 0.08

    return score


def _calcular_aporte_estimado(food: dict[str, Any], quantity: float) -> dict[str, float]:
    reference_amount = max(float(food.get("reference_amount") or 1.0), 1.0)
    scale = float(quantity) / reference_amount
    protein = max(0.0, float(food.get("protein_grams") or 0.0) * scale)
    fat = max(0.0, float(food.get("fat_grams") or 0.0) * scale)
    carbs = max(0.0, float(food.get("carb_grams") or 0.0) * scale)
    return {
        "protein_grams": protein,
        "fat_grams": fat,
        "carb_grams": carbs,
        "calories": (protein * 4.0) + (fat * 9.0) + (carbs * 4.0),
    }


def _calcular_cantidad_por_objetivo_macro(
    food: dict[str, Any],
    *,
    macro_key: str,
    objetivo_macro: float,
    fallback: float,
) -> float:
    reference_amount = max(float(food.get("reference_amount") or 1.0), 1.0)
    macro_por_referencia = max(float(food.get(macro_key) or 0.0), 0.0)
    if macro_por_referencia <= 0:
        return fallback

    densidad = macro_por_referencia / reference_amount
    if densidad <= 0:
        return fallback

    return objetivo_macro / densidad


def construir_cantidad_soporte_razonable(food: dict[str, Any], *, support_role: str) -> float:
    """Calcula una racion de soporte visible y moderada para el alimento dado.

    La idea no es reutilizar ciegamente el `default_quantity`, porque en muchos
    catálogos externos esa cifra representa una ración genérica del alimento,
    no una porción razonable como acompañamiento. En su lugar:
      - fruta: apunta a un aporte moderado de hidratos;
      - lácteo: apunta a un aporte moderado de proteína;
      - verdura: prioriza volumen culinario.
    """
    unit = str(food.get("reference_unit") or "unidad").strip().lower()
    default_quantity = max(float(food.get("default_quantity") or 0.0), 0.0)
    max_quantity = max(float(food.get("max_quantity") or 0.0), 0.0)

    minimos = {
        "fruit": {"g": 10.0, "ml": 80.0, "unidad": 0.5},
        "dairy": {"g": 80.0, "ml": 150.0, "unidad": 1.0},
        "vegetable": {"g": 60.0, "ml": 80.0, "unidad": 1.0},
    }
    maximos = {
        "fruit": {"g": 120.0, "ml": 250.0, "unidad": 1.5},
        "dairy": {"g": 180.0, "ml": 300.0, "unidad": 1.5},
        "vegetable": {"g": 150.0, "ml": 250.0, "unidad": 1.5},
    }

    if support_role == "fruit":
        fallback = default_quantity or (1.0 if unit == "unidad" else 80.0)
        quantity = _calcular_cantidad_por_objetivo_macro(
            food,
            macro_key="carb_grams",
            objetivo_macro=8.0,
            fallback=fallback,
        )
    elif support_role == "dairy":
        fallback = default_quantity or (1.0 if unit == "unidad" else 125.0)
        quantity = _calcular_cantidad_por_objetivo_macro(
            food,
            macro_key="protein_grams",
            objetivo_macro=10.0,
            fallback=fallback,
        )
    else:
        quantity = default_quantity or (1.0 if unit == "unidad" else 100.0)

    minimo = minimos.get(support_role, {}).get(unit, 0.0)
    maximo = maximos.get(support_role, {}).get(unit, 0.0)

    if quantity <= 0:
        quantity = minimo
    if minimo > 0:
        quantity = max(quantity, minimo)
    if maximo > 0:
        quantity = min(quantity, maximo)
    if max_quantity > 0:
        quantity = min(quantity, max_quantity)

    return max(quantity, 0.0)


def es_soporte_significativo(
    food: dict[str, Any],
    *,
    support_role: str,
    quantity: float,
) -> bool:
    """Filtra soportes residuales que no aportan valor nutricional ni culinario."""
    if quantity <= 0:
        return False
    if quantity + 1e-6 < FOOD_OMIT_THRESHOLD.get(str(food.get("reference_unit") or "").strip().lower(), 0.0):
        return False

    unit = str(food.get("reference_unit") or "unidad").strip().lower()
    aporte = _calcular_aporte_estimado(food, quantity)
    tiene_datos_macro = any(float(food.get(macro_key) or 0.0) > 0 for macro_key in CORE_MACRO_KEYS)

    if support_role == "vegetable":
        if unit in {"g", "ml"}:
            return quantity >= 60.0 or aporte["calories"] >= 15.0
        return quantity >= 1.0

    if support_role == "fruit":
        if unit == "unidad":
            return quantity >= 0.5
        if not tiene_datos_macro:
            return quantity >= 40.0
        return aporte["carb_grams"] >= 8.0 or aporte["calories"] >= 30.0

    if support_role == "dairy":
        if unit == "unidad":
            return quantity >= 1.0
        if not tiene_datos_macro:
            return quantity >= 80.0
        return aporte["protein_grams"] >= 6.0 or aporte["calories"] >= 45.0

    return True


def get_support_candidate_foods(
    food_lookup: dict[str, dict[str, Any]],
    *,
    support_role: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    expand_candidate_pool: bool = False,
) -> list[dict[str, Any]]:
    ranked_candidates = sorted(
        (
            food
            for food in iter_canonical_foods(food_lookup)
            if is_support_food_allowed(
                food,
                support_role=support_role,
                meal_slot=meal_slot,
                meal_role=meal_role,
            )
        ),
        key=lambda food: (
            -get_support_food_fit_score(
                food,
                support_role=support_role,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            ),
            get_food_family_signature(food, role=support_role),
            _canonical_food_sort_key(food),
        ),
    )
    deduped_candidates = _dedupe_foods_by_code(ranked_candidates)
    deduped_candidates = _dedupe_foods_by_family(
        deduped_candidates,
        role=support_role,
    )
    candidate_limit = MAX_SUPPORT_CANDIDATES_PER_ROLE
    if expand_candidate_pool:
        candidate_limit *= 2 if meal_slot != "early" else 3
    return deduped_candidates[:candidate_limit]


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
        "family_counts": {},
        "main_pair_counts": {},
        "main_family_pair_counts": {},
        "structure_counts": {},
        "template_counts": {},
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
        family_signature = get_food_family_signature(food_code, role=role)
        family_counts = daily_food_usage["family_counts"].setdefault(role, {})
        family_counts[family_signature] = family_counts.get(family_signature, 0) + 1

    for role, food_code in selected_role_codes.items():
        add_usage(food_code, role)

    for support_food in meal_plan.get("support_food_specs", []):
        add_usage(support_food.get("food_code"), support_food.get("role", "support"))

    if protein_code and carb_code:
        pair_key = f"{protein_code}::{carb_code}"
        daily_food_usage["main_pair_counts"][pair_key] = daily_food_usage["main_pair_counts"].get(pair_key, 0) + 1
        protein_family = get_food_family_signature(protein_code, role="protein")
        carb_family = get_food_family_signature(carb_code, role="carb")
        family_pair_key = f"{protein_family}::{carb_family}"
        daily_food_usage["main_family_pair_counts"][family_pair_key] = (
            daily_food_usage["main_family_pair_counts"].get(family_pair_key, 0) + 1
        )

    structure_signature = get_meal_structure_signature(
        selected_role_codes=selected_role_codes,
        support_food_specs=meal_plan.get("support_food_specs", []),
    )
    daily_food_usage["structure_counts"][structure_signature] = (
        daily_food_usage["structure_counts"].get(structure_signature, 0) + 1
    )

    template_id = str(meal_plan.get("applied_template_id") or "").strip()
    if template_id:
        daily_food_usage["template_counts"][template_id] = daily_food_usage["template_counts"].get(template_id, 0) + 1


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


def apply_family_repeat_penalty(
    food: dict[str, Any] | str,
    *,
    role: str,
    daily_food_usage: dict | None,
) -> float:
    if not daily_food_usage:
        return 0.0

    family_signature = get_food_family_signature(food, role=role)
    family_count = int(daily_food_usage.get("family_counts", {}).get(role, {}).get(family_signature, 0))
    if family_count <= 0:
        return 0.0

    return FAMILY_REPEAT_PENALTY_BY_ROLE.get(role, 0.1) * family_count


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


def apply_main_family_pair_repeat_penalty(
    role_foods: dict[str, dict],
    *,
    daily_food_usage: dict | None,
) -> float:
    if not daily_food_usage:
        return 0.0

    protein_family = get_food_family_signature(role_foods["protein"], role="protein")
    carb_family = get_food_family_signature(role_foods["carb"], role="carb")
    pair_key = f"{protein_family}::{carb_family}"
    pair_count = int(daily_food_usage.get("main_family_pair_counts", {}).get(pair_key, 0))
    return pair_count * REPEATED_MAIN_FAMILY_PAIR_PENALTY


def apply_meal_structure_repeat_penalty(
    *,
    role_foods: dict[str, dict],
    support_foods: list[dict[str, Any]],
    daily_food_usage: dict | None,
) -> float:
    if not daily_food_usage:
        return 0.0

    structure_signature = get_meal_structure_signature(
        selected_role_codes={
            role: str(food.get("code") or "").strip()
            for role, food in role_foods.items()
        },
        support_food_specs=[
            {
                "role": str(food.get("role") or "support"),
                "food_code": str(food.get("code") or food.get("food_code") or "").strip(),
            }
            for food in support_foods
            if str(food.get("code") or food.get("food_code") or "").strip()
        ],
    )
    structure_count = int(daily_food_usage.get("structure_counts", {}).get(structure_signature, 0))
    return structure_count * REPEATED_MEAL_STRUCTURE_PENALTY


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
        for code, f_data in iter_canonical_food_items(food_lookup):
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

    protein_codes = _dedupe_codes_by_family(
        protein_codes,
        food_lookup=food_lookup,
        role="protein",
    )
    carb_codes = _dedupe_codes_by_family(
        carb_codes,
        food_lookup=food_lookup,
        role="carb",
    )
    fat_codes = _dedupe_codes_by_family(
        fat_codes,
        food_lookup=food_lookup,
        role="fat",
    )

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
    expand_candidate_pool: bool = False,
) -> list[list[dict]]:
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    support_options: list[list[dict]] = [[]]
    seen_keys: set[tuple[tuple[str, float], ...]] = {tuple()}

    def add_support_option(option: list[dict[str, Any]]) -> None:
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
                expand_candidate_pool=expand_candidate_pool,
            )
            if ranked_foods:
                return ranked_foods

        if not food_lookup:
            return [{"code": code} for code in fallback_codes]

        return [food_lookup[code] for code in fallback_codes if code in food_lookup]

    roles_soporte: list[tuple[str, list[str]]] = []
    if meal_slot != "early":
        roles_soporte.append(("vegetable", ["mixed_vegetables"]))
    if meal_slot == "early" or meal_role in LOW_FAT_MEAL_ROLES:
        roles_soporte.append(("fruit", ["banana"]))
    if meal_slot == "early":
        roles_soporte.append(("dairy", ["greek_yogurt"]))

    support_candidates_by_role: dict[str, list[dict[str, Any]]] = {}

    for support_role, fallback_codes in roles_soporte:
        support_candidates = iter_support_foods(support_role, fallback_codes)
        support_candidates_by_role[support_role] = support_candidates
        for support_food in support_candidates:
            quantity = construir_cantidad_soporte_razonable(
                support_food,
                support_role=support_role,
            )
            if not es_soporte_significativo(
                support_food,
                support_role=support_role,
                quantity=quantity,
            ):
                continue
            add_support_option([{
                "role": support_role,
                "food_code": support_food["code"],
                "quantity": float(quantity),
            }])

    if expand_candidate_pool and len(roles_soporte) >= 2:
        for role_index, (primary_role, _fallback_codes) in enumerate(roles_soporte):
            primary_candidates = support_candidates_by_role.get(primary_role, [])[:2]
            for secondary_role, _secondary_fallback in roles_soporte[role_index + 1:]:
                secondary_candidates = support_candidates_by_role.get(secondary_role, [])[:2]
                for primary_food in primary_candidates:
                    primary_quantity = construir_cantidad_soporte_razonable(
                        primary_food,
                        support_role=primary_role,
                    )
                    if not es_soporte_significativo(
                        primary_food,
                        support_role=primary_role,
                        quantity=primary_quantity,
                    ):
                        continue
                    for secondary_food in secondary_candidates:
                        if primary_food["code"] == secondary_food["code"]:
                            continue
                        secondary_quantity = construir_cantidad_soporte_razonable(
                            secondary_food,
                            support_role=secondary_role,
                        )
                        if not es_soporte_significativo(
                            secondary_food,
                            support_role=secondary_role,
                            quantity=secondary_quantity,
                        ):
                            continue
                        add_support_option([
                            {
                                "role": primary_role,
                                "food_code": primary_food["code"],
                                "quantity": float(primary_quantity),
                            },
                            {
                                "role": secondary_role,
                                "food_code": secondary_food["code"],
                                "quantity": float(secondary_quantity),
                            },
                        ])

    return support_options
