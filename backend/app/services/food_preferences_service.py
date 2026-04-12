"""Reusable helpers for user food preferences, restrictions, and compatibility."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.utils.normalization import build_food_aliases, normalize_food_name

COMMON_DIETARY_RESTRICTIONS = (
    "vegetariano",
    "vegano",
    "sin_lactosa",
    "sin_gluten",
)
DIETARY_RESTRICTION_ALIASES = {
    "vegetariano": "vegetariano",
    "vegetarian": "vegetariano",
    "vegano": "vegano",
    "vegan": "vegano",
    "sin lactosa": "sin_lactosa",
    "sin_lactosa": "sin_lactosa",
    "lactose free": "sin_lactosa",
    "lactose_free": "sin_lactosa",
    "sin gluten": "sin_gluten",
    "sin_gluten": "sin_gluten",
    "gluten free": "sin_gluten",
    "gluten_free": "sin_gluten",
}
ALLERGY_ALIASES = {
    "frutos secos": "frutos_secos",
    "frutos_secos": "frutos_secos",
    "nuts": "frutos_secos",
    "nut": "frutos_secos",
    "marisco": "marisco",
    "shellfish": "marisco",
    "huevo": "huevo",
    "egg": "huevo",
    "eggs": "huevo",
    "lacteos": "lacteos",
    "lacteo": "lacteos",
    "dairy": "lacteos",
    "milk": "lacteos",
    "gluten": "gluten",
    "pescado": "pescado",
    "fish": "pescado",
}
INTERNAL_FOOD_COMPATIBILITY: dict[str, dict[str, list[str]]] = {
    "chicken_breast": {"dietary_tags": ["sin_lactosa", "sin_gluten"], "allergen_tags": []},
    "turkey_breast": {"dietary_tags": ["sin_lactosa", "sin_gluten"], "allergen_tags": []},
    "eggs": {"dietary_tags": ["vegetariano", "sin_lactosa", "sin_gluten"], "allergen_tags": ["huevo"]},
    "egg_whites": {"dietary_tags": ["vegetariano", "sin_lactosa", "sin_gluten"], "allergen_tags": ["huevo"]},
    "tuna": {"dietary_tags": ["sin_lactosa", "sin_gluten"], "allergen_tags": ["pescado"]},
    "greek_yogurt": {"dietary_tags": ["vegetariano", "sin_gluten"], "allergen_tags": ["lacteos"]},
    "semi_skimmed_milk": {"dietary_tags": ["vegetariano", "sin_gluten"], "allergen_tags": ["lacteos"]},
    "rice": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": [],
    },
    "pasta": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa"],
        "allergen_tags": ["gluten"],
    },
    "oats": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa"],
        "allergen_tags": ["gluten"],
    },
    "whole_wheat_bread": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa"],
        "allergen_tags": ["gluten"],
    },
    "potato": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": [],
    },
    "olive_oil": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": [],
    },
    "avocado": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": [],
    },
    "mixed_nuts": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": ["frutos_secos"],
    },
    "banana": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": [],
    },
    "mixed_vegetables": {
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": [],
    },
}
MEAT_TOKENS = ("chicken", "pollo", "turkey", "pavo", "beef", "carne", "pork", "cerdo", "ham", "jamon")
FISH_TOKENS = ("tuna", "atun", "fish", "salmon", "sardine", "sardina", "cod", "merluza")
SHELLFISH_TOKENS = ("shrimp", "prawn", "gamba", "langostino", "shellfish", "marisco")
EGG_TOKENS = ("egg", "eggs", "huevo", "huevos", "claras")
DAIRY_TOKENS = ("milk", "leche", "yogurt", "yogur", "queso", "cheese", "lacteo", "lacteos")
GLUTEN_TOKENS = ("bread", "pan", "pasta", "wheat", "trigo", "oats", "avena", "gluten")
NUT_TOKENS = ("nuts", "nut", "frutos secos", "fruto seco", "almendra", "nuez", "cacahuete")


class FoodPreferenceConflictError(ValueError):
    """Raised when user preferences leave too few compatible foods to build a diet."""


def normalize_food_label(value: str) -> str:
    return normalize_food_name(value)


def _normalize_list(values: list[str] | None) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()

    for value in values or []:
        normalized_value = normalize_food_label(str(value))
        if not normalized_value or normalized_value in seen_values:
            continue

        normalized_values.append(normalized_value)
        seen_values.add(normalized_value)

    return normalized_values


def _normalize_with_alias_map(values: list[str] | None, alias_map: dict[str, str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()

    for value in values or []:
        normalized_value = normalize_food_label(str(value))
        canonical_value = alias_map.get(normalized_value)
        if not canonical_value or canonical_value in seen_values:
            continue

        normalized_values.append(canonical_value)
        seen_values.add(canonical_value)

    return normalized_values


def sanitize_user_food_preferences(payload: Any) -> dict[str, list[str]]:
    if hasattr(payload, "model_dump"):
        raw_payload = payload.model_dump(exclude_unset=True)
    else:
        raw_payload = dict(payload or {})

    return {
        "preferred_foods": _normalize_list(raw_payload.get("preferred_foods")),
        "disliked_foods": _normalize_list(raw_payload.get("disliked_foods")),
        "dietary_restrictions": _normalize_with_alias_map(
            raw_payload.get("dietary_restrictions"),
            DIETARY_RESTRICTION_ALIASES,
        ),
        "allergies": _normalize_list(raw_payload.get("allergies")),
    }


def build_user_food_preferences_profile(user: Any) -> dict[str, Any]:
    if hasattr(user, "model_dump"):
        user_data = user.model_dump()
    else:
        user_data = dict(user or {})

    serialized_preferences = sanitize_user_food_preferences(
        user_data.get("food_preferences")
        or {
            "preferred_foods": user_data.get("preferred_foods") or user_data.get("preferences") or [],
            "disliked_foods": user_data.get("disliked_foods") or [],
            "dietary_restrictions": user_data.get("dietary_restrictions") or user_data.get("restrictions") or [],
            "allergies": user_data.get("allergies") or [],
        }
    )
    return {
        **serialized_preferences,
        "normalized_preferred_foods": set(serialized_preferences["preferred_foods"]),
        "normalized_disliked_foods": set(serialized_preferences["disliked_foods"]),
        "dietary_restriction_set": set(serialized_preferences["dietary_restrictions"]),
        "allergy_set": set(serialized_preferences["allergies"]),
        "allergy_tag_set": {
            ALLERGY_ALIASES[allergy]
            for allergy in serialized_preferences["allergies"]
            if allergy in ALLERGY_ALIASES
        },
        "has_preferences": any(serialized_preferences.values()),
        "warnings": [],
    }


def _food_text_tokens(food: dict[str, Any]) -> str:
    return " ".join(
        value
        for value in (
            normalize_food_label(food.get("name", "")),
            normalize_food_label(food.get("display_name", "")),
            normalize_food_label(food.get("original_name", "")),
            normalize_food_label(str(food.get("code", "")).replace("_", " ")),
            normalize_food_label(str(food.get("internal_code", "")).replace("_", " ")),
            normalize_food_label(food.get("category", "")),
        )
        if value
    )


def _contains_any_token(text: str, tokens: tuple[str, ...]) -> bool:
    return any(normalize_food_label(token) in text for token in tokens)


def _derive_food_compatibility_from_heuristics(food: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    text = _food_text_tokens(food)
    source = str(food.get("source") or "")
    internal_code = str(food.get("internal_code") or "")
    category = normalize_food_label(food.get("category", ""))

    contains_meat = _contains_any_token(text, MEAT_TOKENS)
    contains_fish = _contains_any_token(text, FISH_TOKENS)
    contains_shellfish = _contains_any_token(text, SHELLFISH_TOKENS)
    contains_egg = _contains_any_token(text, EGG_TOKENS)
    contains_dairy = category == "lacteos" or _contains_any_token(text, DAIRY_TOKENS)
    contains_gluten = _contains_any_token(text, GLUTEN_TOKENS)
    contains_nuts = _contains_any_token(text, NUT_TOKENS)
    plant_based = not any((contains_meat, contains_fish, contains_shellfish, contains_egg, contains_dairy))

    dietary_tags: set[str] = set()
    allergen_tags: set[str] = set()
    compatibility_notes: list[str] = []

    if not contains_dairy:
        dietary_tags.add("sin_lactosa")
    if not contains_gluten:
        dietary_tags.add("sin_gluten")
    if not any((contains_meat, contains_fish, contains_shellfish)):
        dietary_tags.add("vegetariano")
    if plant_based:
        dietary_tags.add("vegano")

    if contains_nuts:
        allergen_tags.add("frutos_secos")
    if contains_shellfish:
        allergen_tags.add("marisco")
    if contains_egg:
        allergen_tags.add("huevo")
    if contains_dairy:
        allergen_tags.add("lacteos")
    if contains_gluten:
        allergen_tags.add("gluten")
    if contains_fish:
        allergen_tags.add("pescado")

    if source in {"spoonacular", "local_cache"} and not internal_code:
        compatibility_notes.append(
            "Compatibilidad dietetica derivada con heuristicas basicas por nombre y categoria."
        )

    return sorted(dietary_tags), sorted(allergen_tags), compatibility_notes


def annotate_food_compatibility(food: dict[str, Any]) -> dict[str, Any]:
    annotated_food = deepcopy(food)
    food_key = str(annotated_food.get("internal_code") or annotated_food.get("code") or "")
    mapped_compatibility = INTERNAL_FOOD_COMPATIBILITY.get(food_key, {})
    heuristic_dietary_tags, heuristic_allergen_tags, heuristic_notes = _derive_food_compatibility_from_heuristics(
        annotated_food
    )

    dietary_tags = sorted(
        set(_normalize_with_alias_map(annotated_food.get("dietary_tags"), DIETARY_RESTRICTION_ALIASES))
        | set(mapped_compatibility.get("dietary_tags", []))
        | set(heuristic_dietary_tags)
    )
    allergen_tags = sorted(
        set(_normalize_with_alias_map(annotated_food.get("allergen_tags"), ALLERGY_ALIASES))
        | set(mapped_compatibility.get("allergen_tags", []))
        | set(heuristic_allergen_tags)
    )
    compatibility_notes = list(dict.fromkeys((annotated_food.get("compatibility_notes") or []) + heuristic_notes))

    annotated_food["dietary_tags"] = dietary_tags
    annotated_food["allergen_tags"] = allergen_tags
    annotated_food["compatibility_notes"] = compatibility_notes
    annotated_food["preference_labels"] = build_food_aliases(
        annotated_food.get("name", ""),
        annotated_food.get("display_name", ""),
        annotated_food.get("original_name", ""),
        str(annotated_food.get("code", "")).replace("_", " "),
        str(annotated_food.get("internal_code", "")).replace("_", " "),
        *(annotated_food.get("aliases") or []),
    )
    return annotated_food


def _matches_food_label(food: dict[str, Any], label: str) -> bool:
    normalized_label = normalize_food_label(label)
    if not normalized_label:
        return False

    for candidate_label in food.get("preference_labels") or []:
        if normalized_label == candidate_label:
            return True
        if len(normalized_label) >= 4 and normalized_label in candidate_label:
            return True
        if len(candidate_label) >= 4 and candidate_label in normalized_label:
            return True

    return False


def _count_preferred_matches(food: dict[str, Any], profile: dict[str, Any]) -> int:
    return sum(
        1
        for preferred_food in profile["normalized_preferred_foods"]
        if _matches_food_label(food, preferred_food)
    )


def is_food_allowed_for_user(food: dict[str, Any], profile: dict[str, Any]) -> tuple[bool, list[str]]:
    annotated_food = annotate_food_compatibility(food)
    reasons: list[str] = []

    for disliked_food in profile["normalized_disliked_foods"]:
        if _matches_food_label(annotated_food, disliked_food):
            reasons.append(f"marcado como no deseado: {disliked_food}")

    for allergy in profile["allergy_set"]:
        if _matches_food_label(annotated_food, allergy):
            reasons.append(f"marcado como alergia o exclusion sensible: {allergy}")
            continue

    for allergy_tag in profile.get("allergy_tag_set", set()):
        if allergy_tag in annotated_food.get("allergen_tags", []):
            reasons.append(f"incompatible con alergia o intolerancia: {allergy_tag}")

    for restriction in profile["dietary_restriction_set"]:
        if restriction not in annotated_food.get("dietary_tags", []):
            reasons.append(f"incompatible con restriccion dietetica: {restriction}")

    return not reasons, reasons


def filter_allowed_foods(foods: list[dict[str, Any]], profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed_foods: list[dict[str, Any]] = []
    blocked_foods: list[dict[str, Any]] = []

    for food in foods:
        annotated_food = annotate_food_compatibility(food)
        is_allowed, reasons = is_food_allowed_for_user(annotated_food, profile)
        if is_allowed:
            allowed_foods.append(annotated_food)
            continue

        blocked_foods.append(
            {
                "food_code": annotated_food.get("code"),
                "name": annotated_food.get("name"),
                "reasons": reasons,
            }
        )

    return allowed_foods, blocked_foods


def prioritize_preferred_foods(foods: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    indexed_foods = list(enumerate(foods))
    prioritized_foods = sorted(
        indexed_foods,
        key=lambda item: (
            -_count_preferred_matches(item[1], profile),
            item[0],
        ),
    )
    return [food for _, food in prioritized_foods]


def apply_user_food_preferences(foods: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    if not profile.get("has_preferences"):
        annotated_foods = [annotate_food_compatibility(food) for food in foods]
        return {
            "foods": annotated_foods,
            "blocked_foods": [],
            "preferred_matches": 0,
        }

    allowed_foods, blocked_foods = filter_allowed_foods(foods, profile)
    prioritized_foods = prioritize_preferred_foods(allowed_foods, profile)
    preferred_matches = sum(
        1
        for food in prioritized_foods
        if _count_preferred_matches(food, profile) > 0
    )
    return {
        "foods": prioritized_foods,
        "blocked_foods": blocked_foods,
        "preferred_matches": preferred_matches,
    }


def count_preferred_food_matches_in_meals(meals: list[dict[str, Any]], profile: dict[str, Any]) -> int:
    return sum(
        1
        for meal in meals
        for food in meal.get("foods", [])
        if _count_preferred_matches(annotate_food_compatibility(food), profile) > 0
    )
