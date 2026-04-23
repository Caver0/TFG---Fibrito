"""Capa ligera de coherencia culinaria para generacion y sustitucion."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.diet.candidates import (
    construir_cantidad_soporte_razonable,
    get_food_family_signature,
    get_meal_structure_signature,
    get_food_role_fit_score,
    get_support_food_fit_score,
    is_food_allowed_for_role_and_slot,
    is_support_food_allowed,
)
from app.services.diet.common import resolve_meal_context
from app.services.diet.constants import REPEATED_TEMPLATE_PENALTY
from app.services.diet.solver import build_exact_meal_solution
from app.services.food_catalog_service import _serialize_cached_food, get_internal_food_lookup
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import is_food_allowed_for_user
from app.utils.normalization import normalize_food_name

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FOOD_PAIRING_RULES_PATH = DATA_DIR / "food_pairing_rules.json"
MEAL_TEMPLATES_PATH = DATA_DIR / "meal_templates.json"
TEMPLATE_ALLOWED_SCORE_DELTA = 0.75
REGENERATION_TEMPLATE_ALLOWED_SCORE_DELTA = 1.6
PAIRING_ROLE_ORDER = ("protein", "carb", "fat")
KNOWN_SUPPORT_ROLES = {"fruit", "vegetable", "dairy"}
TAG_ALIAS_MAP = {
    "protein": {"protein", "lean_protein"},
    "vegetables": {"vegetables", "salad"},
    "healthy_fat": {"healthy_fat"},
    "milk": {"milk", "dairy"},
    "yogurt": {"yogurt", "dairy"},
    "spread": {"spread", "jam"},
    "jam": {"jam", "spread"},
}
TEMPLATE_ROLE_TO_CORE_ROLE = {
    "protein": "protein",
    "protein_fat": "protein",
    "carb": "carb",
    "fat": "fat",
    "liquid": "protein",
}
SOURCE_PRIORITY = {
    "internal_catalog": 0,
    "internal": 0,
    "local_cache": 1,
    "cache": 1,
    "spoonacular": 2,
}
STRUCTURE_SUPPORT_ROLES = {"fruit", "vegetable", "dairy", "jam", "spread", "sauce", "lean_protein", "healthy_fat", "bread"}
TEMPLATE_VARIETY_WINDOW_BY_SLOT = {
    "early": 1.35,
    "main": 0.85,
    "late": 0.85,
}
COHERENCE_VARIETY_WINDOW_BY_SLOT = {
    "early": 1.15,
    "main": 0.75,
    "late": 0.75,
}


@lru_cache(maxsize=1)
def load_food_pairing_rules() -> list[dict[str, Any]]:
    with FOOD_PAIRING_RULES_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return list(payload.get("rules", []))


@lru_cache(maxsize=1)
def load_meal_templates() -> list[dict[str, Any]]:
    with MEAL_TEMPLATES_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return list(payload.get("templates", []))


def build_generation_food_lookup(
    database,
    *,
    internal_food_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    # Copia superficial suficiente: durante generacion solo se añaden codigos nuevos
    # al lookup de trabajo; no se mutan los alimentos base del catalogo interno.
    full_food_lookup = dict(internal_food_lookup or get_internal_food_lookup())
    local_foods_cursor = database.foods_catalog.find({"suitable_meals": {"$exists": True, "$not": {"$size": 0}}})
    for document in local_foods_cursor:
        serialized_food = _serialize_cached_food(document)
        internal_code = str(serialized_food.get("internal_code") or "").strip()
        if internal_code and internal_code in full_food_lookup:
            continue
        full_food_lookup[serialized_food["code"]] = serialized_food

    def canonical_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, str, str, str]:
        code, food = item
        normalized_code = str(food.get("code") or code or "").strip().lower()
        normalized_internal_code = str(food.get("internal_code") or "").strip().lower()
        normalized_name = normalize_food_name(
            str(food.get("display_name") or food.get("name") or food.get("original_name") or normalized_code)
        ).strip()
        source_priority = SOURCE_PRIORITY.get(str(food.get("source") or "").strip().lower(), 99)
        return (
            source_priority,
            normalized_internal_code or normalized_code,
            normalized_code,
            normalized_name,
        )

    return {
        code: food
        for code, food in sorted(full_food_lookup.items(), key=canonical_sort_key)
    }


def _food_aliases(food: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for raw_value in (
        food.get("code"),
        str(food.get("code") or "").replace("_", " "),
        food.get("name"),
        food.get("display_name"),
        food.get("original_name"),
        *(food.get("aliases") or []),
    ):
        normalized_value = normalize_food_name(str(raw_value or "")).strip()
        if normalized_value:
            aliases.add(normalized_value)
    return aliases


def _derive_text_tags(text: str) -> set[str]:
    normalized_text = normalize_food_name(text)
    tags: set[str] = set()
    if not normalized_text:
        return tags

    if any(token in normalized_text for token in ("pan", "bread", "toast", "tostad")):
        tags.update({"bread", "toast"})
    if any(token in normalized_text for token in ("cornflakes", "cereal", "muesli", "granola")):
        tags.add("breakfast_cereal")
    if any(token in normalized_text for token in ("avena", "oats")):
        tags.add("oats")
    if any(token in normalized_text for token in ("tortitas de arroz", "tortitas de maiz", "rice cake", "corn cake")):
        tags.add("rice_cake")
    if any(token in normalized_text for token in ("mermelada", "jam")):
        tags.update({"spread", "jam"})
    if any(token in normalized_text for token in ("crema de cacahuete", "mantequilla de cacahuete", "peanut butter")):
        tags.update({"spread", "healthy_fat"})
    if any(token in normalized_text for token in ("aceite", "olive oil", "oil", "aguacate", "avocado", "frutos secos", "nuts", "almendra")):
        tags.add("healthy_fat")
    if any(token in normalized_text for token in ("pollo", "pavo", "turkey", "atun", "tuna", "egg", "huevo", "salmon")):
        tags.update({"protein", "lean_protein"})
    if any(token in normalized_text for token in ("tomate triturado", "tomate frito", "salsa", "sauce")):
        tags.add("sauce")
    if any(token in normalized_text for token in ("tomate", "lechuga", "cebolla", "pimiento", "verdura", "vegetable", "ensalada", "salad")):
        tags.update({"vegetables", "salad"})
    if any(token in normalized_text for token in ("leche", "milk", "bebida vegetal")):
        tags.update({"milk", "dairy"})
    if any(token in normalized_text for token in ("yogur", "yogurt", "skyr", "queso fresco", "queso fresco batido")):
        tags.update({"yogurt", "dairy"})
    if any(token in normalized_text for token in ("platano", "banana", "manzana", "apple", "fruta", "fruit")):
        tags.add("fruit")
    if any(token in normalized_text for token in ("wrap", "tortilla")):
        tags.add("wrap")
    if any(token in normalized_text for token in ("pasta", "macarron", "espagueti")):
        tags.add("pasta")
    if any(token in normalized_text for token in ("arroz", "rice")):
        tags.add("rice")
    if any(token in normalized_text for token in ("patata", "potato", "boniato", "batata", "sweet potato")):
        tags.add("potato")
    if any(token in normalized_text for token in ("queso fresco", "cottage", "quark", "queso batido")):
        tags.add("fresh_dairy")
    if any(token in normalized_text for token in ("pollo", "chicken", "pavo", "turkey")):
        tags.add("poultry")
    if any(token in normalized_text for token in ("atun", "tuna", "salmon", "fish")):
        tags.add("fish")
    if any(token in normalized_text for token in ("huevo", "egg")):
        tags.add("egg")
    return tags


def _derive_food_tags(food: dict[str, Any]) -> set[str]:
    tags = set()
    for alias in _food_aliases(food):
        tags.update(_derive_text_tags(alias))

    functional_group = derive_functional_group(food)
    if functional_group == "protein":
        tags.add("protein")
    elif functional_group == "carb":
        tags.add("carb")
    elif functional_group == "fat":
        tags.add("healthy_fat")
    elif functional_group == "fruit":
        tags.update({"fruit", "carb"})
    elif functional_group == "vegetable":
        tags.update({"vegetables", "salad"})
    elif functional_group == "dairy":
        tags.add("dairy")

    return tags


def _meal_types_for_context(meal_slot: str, meal_role: str) -> set[str]:
    meal_types: set[str] = set()
    if meal_slot == "early":
        meal_types.update({"breakfast", "snack"})
    elif meal_slot == "main":
        meal_types.add("lunch")
    elif meal_slot == "late":
        meal_types.add("dinner")

    if meal_role == "breakfast":
        meal_types.add("breakfast")
    elif meal_role == "pre_workout":
        meal_types.add("preworkout")
    elif meal_role == "post_workout":
        meal_types.add("postworkout")
    elif meal_role == "dinner":
        meal_types.add("dinner")

    return meal_types


def _build_plan_food_entries(
    meal_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for role, food_code in meal_plan.get("selected_role_codes", {}).items():
        if food_code in food_lookup:
            entries.append({
                "kind": "role",
                "role": role,
                "food_code": food_code,
                "food": food_lookup[food_code],
            })

    for support in meal_plan.get("support_food_specs", []):
        support_code = str(support.get("food_code") or "").strip()
        if support_code in food_lookup:
            entries.append({
                "kind": "support",
                "role": str(support.get("role") or "support"),
                "food_code": support_code,
                "food": food_lookup[support_code],
            })
    return entries


def _rule_is_enabled_for_meal(rule: dict[str, Any], *, meal_slot: str, meal_role: str) -> bool:
    preferred_slots = {normalize_food_name(slot) for slot in (rule.get("preferred_meal_slots") or []) if slot}
    if not preferred_slots:
        return True
    return not preferred_slots.isdisjoint(_meal_types_for_context(meal_slot, meal_role))


def _food_matches_rule_foods(food: dict[str, Any], names: list[str]) -> bool:
    if not names:
        return False
    aliases = _food_aliases(food)
    normalized_names = [normalize_food_name(name) for name in names if name]
    return any(
        normalized_name in aliases
        or any(normalized_name in alias or alias in normalized_name for alias in aliases)
        for normalized_name in normalized_names
    )


def _food_matches_rule_tags(food: dict[str, Any], tags: list[str]) -> bool:
    if not tags:
        return False
    food_tags = _derive_food_tags(food)
    expanded_tags: set[str] = set()
    for tag in tags:
        normalized_tag = normalize_food_name(tag)
        expanded_tags.add(normalized_tag)
        expanded_tags.update(TAG_ALIAS_MAP.get(normalized_tag, set()))
    return not food_tags.isdisjoint(expanded_tags)


def _food_matches_preferred_companion(food: dict[str, Any], preferred_companions: dict[str, Any]) -> bool:
    return _food_matches_rule_foods(food, preferred_companions.get("foods", [])) or _food_matches_rule_tags(
        food,
        preferred_companions.get("tags", []),
    )


def _plan_codes(meal_plan: dict[str, Any]) -> set[str]:
    codes = {
        str(food_code).strip()
        for food_code in meal_plan.get("selected_role_codes", {}).values()
        if str(food_code).strip()
    }
    codes.update(
        str(support.get("food_code") or "").strip()
        for support in meal_plan.get("support_food_specs", [])
        if str(support.get("food_code") or "").strip()
    )
    return codes


def _active_generation_excluded_codes(
    excluded_food_codes: set[str] | None,
    *,
    strict_exclusions: bool,
) -> set[str]:
    if not strict_exclusions:
        return set()
    return {str(code).strip() for code in (excluded_food_codes or set()) if str(code).strip()}


def _resolve_regeneration_context(
    regeneration_context: dict[str, Any] | None,
    *,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
) -> dict[str, Any]:
    context = dict(regeneration_context or {})
    context["original_food_codes"] = {
        str(code).strip()
        for code in context.get("original_food_codes", set())
        if str(code).strip()
    }
    context["original_selected_role_codes"] = {
        role: str(food_code).strip()
        for role, food_code in context.get("original_selected_role_codes", {}).items()
        if str(food_code).strip()
    }
    context["original_support_food_specs"] = [
        {
            "role": str(support_food.get("role") or "support"),
            "food_code": str(support_food.get("food_code") or "").strip(),
            "quantity": float(support_food.get("quantity") or 0.0),
        }
        for support_food in context.get("original_support_food_specs", [])
        if str(support_food.get("food_code") or "").strip()
    ]
    context["strict_exclusions"] = bool(context.get("strict_exclusions", strict_exclusions))
    context["prefer_visible_difference"] = bool(context.get("prefer_visible_difference", False))
    context["min_visual_difference"] = max(int(context.get("min_visual_difference", 2) or 0), 1)
    context["avoid_same_template"] = bool(context.get("avoid_same_template", False))
    context["expand_candidate_pool"] = bool(context.get("expand_candidate_pool", False))
    context["min_distinct_calorie_ratio"] = float(context.get("min_distinct_calorie_ratio", 0.45) or 0.0)
    context["excluded_food_codes"] = _active_generation_excluded_codes(
        excluded_food_codes or context.get("excluded_food_codes"),
        strict_exclusions=context["strict_exclusions"],
    )
    return context


def _is_regeneration_context_active(regeneration_context: dict[str, Any] | None) -> bool:
    resolved_context = _resolve_regeneration_context(regeneration_context)
    return bool(resolved_context.get("prefer_visible_difference"))


def _classify_protein_family(food: dict[str, Any]) -> str:
    tags = _derive_food_tags(food)
    if "yogurt" in tags or "fresh_dairy" in tags or derive_functional_group(food) == "dairy":
        return "dairy"
    if "egg" in tags:
        return "egg"
    if "fish" in tags:
        return "fish"
    if "poultry" in tags:
        return "poultry"
    if "lean_protein" in tags:
        return "lean_protein"
    if derive_functional_group(food) == "protein":
        return "protein"
    return "other"


def _classify_carb_family(food: dict[str, Any]) -> str:
    tags = _derive_food_tags(food)
    functional_group = derive_functional_group(food)
    if "wrap" in tags:
        return "wrap"
    if "rice_cake" in tags:
        return "rice_cake"
    if "bread" in tags or "toast" in tags:
        return "bread"
    if "breakfast_cereal" in tags:
        return "cereal"
    if "oats" in tags:
        return "oats"
    if "rice" in tags:
        return "rice"
    if "pasta" in tags:
        return "pasta"
    if "potato" in tags:
        return "potato"
    if functional_group == "fruit":
        return "fruit"
    if functional_group == "carb":
        return "carb"
    return "other"


def _classify_fat_family(food: dict[str, Any]) -> str:
    tags = _derive_food_tags(food)
    food_code = str(food.get("code") or "").strip().lower()
    if "spread" in tags and "healthy_fat" in tags:
        return "fat_spread"
    if food_code == "avocado":
        return "avocado"
    if food_code == "olive_oil" or "sauce" in tags:
        return "oil"
    if "healthy_fat" in tags:
        return "healthy_fat"
    if derive_functional_group(food) == "fat":
        return "fat"
    return "other"


def _build_visible_structure_signature(
    meal_plan: dict[str, Any],
    *,
    food_lookup: dict[str, dict[str, Any]],
) -> str:
    selected_role_codes = meal_plan.get("selected_role_codes", {})
    protein_food = food_lookup.get(str(selected_role_codes.get("protein") or "").strip())
    carb_food = food_lookup.get(str(selected_role_codes.get("carb") or "").strip())
    fat_food = food_lookup.get(str(selected_role_codes.get("fat") or "").strip())
    support_signatures = []

    for support_food in meal_plan.get("support_food_specs", []):
        support_role = str(support_food.get("role") or "support").strip().lower()
        if support_role in STRUCTURE_SUPPORT_ROLES:
            support_code = str(support_food.get("food_code") or "").strip()
            support_entry = food_lookup.get(support_code, support_code)
            support_signatures.append(
                get_food_family_signature(support_entry, role=support_role),
            )

    signature_components = [
        f"P:{_classify_protein_family(protein_food) if protein_food else 'missing'}",
        f"C:{_classify_carb_family(carb_food) if carb_food else 'missing'}",
        f"F:{_classify_fat_family(fat_food) if fat_food else 'missing'}",
        f"S:{','.join(sorted(dict.fromkeys(support_signatures)))}",
    ]
    return "|".join(signature_components)


def _build_meal_plan_fingerprint(meal_plan: dict[str, Any]) -> str:
    selected_role_codes = meal_plan.get("selected_role_codes", {})
    fingerprint_parts = [
        str(selected_role_codes.get(role) or "").strip()
        for role in PAIRING_ROLE_ORDER
    ]
    fingerprint_parts.extend(
        sorted(
            f"{str(support_food.get('role') or 'support').strip().lower()}:{str(support_food.get('food_code') or '').strip()}"
            for support_food in meal_plan.get("support_food_specs", [])
            if str(support_food.get("food_code") or "").strip()
        )
    )
    template_id = str(meal_plan.get("applied_template_id") or "").strip()
    if template_id:
        fingerprint_parts.append(f"template:{template_id}")
    return "|".join(part for part in fingerprint_parts if part)


def _select_seeded_plan_candidate(
    candidate_entries: list[dict[str, Any]],
    *,
    variety_seed: int | None,
    near_best_window: float,
) -> dict[str, Any] | None:
    if not candidate_entries:
        return None

    ranked_entries = sorted(candidate_entries, key=lambda entry: entry["ranking_key"])
    best_entry = ranked_entries[0]
    if variety_seed is None:
        return best_entry["plan"]

    best_cost = float(best_entry["selection_cost"])
    eligible_entries = [
        entry
        for entry in ranked_entries
        if float(entry["selection_cost"]) <= best_cost + near_best_window
    ]
    if len(eligible_entries) == 1:
        return eligible_entries[0]["plan"]

    best_by_structure: dict[str, dict[str, Any]] = {}
    for entry in eligible_entries:
        structure_signature = str(entry["structure_signature"])
        existing_entry = best_by_structure.get(structure_signature)
        if existing_entry is None or entry["ranking_key"] < existing_entry["ranking_key"]:
            best_by_structure[structure_signature] = entry

    seeded_entries: list[tuple[tuple[float, float, str], dict[str, Any]]] = []
    for structure_signature, entry in best_by_structure.items():
        fingerprint = _build_meal_plan_fingerprint(entry["plan"]) or structure_signature
        digest = hashlib.blake2b(
            f"{variety_seed}:{structure_signature}:{fingerprint}".encode("utf-8"),
            digest_size=8,
        ).digest()
        normalized_value = int.from_bytes(digest, "big") / float(2**64 - 1)
        seeded_entries.append(
            (
                (normalized_value, float(entry["selection_cost"]), fingerprint),
                entry["plan"],
            ),
        )

    return min(seeded_entries, key=lambda item: item[0])[1]


def build_global_diversity_penalty(
    *,
    meal_plan: dict[str, Any],
    daily_diversity_context: dict[str, Any] | None,
) -> float:
    if not daily_diversity_context:
        return 0.0

    selected_role_codes = {
        role: str(food_code).strip()
        for role, food_code in meal_plan.get("selected_role_codes", {}).items()
        if str(food_code).strip()
    }
    support_food_specs = meal_plan.get("support_food_specs", [])
    penalty = 0.0

    for role in ("protein", "carb", "fat"):
        role_code = selected_role_codes.get(role)
        if not role_code:
            continue
        family_signature = get_food_family_signature(role_code, role=role)
        penalty += (
            int(daily_diversity_context.get("family_counts", {}).get(role, {}).get(family_signature, 0))
            * {"protein": 0.75, "carb": 0.6, "fat": 0.22}.get(role, 0.15)
        )

    protein_code = selected_role_codes.get("protein")
    carb_code = selected_role_codes.get("carb")
    if protein_code and carb_code:
        family_pair_key = (
            f"{get_food_family_signature(protein_code, role='protein')}::"
            f"{get_food_family_signature(carb_code, role='carb')}"
        )
        penalty += int(daily_diversity_context.get("main_family_pair_counts", {}).get(family_pair_key, 0)) * 1.15

    structure_signature = get_meal_structure_signature(
        selected_role_codes=selected_role_codes,
        support_food_specs=support_food_specs,
    )
    penalty += int(daily_diversity_context.get("structure_counts", {}).get(structure_signature, 0)) * 1.45

    template_id = str(meal_plan.get("applied_template_id") or "").strip()
    if template_id:
        penalty += int(daily_diversity_context.get("template_counts", {}).get(template_id, 0)) * REPEATED_TEMPLATE_PENALTY

    return penalty


def evaluate_regeneration_candidate(
    *,
    meal,
    meal_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    regeneration_context: dict[str, Any] | None,
) -> dict[str, Any]:
    resolved_context = _resolve_regeneration_context(regeneration_context)
    original_food_codes = resolved_context.get("original_food_codes", set())
    original_selected_role_codes = resolved_context.get("original_selected_role_codes", {})
    original_support_food_specs = [
        {
            "role": str(support_food.get("role") or "support"),
            "food_code": str(support_food.get("food_code") or "").strip(),
            "quantity": float(support_food.get("quantity") or 0.0),
        }
        for support_food in resolved_context.get("original_support_food_specs", [])
        if str(support_food.get("food_code") or "").strip()
    ]
    min_visual_difference = resolved_context.get("min_visual_difference", 2)
    min_distinct_calorie_ratio = resolved_context.get("min_distinct_calorie_ratio", 0.45)
    avoid_same_template = resolved_context.get("avoid_same_template", False)

    candidate_food_codes = _plan_codes(meal_plan)
    candidate_selected_role_codes = {
        role: str(food_code).strip()
        for role, food_code in meal_plan.get("selected_role_codes", {}).items()
        if str(food_code).strip()
    }
    changed_visible_food_count = max(
        len(original_food_codes - candidate_food_codes),
        len(candidate_food_codes - original_food_codes),
    )
    changed_protein = (
        bool(original_selected_role_codes)
        and original_selected_role_codes.get("protein") != candidate_selected_role_codes.get("protein")
    )
    changed_carb = (
        bool(original_selected_role_codes)
        and original_selected_role_codes.get("carb") != candidate_selected_role_codes.get("carb")
    )
    changed_main_base = changed_protein or changed_carb
    changed_main_role_count = int(changed_protein) + int(changed_carb)

    original_structure_signature = str(
        resolved_context.get("original_structure_signature")
        or ""
    ).strip()
    if not original_structure_signature and original_selected_role_codes:
        original_structure_signature = _build_visible_structure_signature(
            {
                "selected_role_codes": original_selected_role_codes,
                "support_food_specs": original_support_food_specs,
            },
            food_lookup=food_lookup,
        )
    candidate_structure_signature = _build_visible_structure_signature(
        meal_plan,
        food_lookup=food_lookup,
    )
    structure_changed = (
        bool(original_structure_signature)
        and candidate_structure_signature != original_structure_signature
    )
    same_visible_structure = (
        bool(original_structure_signature)
        and candidate_structure_signature == original_structure_signature
    )

    original_template_id = str(resolved_context.get("original_template_id") or "").strip()
    candidate_template_id = str(meal_plan.get("applied_template_id") or "").strip()
    same_template = bool(
        original_template_id
        and candidate_template_id
        and original_template_id == candidate_template_id
    )

    total_calories = max(float(meal_plan.get("actual_calories") or 0.0), 1.0)
    distinct_calories = sum(
        float(food.get("calories") or 0.0)
        for food in meal_plan.get("foods", [])
        if str(food.get("food_code") or "").strip() not in original_food_codes
    )
    distinct_calorie_ratio = distinct_calories / total_calories

    passes_threshold = bool(
        changed_visible_food_count >= min_visual_difference
        or changed_main_base
        or structure_changed
        or distinct_calorie_ratio >= min_distinct_calorie_ratio
    )
    if avoid_same_template and same_template and not changed_main_base:
        passes_threshold = False

    visible_difference_score = (
        (changed_visible_food_count * 4.0)
        + (changed_main_role_count * 3.5)
        + (2.5 if structure_changed else 0.0)
        + (distinct_calorie_ratio * 3.0)
        - (2.0 if avoid_same_template and same_visible_structure else 0.0)
        - (1.0 if avoid_same_template and same_template else 0.0)
    )

    return {
        "meal_number": getattr(meal, "meal_number", None),
        "changed_visible_food_count": changed_visible_food_count,
        "changed_main_base": changed_main_base,
        "changed_main_role_count": changed_main_role_count,
        "distinct_calorie_ratio": distinct_calorie_ratio,
        "structure_changed": structure_changed,
        "same_visible_structure": same_visible_structure,
        "same_template": same_template,
        "candidate_structure_signature": candidate_structure_signature,
        "passes_threshold": passes_threshold,
        "visible_difference_score": visible_difference_score,
    }


def build_regeneration_candidate_ranking(
    *,
    meal,
    meal_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    regeneration_context: dict[str, Any] | None,
) -> tuple[Any, ...]:
    difference_summary = evaluate_regeneration_candidate(
        meal=meal,
        meal_plan=meal_plan,
        food_lookup=food_lookup,
        regeneration_context=regeneration_context,
    )
    return (
        int(not difference_summary["passes_threshold"]),
        int(difference_summary["same_template"]),
        int(difference_summary["same_visible_structure"]),
        -difference_summary["visible_difference_score"],
        float(meal_plan.get("score", 0.0)),
        str(meal_plan.get("applied_template_id") or ""),
    )


def _food_is_allowed_for_generation(food: dict[str, Any], preference_profile: dict[str, Any] | None) -> bool:
    if not preference_profile:
        return True
    allowed, _reasons = is_food_allowed_for_user(food, preference_profile)
    return allowed


def _compatibility_rank(
    food: dict[str, Any],
    *,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> float:
    scores = [0.0]
    for role in PAIRING_ROLE_ORDER:
        if is_food_allowed_for_role_and_slot(food, role=role, meal_slot=meal_slot):
            scores.append(
                get_food_role_fit_score(
                    food,
                    role=role,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                    training_focus=training_focus,
                )
            )
    for support_role in KNOWN_SUPPORT_ROLES:
        if is_support_food_allowed(food, support_role=support_role, meal_slot=meal_slot, meal_role=meal_role):
            scores.append(
                get_support_food_fit_score(
                    food,
                    support_role=support_role,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                    training_focus=training_focus,
                )
            )
    return max(scores)


def _find_candidate_foods(
    food_lookup: dict[str, dict[str, Any]],
    *,
    query: str | None = None,
    tag: str | None = None,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    preference_profile: dict[str, Any] | None,
    excluded_codes: set[str],
) -> list[dict[str, Any]]:
    normalized_query = normalize_food_name(query or "")
    query_tags = _derive_text_tags(normalized_query) if normalized_query else set()
    target_tag = normalize_food_name(tag or "")
    candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    for food in food_lookup.values():
        food_code = str(food.get("code") or "").strip()
        if not food_code or food_code in excluded_codes:
            continue
        if not _food_is_allowed_for_generation(food, preference_profile):
            continue

        aliases = _food_aliases(food)
        food_tags = _derive_food_tags(food)

        exact_match = normalized_query and normalized_query in aliases
        partial_match = normalized_query and any(normalized_query in alias or alias in normalized_query for alias in aliases)
        query_tag_match = bool(query_tags and not food_tags.isdisjoint(query_tags))
        tag_match = False
        if target_tag:
            expanded_target_tags = {target_tag, *TAG_ALIAS_MAP.get(target_tag, set())}
            tag_match = not food_tags.isdisjoint(expanded_target_tags)

        if not any((exact_match, partial_match, query_tag_match, tag_match)):
            continue

        match_priority = 0
        if exact_match:
            match_priority = 3
        elif partial_match:
            match_priority = 2
        elif query_tag_match or tag_match:
            match_priority = 1

        candidates.append((
            (
                -match_priority,
                -_compatibility_rank(
                    food,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                    training_focus=training_focus,
                ),
                SOURCE_PRIORITY.get(str(food.get("source") or "internal_catalog"), 9),
                str(food.get("name") or "").lower(),
            ),
            food,
        ))

    candidates.sort(key=lambda item: item[0])
    return [food for _, food in candidates]


def _choose_preferred_companion_candidate(
    rule: dict[str, Any],
    *,
    meal_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    preference_profile: dict[str, Any] | None,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
    regeneration_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    resolved_regeneration_context = _resolve_regeneration_context(
        regeneration_context,
        excluded_food_codes=excluded_food_codes,
        strict_exclusions=strict_exclusions,
    )
    preferred_companions = rule.get("preferred_companions") or {}
    excluded_codes = _plan_codes(meal_plan) | _active_generation_excluded_codes(
        resolved_regeneration_context.get("excluded_food_codes"),
        strict_exclusions=resolved_regeneration_context.get("strict_exclusions", False),
    )

    for preferred_name in preferred_companions.get("foods", []):
        matched_candidates = _find_candidate_foods(
            food_lookup,
            query=preferred_name,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            preference_profile=preference_profile,
            excluded_codes=excluded_codes,
        )
        if matched_candidates:
            return matched_candidates[0]

    for preferred_tag in preferred_companions.get("tags", []):
        matched_candidates = _find_candidate_foods(
            food_lookup,
            tag=preferred_tag,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            preference_profile=preference_profile,
            excluded_codes=excluded_codes,
        )
        if matched_candidates:
            return matched_candidates[0]

    return None


def _choose_valid_base_candidate(
    rule: dict[str, Any],
    *,
    meal_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    preference_profile: dict[str, Any] | None,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
    regeneration_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    resolved_regeneration_context = _resolve_regeneration_context(
        regeneration_context,
        excluded_food_codes=excluded_food_codes,
        strict_exclusions=strict_exclusions,
    )
    excluded_codes = _plan_codes(meal_plan) | _active_generation_excluded_codes(
        resolved_regeneration_context.get("excluded_food_codes"),
        strict_exclusions=resolved_regeneration_context.get("strict_exclusions", False),
    )
    for valid_tag in rule.get("valid_base_tags", []):
        matched_candidates = _find_candidate_foods(
            food_lookup,
            tag=valid_tag,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            preference_profile=preference_profile,
            excluded_codes=excluded_codes,
        )
        if matched_candidates:
            return matched_candidates[0]
    return None


def _derive_support_role(food: dict[str, Any]) -> str:
    food_tags = _derive_food_tags(food)
    functional_group = derive_functional_group(food)
    if functional_group in KNOWN_SUPPORT_ROLES:
        return functional_group
    if "jam" in food_tags:
        return "jam"
    if "spread" in food_tags:
        return "spread"
    if "sauce" in food_tags:
        return "sauce"
    if "lean_protein" in food_tags:
        return "lean_protein"
    if "healthy_fat" in food_tags:
        return "healthy_fat"
    if "bread" in food_tags:
        return "bread"
    return "support"


def _round_quantity_to_step(quantity: float, step: float) -> float:
    if step <= 0:
        return quantity
    return round(round(quantity / step) * step, 2)


def _clamp_food_quantity(food: dict[str, Any], quantity: float) -> float:
    step = max(float(food.get("step") or 1.0), 0.1)
    min_quantity = float(food.get("min_quantity") or step)
    max_quantity = max(float(food.get("max_quantity") or 0.0), min_quantity)
    quantity = max(min_quantity, min(quantity, max_quantity))
    return _round_quantity_to_step(quantity, step)


def _build_pairing_support_quantity(food: dict[str, Any]) -> float:
    support_role = _derive_support_role(food)
    if support_role in KNOWN_SUPPORT_ROLES:
        return _clamp_food_quantity(
            food,
            construir_cantidad_soporte_razonable(food, support_role=support_role),
        )

    unit = str(food.get("reference_unit") or "g").strip().lower()
    default_quantity = max(float(food.get("default_quantity") or 0.0), 0.0)
    if support_role == "healthy_fat":
        quantity = 10.0 if unit in {"g", "ml"} else 0.5
    elif support_role in {"jam", "spread"}:
        quantity = 15.0 if unit in {"g", "ml"} else 0.5
    elif support_role == "lean_protein":
        quantity = 60.0 if unit in {"g", "ml"} else 1.0
    elif support_role == "bread":
        quantity = 40.0 if unit in {"g", "ml"} else 1.0
    elif support_role == "sauce":
        quantity = 60.0 if unit in {"g", "ml"} else 0.5
    else:
        quantity = default_quantity * 0.45 if default_quantity > 0 else (30.0 if unit in {"g", "ml"} else 1.0)
    return _clamp_food_quantity(food, quantity)


def _build_ratio_quantity(
    food: dict[str, Any],
    *,
    ratio: float | None,
    total_ratio: float,
    target_calories: float,
    support_role: str,
) -> float:
    if ratio is None or total_ratio <= 0:
        return _build_pairing_support_quantity(food)

    reference_amount = max(float(food.get("reference_amount") or 1.0), 1.0)
    calorie_density = float(food.get("calories") or 0.0) / reference_amount
    if calorie_density <= 1e-6:
        return _build_pairing_support_quantity(food)

    target_support_calories = max(float(target_calories) * (ratio / total_ratio), 0.0)
    ratio_quantity = target_support_calories / calorie_density
    reasonable_quantity = _build_pairing_support_quantity(food)
    cap_multiplier = {
        "fruit": 1.8,
        "dairy": 1.6,
        "vegetable": 1.5,
        "healthy_fat": 1.5,
        "jam": 1.5,
        "spread": 1.6,
        "sauce": 1.5,
        "lean_protein": 1.35,
    }.get(support_role, 1.4)
    blended_quantity = min(ratio_quantity, reasonable_quantity * cap_multiplier)
    blended_quantity = max(blended_quantity, reasonable_quantity * 0.85)
    return _clamp_food_quantity(food, blended_quantity)


def _rebuild_meal_solution(
    *,
    meal,
    meal_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    meal_slot: str,
    training_focus: bool,
    preference_profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    role_foods = {}
    for role, food_code in meal_plan.get("selected_role_codes", {}).items():
        if food_code not in food_lookup:
            return None
        role_foods[role] = food_lookup[food_code]

    if set(role_foods) != set(PAIRING_ROLE_ORDER):
        return None

    return build_exact_meal_solution(
        meal=meal,
        role_foods=role_foods,
        support_food_specs=meal_plan.get("support_food_specs", []),
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=food_lookup,
        training_focus=training_focus,
        meal_slot=meal_slot,
        preference_profile=preference_profile,
    )


def _with_support_food(
    meal_plan: dict[str, Any],
    *,
    food_code: str,
    quantity: float,
    role: str,
) -> dict[str, Any]:
    support_food_specs = []
    seen_codes: set[str] = set()
    selected_role_codes = {
        role_key: code
        for role_key, code in meal_plan.get("selected_role_codes", {}).items()
    }

    for support in meal_plan.get("support_food_specs", []):
        support_code = str(support.get("food_code") or "").strip()
        if not support_code or support_code == food_code or support_code in selected_role_codes.values():
            continue
        if support_code in seen_codes:
            continue
        seen_codes.add(support_code)
        support_food_specs.append({
            "role": str(support.get("role") or "support"),
            "food_code": support_code,
            "quantity": float(support.get("quantity") or 0.0),
        })

    support_food_specs.append({
        "role": role,
        "food_code": food_code,
        "quantity": float(quantity),
    })
    return {
        **meal_plan,
        "selected_role_codes": selected_role_codes,
        "support_food_specs": support_food_specs,
    }


def _current_plan_satisfies_rule(
    rule: dict[str, Any],
    *,
    entries: list[dict[str, Any]],
) -> bool:
    trigger_entries = [
        entry
        for entry in entries
        if _food_matches_rule_foods(entry["food"], rule.get("trigger_foods", []))
        or _food_matches_rule_tags(entry["food"], rule.get("trigger_tags", []))
    ]
    if not trigger_entries:
        return True

    if rule.get("food_role") == "base":
        preferred_companions = rule.get("preferred_companions") or {}
        companion_entries = [
            entry
            for entry in entries
            if entry not in trigger_entries
        ]
        if str(rule.get("companion_strategy") or "") == "force_preferred_on_generation":
            return any(_food_matches_preferred_companion(entry["food"], preferred_companions) for entry in companion_entries)
        return bool(companion_entries)

    if rule.get("food_role") == "complement":
        valid_base_tags = rule.get("valid_base_tags", [])
        return any(
            entry not in trigger_entries and _food_matches_rule_tags(entry["food"], valid_base_tags)
            for entry in entries
        )

    return True


def apply_food_pairing_rules_to_meal_plan(
    *,
    meal,
    meal_plan: dict[str, Any],
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None = None,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
    regeneration_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_plan = meal_plan
    rules = sorted(load_food_pairing_rules(), key=lambda rule: int(rule.get("priority") or 0), reverse=True)

    for rule in rules:
        if not _rule_is_enabled_for_meal(rule, meal_slot=meal_slot, meal_role=meal_role):
            continue

        current_entries = _build_plan_food_entries(current_plan, food_lookup)
        if _current_plan_satisfies_rule(rule, entries=current_entries):
            continue

        candidate_food = None
        if rule.get("food_role") == "base":
            candidate_food = _choose_preferred_companion_candidate(
                rule,
                meal_plan=current_plan,
                food_lookup=food_lookup,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
                preference_profile=preference_profile,
                excluded_food_codes=excluded_food_codes,
                strict_exclusions=strict_exclusions,
                regeneration_context=regeneration_context,
            )
        elif rule.get("food_role") == "complement":
            candidate_food = _choose_valid_base_candidate(
                rule,
                meal_plan=current_plan,
                food_lookup=food_lookup,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
                preference_profile=preference_profile,
                excluded_food_codes=excluded_food_codes,
                strict_exclusions=strict_exclusions,
                regeneration_context=regeneration_context,
            )

        if not candidate_food:
            continue

        proposed_plan = _with_support_food(
            current_plan,
            food_code=str(candidate_food["code"]),
            quantity=_build_pairing_support_quantity(candidate_food),
            role=_derive_support_role(candidate_food),
        )
        rebuilt_solution = _rebuild_meal_solution(
            meal=meal,
            meal_plan=proposed_plan,
            food_lookup=food_lookup,
            meal_slot=meal_slot,
            training_focus=training_focus,
            preference_profile=preference_profile,
        )
        if not rebuilt_solution:
            continue
        current_plan = rebuilt_solution

    return current_plan


def _resolve_template_food(
    food_lookup: dict[str, dict[str, Any]],
    *,
    food_name: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    preference_profile: dict[str, Any] | None,
    resolution_cache: dict[tuple[Any, ...], dict[str, Any] | None] | None = None,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
    regeneration_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    resolved_regeneration_context = _resolve_regeneration_context(
        regeneration_context,
        excluded_food_codes=excluded_food_codes,
        strict_exclusions=strict_exclusions,
    )
    excluded_codes = _active_generation_excluded_codes(
        resolved_regeneration_context.get("excluded_food_codes"),
        strict_exclusions=resolved_regeneration_context.get("strict_exclusions", False),
    )
    cache_key = (
        normalize_food_name(food_name),
        meal_slot,
        meal_role,
        bool(training_focus),
        tuple(sorted(excluded_codes)),
    )
    if resolution_cache is not None and cache_key in resolution_cache:
        return resolution_cache[cache_key]

    candidates = _find_candidate_foods(
        food_lookup,
        query=food_name,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
        preference_profile=preference_profile,
        excluded_codes=excluded_codes,
    )
    resolved_candidate = candidates[0] if candidates else None
    if resolution_cache is not None:
        resolution_cache[cache_key] = resolved_candidate
    return resolved_candidate


def _remove_code_from_support_specs(
    support_specs: list[dict[str, Any]],
    *,
    food_code: str,
) -> list[dict[str, Any]]:
    return [
        support
        for support in support_specs
        if str(support.get("food_code") or "").strip() != food_code
    ]


def _assign_template_food(
    *,
    template_food: dict[str, Any],
    resolved_food: dict[str, Any],
    working_plan: dict[str, Any],
    target_meal,
    total_ratio: float,
) -> tuple[dict[str, Any], bool]:
    template_role = normalize_food_name(str(template_food.get("role") or "support"))
    selected_role_codes = dict(working_plan.get("selected_role_codes", {}))
    support_specs = list(working_plan.get("support_food_specs", []))
    resolved_code = str(resolved_food.get("code") or "").strip()
    changed = False

    core_role = TEMPLATE_ROLE_TO_CORE_ROLE.get(template_role)
    if core_role and selected_role_codes.get(core_role) != resolved_code:
        selected_role_codes[core_role] = resolved_code
        support_specs = _remove_code_from_support_specs(support_specs, food_code=resolved_code)
        changed = True
    elif resolved_code not in selected_role_codes.values():
        support_role = _derive_support_role(resolved_food)
        ratio_value = float(template_food.get("ratio") or 0.0) if template_food.get("ratio") is not None else None
        support_quantity = _build_ratio_quantity(
            resolved_food,
            ratio=ratio_value,
            total_ratio=total_ratio,
            target_calories=float(target_meal.target_calories),
            support_role=support_role,
        )
        existing_support_codes = {
            str(support.get("food_code") or "").strip()
            for support in support_specs
        }
        if resolved_code not in existing_support_codes:
            support_specs.append({
                "role": support_role,
                "food_code": resolved_code,
                "quantity": support_quantity,
            })
            changed = True

    return {
        **working_plan,
        "selected_role_codes": selected_role_codes,
        "support_food_specs": support_specs,
    }, changed


def _build_template_plan_candidate(
    template: dict[str, Any],
    *,
    meal,
    base_plan: dict[str, Any],
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    resolution_cache: dict[tuple[Any, ...], dict[str, Any] | None] | None = None,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
    regeneration_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, int, int]:
    working_plan = {
        **base_plan,
        "selected_role_codes": dict(base_plan.get("selected_role_codes", {})),
        "support_food_specs": list(base_plan.get("support_food_specs", [])),
    }
    current_codes = _plan_codes(base_plan)
    matched_existing = 0
    resolved_count = 0
    changed = False
    template_foods = [food for food in template.get("foods", []) if not food.get("optional")]
    total_ratio = sum(float(food.get("ratio") or 0.0) for food in template_foods if food.get("ratio") is not None)

    for template_food in template_foods:
        resolved_food = _resolve_template_food(
            food_lookup,
            food_name=str(template_food.get("name") or ""),
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            preference_profile=preference_profile,
            resolution_cache=resolution_cache,
            excluded_food_codes=excluded_food_codes,
            strict_exclusions=strict_exclusions,
            regeneration_context=regeneration_context,
        )
        if not resolved_food:
            return None, matched_existing, resolved_count

        resolved_count += 1
        if str(resolved_food.get("code") or "").strip() in current_codes:
            matched_existing += 1

        working_plan, food_changed = _assign_template_food(
            template_food=template_food,
            resolved_food=resolved_food,
            working_plan=working_plan,
            target_meal=meal,
            total_ratio=total_ratio,
        )
        changed = changed or food_changed

    if not changed:
        return None, matched_existing, resolved_count

    return working_plan, matched_existing, resolved_count


def apply_meal_templates_to_meal_plan(
    *,
    meal,
    meal_plan: dict[str, Any],
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None = None,
    daily_diversity_context: dict[str, Any] | None = None,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
    regeneration_context: dict[str, Any] | None = None,
    variety_seed: int | None = None,
) -> dict[str, Any]:
    meal_types = _meal_types_for_context(meal_slot, meal_role)
    if not meal_types:
        return meal_plan

    resolved_regeneration_context = _resolve_regeneration_context(
        regeneration_context,
        excluded_food_codes=excluded_food_codes,
        strict_exclusions=strict_exclusions,
    )
    regeneration_active = _is_regeneration_context_active(resolved_regeneration_context)
    current_plan = meal_plan
    current_score = float(current_plan.get("score", 0.0))
    template_candidates: list[dict[str, Any]] = []
    template_resolution_cache: dict[tuple[Any, ...], dict[str, Any] | None] = {}

    for template in load_meal_templates():
        template_meal_types = {
            normalize_food_name(meal_type)
            for meal_type in template.get("meal_types", [])
            if meal_type
        }
        if meal_types.isdisjoint(template_meal_types):
            continue

        candidate_plan, matched_existing, resolved_count = _build_template_plan_candidate(
            template,
            meal=meal,
            base_plan=current_plan,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
            food_lookup=food_lookup,
            preference_profile=preference_profile,
            resolution_cache=template_resolution_cache,
            excluded_food_codes=excluded_food_codes,
            strict_exclusions=strict_exclusions,
            regeneration_context=resolved_regeneration_context,
        )
        if not candidate_plan or resolved_count < 2:
            continue

        rebuilt_solution = _rebuild_meal_solution(
            meal=meal,
            meal_plan=candidate_plan,
            food_lookup=food_lookup,
            meal_slot=meal_slot,
            training_focus=training_focus,
            preference_profile=preference_profile,
        )
        if not rebuilt_solution:
            continue

        rebuilt_solution = {
            **rebuilt_solution,
            "applied_template_id": str(template.get("id") or ""),
            "applied_template_name": str(template.get("name") or ""),
            "applied_template_food_count": resolved_count,
        }
        candidate_score = float(rebuilt_solution.get("score", 0.0))
        allowed_score_delta = (
            REGENERATION_TEMPLATE_ALLOWED_SCORE_DELTA
            if regeneration_active
            else TEMPLATE_ALLOWED_SCORE_DELTA
        )
        if candidate_score > current_score + allowed_score_delta:
            continue

        if not regeneration_active and matched_existing < 1 and resolved_count < 3:
            continue

        if regeneration_active:
            difference_summary = evaluate_regeneration_candidate(
                meal=meal,
                meal_plan=rebuilt_solution,
                food_lookup=food_lookup,
                regeneration_context=resolved_regeneration_context,
            )
            ranking_key = (
                int(not difference_summary["passes_threshold"]),
                int(difference_summary["same_template"]),
                int(difference_summary["same_visible_structure"]),
                -difference_summary["visible_difference_score"],
                candidate_score,
                -int(template.get("priority") or 0),
                str(template.get("id") or ""),
            )
            selection_cost = (
                candidate_score
                + (10.0 if not difference_summary["passes_threshold"] else 0.0)
                + (2.5 if difference_summary["same_template"] else 0.0)
                + (3.0 if difference_summary["same_visible_structure"] else 0.0)
                - (difference_summary["visible_difference_score"] * 0.18)
            )
        else:
            if daily_diversity_context:
                diversity_penalty = build_global_diversity_penalty(
                    meal_plan=rebuilt_solution,
                    daily_diversity_context=daily_diversity_context,
                )
                ranking_key = (
                    round(diversity_penalty, 4),
                    candidate_score,
                    -matched_existing,
                    -int(template.get("priority") or 0),
                    str(template.get("id") or ""),
                )
            else:
                ranking_key = (
                    -matched_existing,
                    -int(template.get("priority") or 0),
                    candidate_score,
                    str(template.get("id") or ""),
                )
            diversity_penalty = 0.0
            selection_cost = candidate_score + float(diversity_penalty)
        if daily_diversity_context and not regeneration_active:
            selection_cost = candidate_score + float(diversity_penalty)

        template_candidates.append(
            {
                "plan": rebuilt_solution,
                "ranking_key": ranking_key,
                "selection_cost": selection_cost,
                "structure_signature": _build_visible_structure_signature(
                    rebuilt_solution,
                    food_lookup=food_lookup,
                ),
            },
        )

    selected_template_plan = _select_seeded_plan_candidate(
        template_candidates,
        variety_seed=variety_seed,
        near_best_window=TEMPLATE_VARIETY_WINDOW_BY_SLOT.get(meal_slot, 0.85),
    )
    return selected_template_plan if selected_template_plan is not None else current_plan


def apply_generation_coherence(
    *,
    meal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    meal_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None = None,
    daily_diversity_context: dict[str, Any] | None = None,
    excluded_food_codes: set[str] | None = None,
    strict_exclusions: bool = False,
    regeneration_context: dict[str, Any] | None = None,
    variety_seed: int | None = None,
) -> dict[str, Any]:
    resolved_regeneration_context = _resolve_regeneration_context(
        regeneration_context,
        excluded_food_codes=excluded_food_codes,
        strict_exclusions=strict_exclusions,
    )
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    paired_plan = apply_food_pairing_rules_to_meal_plan(
        meal=meal,
        meal_plan=meal_plan,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        excluded_food_codes=excluded_food_codes,
        strict_exclusions=strict_exclusions,
        regeneration_context=resolved_regeneration_context,
    )
    templated_plan = apply_meal_templates_to_meal_plan(
        meal=meal,
        meal_plan=paired_plan,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        daily_diversity_context=daily_diversity_context,
        excluded_food_codes=excluded_food_codes,
        strict_exclusions=strict_exclusions,
        regeneration_context=resolved_regeneration_context,
        variety_seed=variety_seed,
    )
    coherence_candidates = [paired_plan, templated_plan]

    if not _is_regeneration_context_active(resolved_regeneration_context):
        if not daily_diversity_context and variety_seed is None:
            return templated_plan
        candidate_entries: list[dict[str, Any]] = []
        for candidate in coherence_candidates:
            diversity_penalty = round(
                build_global_diversity_penalty(
                    meal_plan=candidate,
                    daily_diversity_context=daily_diversity_context,
                ),
                4,
            )
            candidate_entries.append(
                {
                    "plan": candidate,
                    "ranking_key": (
                        diversity_penalty,
                        float(candidate.get("score", 0.0)),
                        str(candidate.get("applied_template_id") or ""),
                    ),
                    "selection_cost": float(candidate.get("score", 0.0)) + diversity_penalty,
                    "structure_signature": _build_visible_structure_signature(
                        candidate,
                        food_lookup=food_lookup,
                    ),
                },
            )
        selected_candidate = _select_seeded_plan_candidate(
            candidate_entries,
            variety_seed=variety_seed,
            near_best_window=COHERENCE_VARIETY_WINDOW_BY_SLOT.get(meal_slot, 0.75),
        )
        return selected_candidate if selected_candidate is not None else templated_plan

    candidate_entries = []
    for candidate in coherence_candidates:
        ranking_key = build_regeneration_candidate_ranking(
            meal=meal,
            meal_plan=candidate,
            food_lookup=food_lookup,
            regeneration_context=resolved_regeneration_context,
        )
        difference_summary = evaluate_regeneration_candidate(
            meal=meal,
            meal_plan=candidate,
            food_lookup=food_lookup,
            regeneration_context=resolved_regeneration_context,
        )
        candidate_entries.append(
            {
                "plan": candidate,
                "ranking_key": ranking_key,
                "selection_cost": (
                    float(candidate.get("score", 0.0))
                    + (10.0 if not difference_summary["passes_threshold"] else 0.0)
                    + (2.5 if difference_summary["same_template"] else 0.0)
                    + (3.0 if difference_summary["same_visible_structure"] else 0.0)
                    - (difference_summary["visible_difference_score"] * 0.18)
                ),
                "structure_signature": difference_summary["candidate_structure_signature"],
            },
        )
    selected_candidate = _select_seeded_plan_candidate(
        candidate_entries,
        variety_seed=variety_seed,
        near_best_window=COHERENCE_VARIETY_WINDOW_BY_SLOT.get(meal_slot, 0.75),
    )
    return selected_candidate if selected_candidate is not None else templated_plan


def get_preferred_pairing_rank(
    candidate_food: dict[str, Any],
    *,
    meal_plan: dict[str, Any],
    current_food_entry: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    meal_slot: str,
    meal_role: str,
) -> int:
    del meal_slot, meal_role
    entries = _build_plan_food_entries(meal_plan, food_lookup)
    current_code = str(current_food_entry.get("code") or "").strip()
    current_is_base_for_rule = False

    for rule in load_food_pairing_rules():
        trigger_entries = [
            entry
            for entry in entries
            if _food_matches_rule_foods(entry["food"], rule.get("trigger_foods", []))
            or _food_matches_rule_tags(entry["food"], rule.get("trigger_tags", []))
        ]
        if not trigger_entries or rule.get("food_role") != "base":
            continue
        if any(str(entry["food_code"]) == current_code for entry in trigger_entries):
            current_is_base_for_rule = True
            continue
        preferred_companions = rule.get("preferred_companions") or {}
        if _food_matches_preferred_companion(candidate_food, preferred_companions):
            return 0

    if current_is_base_for_rule:
        return 2
    return 1
