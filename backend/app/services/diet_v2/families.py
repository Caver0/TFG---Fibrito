"""Canonical food families used by the diet generation v2 engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.food_group_service import derive_functional_group
from app.utils.normalization import normalize_food_name


@dataclass(frozen=True)
class FoodFamilyDefinition:
    id: str
    roles: frozenset[str]
    functional_groups: frozenset[str]
    codes: frozenset[str]
    tokens: tuple[str, ...]
    priority: int


FAMILY_DEFINITIONS: tuple[FoodFamilyDefinition, ...] = (
    FoodFamilyDefinition(
        id="dairy_high_protein",
        roles=frozenset({"protein", "dairy"}),
        functional_groups=frozenset({"protein", "dairy"}),
        codes=frozenset({"greek_yogurt"}),
        tokens=("greek yogurt", "yogur", "yogurt", "skyr", "queso fresco", "cottage", "quark"),
        priority=10,
    ),
    FoodFamilyDefinition(
        id="egg_proteins",
        roles=frozenset({"protein"}),
        functional_groups=frozenset({"protein"}),
        codes=frozenset({"eggs", "egg_whites"}),
        tokens=("egg", "eggs", "huevo", "huevos", "claras"),
        priority=11,
    ),
    FoodFamilyDefinition(
        id="lean_poultry",
        roles=frozenset({"protein"}),
        functional_groups=frozenset({"protein"}),
        codes=frozenset({"chicken_breast", "turkey_breast"}),
        tokens=("chicken", "pollo", "turkey", "pavo"),
        priority=12,
    ),
    FoodFamilyDefinition(
        id="lean_fish",
        roles=frozenset({"protein"}),
        functional_groups=frozenset({"protein"}),
        codes=frozenset({"tuna"}),
        tokens=("tuna", "atun", "fish", "salmon", "merluza", "bacalao"),
        priority=13,
    ),
    FoodFamilyDefinition(
        id="toast_breads",
        roles=frozenset({"carb"}),
        functional_groups=frozenset({"carb"}),
        codes=frozenset({"whole_wheat_bread"}),
        tokens=("pan", "bread", "toast", "tostada"),
        priority=20,
    ),
    FoodFamilyDefinition(
        id="oats_cereals",
        roles=frozenset({"carb"}),
        functional_groups=frozenset({"carb"}),
        codes=frozenset({"oats"}),
        tokens=("oats", "avena", "porridge"),
        priority=21,
    ),
    FoodFamilyDefinition(
        id="breakfast_cereals",
        roles=frozenset({"carb"}),
        functional_groups=frozenset({"carb"}),
        codes=frozenset({"cornflakes"}),
        tokens=("cornflakes", "cereal", "cereales", "granola", "muesli", "flakes"),
        priority=22,
    ),
    FoodFamilyDefinition(
        id="rice_starches",
        roles=frozenset({"carb"}),
        functional_groups=frozenset({"carb"}),
        codes=frozenset({"rice"}),
        tokens=("rice", "arroz"),
        priority=23,
    ),
    FoodFamilyDefinition(
        id="pasta_starches",
        roles=frozenset({"carb"}),
        functional_groups=frozenset({"carb"}),
        codes=frozenset({"pasta"}),
        tokens=("pasta", "macarron", "espagueti"),
        priority=24,
    ),
    FoodFamilyDefinition(
        id="potato_starches",
        roles=frozenset({"carb"}),
        functional_groups=frozenset({"carb"}),
        codes=frozenset({"potato"}),
        tokens=("potato", "patata", "boniato", "batata"),
        priority=25,
    ),
    FoodFamilyDefinition(
        id="wrap_breads",
        roles=frozenset({"carb"}),
        functional_groups=frozenset({"carb"}),
        codes=frozenset(),
        tokens=("wrap", "tortilla"),
        priority=26,
    ),
    FoodFamilyDefinition(
        id="fruit_carbs",
        roles=frozenset({"carb", "fruit"}),
        functional_groups=frozenset({"fruit", "carb"}),
        codes=frozenset({"banana"}),
        tokens=("banana", "platano", "manzana", "apple", "fruta", "fruit"),
        priority=27,
    ),
    FoodFamilyDefinition(
        id="cooking_fats",
        roles=frozenset({"fat"}),
        functional_groups=frozenset({"fat"}),
        codes=frozenset({"olive_oil"}),
        tokens=("aceite", "olive oil", "oil"),
        priority=30,
    ),
    FoodFamilyDefinition(
        id="avocado_fats",
        roles=frozenset({"fat"}),
        functional_groups=frozenset({"fat"}),
        codes=frozenset({"avocado"}),
        tokens=("aguacate", "avocado"),
        priority=31,
    ),
    FoodFamilyDefinition(
        id="nuts_and_fats",
        roles=frozenset({"fat"}),
        functional_groups=frozenset({"fat"}),
        codes=frozenset({"mixed_nuts"}),
        tokens=("nuts", "frutos secos", "almendra", "walnut", "peanut butter", "cacahuete"),
        priority=32,
    ),
    FoodFamilyDefinition(
        id="vegetable_sides",
        roles=frozenset({"vegetable"}),
        functional_groups=frozenset({"vegetable"}),
        codes=frozenset({"mixed_vegetables"}),
        tokens=("verdura", "vegetable", "vegetables", "ensalada", "salad", "tomate", "lechuga"),
        priority=40,
    ),
    FoodFamilyDefinition(
        id="dairy_supports",
        roles=frozenset({"dairy"}),
        functional_groups=frozenset({"dairy", "protein"}),
        codes=frozenset({"semi_skimmed_milk", "greek_yogurt"}),
        tokens=("milk", "leche", "yogur", "yogurt", "skyr"),
        priority=41,
    ),
)

_FAMILY_BY_ID = {family.id: family for family in FAMILY_DEFINITIONS}


def _food_terms(food_or_code: dict[str, Any] | str) -> set[str]:
    if isinstance(food_or_code, str):
        raw_values = (food_or_code, food_or_code.replace("_", " "))
    else:
        raw_values = (
            food_or_code.get("code"),
            str(food_or_code.get("code") or "").replace("_", " "),
            food_or_code.get("name"),
            food_or_code.get("display_name"),
            food_or_code.get("original_name"),
            food_or_code.get("category"),
            *(food_or_code.get("aliases") or []),
        )

    normalized_terms: set[str] = set()
    for raw_value in raw_values:
        normalized_value = normalize_food_name(str(raw_value or "")).strip()
        if normalized_value:
            normalized_terms.add(normalized_value)
    return normalized_terms


def get_family_definition(family_id: str) -> FoodFamilyDefinition | None:
    return _FAMILY_BY_ID.get(family_id)


def get_matching_family_ids(
    food_or_code: dict[str, Any] | str,
    *,
    role: str | None = None,
) -> tuple[str, ...]:
    normalized_terms = _food_terms(food_or_code)
    if isinstance(food_or_code, dict):
        food_code = str(food_or_code.get("code") or "").strip()
        functional_group = derive_functional_group(food_or_code)
    else:
        food_code = str(food_or_code or "").strip()
        functional_group = None

    matched_families: list[tuple[int, str]] = []
    for family in FAMILY_DEFINITIONS:
        if role and family.roles and role not in family.roles:
            continue
        if functional_group and family.functional_groups and functional_group not in family.functional_groups:
            continue
        if food_code and food_code in family.codes:
            matched_families.append((family.priority, family.id))
            continue
        if any(token in term for term in normalized_terms for token in family.tokens):
            matched_families.append((family.priority, family.id))

    matched_families.sort()
    return tuple(family_id for _priority, family_id in matched_families)


def get_primary_family_id(
    food_or_code: dict[str, Any] | str,
    *,
    role: str | None = None,
) -> str:
    matching_families = get_matching_family_ids(food_or_code, role=role)
    if matching_families:
        return matching_families[0]

    if isinstance(food_or_code, dict):
        fallback_role = role or derive_functional_group(food_or_code)
        fallback_label = next(iter(sorted(_food_terms(food_or_code))), "unknown")
        return f"{fallback_role}:{fallback_label}"

    fallback_role = role or "food"
    fallback_label = next(iter(sorted(_food_terms(food_or_code))), "unknown")
    return f"{fallback_role}:{fallback_label}"


def food_matches_allowed_families(
    food_or_code: dict[str, Any] | str,
    *,
    allowed_families: tuple[str, ...] | list[str] | set[str],
    role: str | None = None,
) -> bool:
    normalized_allowed_families = tuple(allowed_families)
    if not normalized_allowed_families:
        return True

    matching_families = set(get_matching_family_ids(food_or_code, role=role))
    return any(family_id in matching_families for family_id in normalized_allowed_families)


def summarize_plan_families(
    selected_role_codes: dict[str, str],
    support_food_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    role_families = {
        role: get_primary_family_id(food_code, role=role)
        for role, food_code in selected_role_codes.items()
        if str(food_code or "").strip()
    }
    support_families = [
        get_primary_family_id(
            str(support_food.get("food_code") or "").strip(),
            role=str(support_food.get("role") or "support").strip().lower(),
        )
        for support_food in support_food_specs
        if str(support_food.get("food_code") or "").strip()
    ]
    return {
        "role_families": role_families,
        "support_families": support_families,
    }
