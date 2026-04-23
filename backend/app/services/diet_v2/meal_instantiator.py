"""Blueprint instantiation for the diet generation v2 engine."""
from __future__ import annotations

import hashlib
from typing import Any

from app.services.diet.candidates import (
    apply_daily_usage_candidate_limits,
    apply_weekly_repeat_penalty,
    construir_cantidad_soporte_razonable,
    get_food_role_fit_score,
    get_role_candidate_codes,
    get_support_candidate_foods,
    iter_canonical_food_items,
)
from app.services.diet.constants import LOW_FAT_MEAL_ROLES
from app.services.diet_v2.blueprints import MealBlueprint, get_blueprint_visual_family
from app.services.diet_v2.diversity import build_meal_diversity_penalty, get_carb_cluster
from app.services.diet_v2.families import (
    food_matches_allowed_families,
    get_primary_family_id,
)
from app.services.food_preferences_service import count_food_preference_matches, is_food_allowed_for_user


def _stable_noise(seed: int, *parts: object) -> float:
    digest = hashlib.blake2b(
        f"{seed}|{'|'.join(str(part) for part in parts)}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") / 2**64


def _count_daily_family_usage(
    daily_food_usage: dict[str, Any] | None,
    *,
    family_id: str,
    role: str,
) -> int:
    if not daily_food_usage:
        return 0
    family_counts = daily_food_usage.get("family_counts", {}).get(role, {})
    return int(family_counts.get(f"{role}:{family_id}", 0))


def _build_role_candidate_score(
    food: dict[str, Any],
    *,
    role: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
    diversity_state: dict[str, Any],
    already_selected_codes: set[str],
    excluded_food_codes: set[str] | None,
    variety_seed: int,
) -> float:
    food_code = str(food.get("code") or "").strip()
    family_id = get_primary_family_id(food, role=role)
    score = get_food_role_fit_score(
        food,
        role=role,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
    )
    if preference_profile:
        score += count_food_preference_matches(food, preference_profile) * 0.6
    if daily_food_usage:
        score -= float(daily_food_usage.get("role_counts", {}).get(role, {}).get(food_code, 0)) * 0.9
    score -= _count_daily_family_usage(daily_food_usage, family_id=family_id, role=role) * 0.55
    score -= apply_weekly_repeat_penalty(food_code, role=role, weekly_food_usage=weekly_food_usage)
    if food_code in already_selected_codes:
        score -= 6.0
    if excluded_food_codes and food_code in excluded_food_codes:
        score -= 8.0

    if role == "protein":
        score -= float(diversity_state["protein_family_counts"].get(family_id, 0)) * 0.8
    elif role == "carb":
        score -= float(diversity_state["carb_family_counts"].get(family_id, 0)) * 0.95
        carb_cluster = get_carb_cluster(family_id)
        if carb_cluster:
            score -= float(diversity_state["carb_cluster_counts"].get(carb_cluster, 0)) * 0.55
            if meal_slot == "early" and carb_cluster == "breakfast_cereal":
                score -= float(
                    diversity_state["meal_slot_carb_cluster_counts"].get(meal_slot, {}).get(carb_cluster, 0)
                ) * 1.25
    elif role == "fat":
        score -= float(diversity_state["fat_family_counts"].get(family_id, 0)) * 0.2

    if meal_role in LOW_FAT_MEAL_ROLES and role == "fat":
        score -= 0.2

    score += _stable_noise(variety_seed, role, food_code) * 0.12
    return score


def _filter_role_candidates(
    *,
    role: str,
    allowed_families: tuple[str, ...],
    meal_request: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
    diversity_state: dict[str, Any],
    already_selected_codes: set[str],
    excluded_food_codes: set[str] | None,
    variety_seed: int,
) -> list[str]:
    forced_role_codes = meal_request.get("forced_role_codes") or {}
    forced_code = str(forced_role_codes.get(role) or "").strip()
    if forced_code:
        if forced_code not in food_lookup:
            return []
        forced_food = food_lookup[forced_code]
        allowed, _reasons = is_food_allowed_for_user(forced_food, preference_profile) if preference_profile else (True, [])
        if not allowed:
            return []
        if not food_matches_allowed_families(forced_food, allowed_families=allowed_families, role=role):
            return []
        return [forced_code]

    candidate_codes = get_role_candidate_codes(
        meal=meal_request["meal"],
        meal_index=meal_request["meal_index"],
        meals_count=meal_request["meals_count"],
        training_focus=meal_request["training_focus"],
        food_lookup=food_lookup,
    )
    candidate_codes = apply_daily_usage_candidate_limits(
        candidate_codes,
        daily_food_usage=daily_food_usage,
    )
    compatible_candidates: list[tuple[float, str]] = []
    seen_candidate_codes: set[str] = set()

    def try_candidate(candidate_code: str) -> None:
        if candidate_code in seen_candidate_codes or candidate_code not in food_lookup:
            return
        seen_candidate_codes.add(candidate_code)
        candidate_food = food_lookup[candidate_code]
        if not food_matches_allowed_families(candidate_food, allowed_families=allowed_families, role=role):
            return
        if preference_profile:
            allowed, _reasons = is_food_allowed_for_user(candidate_food, preference_profile)
            if not allowed:
                return
        candidate_score = _build_role_candidate_score(
            candidate_food,
            role=role,
            meal_slot=meal_request["meal_slot"],
            meal_role=meal_request["meal_role"],
            training_focus=meal_request["training_focus"],
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            weekly_food_usage=weekly_food_usage,
            diversity_state=diversity_state,
            already_selected_codes=already_selected_codes,
            excluded_food_codes=excluded_food_codes,
            variety_seed=variety_seed,
        )
        compatible_candidates.append((candidate_score, candidate_code))

    for candidate_code in candidate_codes.get(role, []):
        try_candidate(candidate_code)

    if not compatible_candidates:
        for candidate_code, _candidate_food in iter_canonical_food_items(food_lookup):
            try_candidate(candidate_code)

    compatible_candidates.sort(key=lambda item: (-item[0], item[1]))
    return [candidate_code for _score, candidate_code in compatible_candidates]


def _build_support_candidates(
    *,
    component,
    meal_request: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    already_selected_codes: set[str],
    excluded_food_codes: set[str] | None,
) -> list[dict[str, Any]]:
    preferred_support_candidates = sorted(
        meal_request.get("preferred_support_candidates") or [],
        key=lambda item: (
            str(item.get("role") or "").strip().lower(),
            str(item.get("food_code") or "").strip().lower(),
            -float(item.get("quantity") or 0.0),
        ),
    )
    ranked_supports: list[dict[str, Any]] = []
    seen_support_codes: set[str] = set()

    for preferred_support in preferred_support_candidates:
        support_code = str(preferred_support.get("food_code") or "").strip()
        if (
            str(preferred_support.get("role") or "").strip().lower() != component.role
            or support_code in seen_support_codes
            or support_code not in food_lookup
        ):
            continue
        support_food = food_lookup[support_code]
        if support_code in already_selected_codes or (excluded_food_codes and support_code in excluded_food_codes):
            continue
        if not food_matches_allowed_families(support_food, allowed_families=component.allowed_families, role=component.role):
            continue
        if preference_profile:
            allowed, _reasons = is_food_allowed_for_user(support_food, preference_profile)
            if not allowed:
                continue
        ranked_supports.append({
            "role": component.role,
            "food_code": support_code,
            "quantity": float(preferred_support.get("quantity") or construir_cantidad_soporte_razonable(
                support_food,
                support_role=component.role,
            )),
        })
        seen_support_codes.add(support_code)

    support_foods = get_support_candidate_foods(
        food_lookup,
        support_role=component.role,
        meal_slot=meal_request["meal_slot"],
        meal_role=meal_request["meal_role"],
        training_focus=meal_request["training_focus"],
        expand_candidate_pool=True,
    )
    if not support_foods:
        support_foods = [
            food
            for _code, food in iter_canonical_food_items(food_lookup)
            if str(food.get("code") or "").strip()
        ]

    for support_food in support_foods:
        support_code = str(support_food.get("code") or "").strip()
        if support_code in seen_support_codes or support_code in already_selected_codes:
            continue
        if excluded_food_codes and support_code in excluded_food_codes:
            continue
        if not food_matches_allowed_families(support_food, allowed_families=component.allowed_families, role=component.role):
            continue
        if preference_profile:
            allowed, _reasons = is_food_allowed_for_user(support_food, preference_profile)
            if not allowed:
                continue
        ranked_supports.append({
            "role": component.role,
            "food_code": support_code,
            "quantity": float(construir_cantidad_soporte_razonable(
                support_food,
                support_role=component.role,
            )),
        })
        seen_support_codes.add(support_code)

    return ranked_supports


def instantiate_blueprint(
    *,
    blueprint: MealBlueprint,
    meal_request: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
    diversity_state: dict[str, Any],
    variety_seed: int,
    excluded_food_codes: set[str] | None = None,
) -> dict[str, Any] | None:
    selected_role_codes: dict[str, str] = {}
    role_candidate_pool: dict[str, list[str]] = {}
    already_selected_codes: set[str] = set()

    for component in blueprint.required_components:
        if component.role not in {"protein", "carb", "fat"}:
            continue
        compatible_codes = _filter_role_candidates(
            role=component.role,
            allowed_families=component.allowed_families,
            meal_request=meal_request,
            food_lookup=food_lookup,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            weekly_food_usage=weekly_food_usage,
            diversity_state=diversity_state,
            already_selected_codes=already_selected_codes,
            excluded_food_codes=excluded_food_codes,
            variety_seed=variety_seed,
        )
        if not compatible_codes:
            return None
        selected_code = compatible_codes[0]
        selected_role_codes[component.role] = selected_code
        role_candidate_pool[component.role] = compatible_codes[:6]
        already_selected_codes.add(selected_code)

    for required_role in ("protein", "carb", "fat"):
        if required_role not in selected_role_codes:
            return None

    support_food_specs: list[dict[str, Any]] = []
    for component in blueprint.required_components + blueprint.optional_components:
        if component.role in {"protein", "carb", "fat"}:
            continue
        support_candidates = _build_support_candidates(
            component=component,
            meal_request=meal_request,
            food_lookup=food_lookup,
            preference_profile=preference_profile,
            already_selected_codes=already_selected_codes,
            excluded_food_codes=excluded_food_codes,
        )
        if not support_candidates and not component.optional:
            return None
        if support_candidates:
            support_choice = support_candidates[0]
            support_food_specs.append(support_choice)
            already_selected_codes.add(support_choice["food_code"])

    protein_family = get_primary_family_id(food_lookup[selected_role_codes["protein"]], role="protein")
    carb_family = get_primary_family_id(food_lookup[selected_role_codes["carb"]], role="carb")
    fat_family = get_primary_family_id(food_lookup[selected_role_codes["fat"]], role="fat")
    support_families = [
        get_primary_family_id(food_lookup[support_food["food_code"]], role=support_food["role"])
        for support_food in support_food_specs
        if support_food["food_code"] in food_lookup
    ]
    visual_family = get_blueprint_visual_family(
        blueprint,
        meal_slot=meal_request["meal_slot"],
    )
    diversity_penalty = build_meal_diversity_penalty(
        blueprint_id=blueprint.id,
        structural_family=blueprint.structural_family,
        visual_family=visual_family,
        visual_continuity_group=blueprint.visual_continuity_group,
        style_tags=blueprint.style_tags,
        meal_slot=meal_request["meal_slot"],
        meal_role=meal_request["meal_role"],
        protein_family=protein_family,
        carb_family=carb_family,
        fat_family=fat_family,
        support_families=support_families,
        diversity_state=diversity_state,
    )

    return {
        "selected_role_codes": selected_role_codes,
        "support_food_specs": support_food_specs,
        "role_candidate_pool": role_candidate_pool,
        "protein_family": protein_family,
        "carb_family": carb_family,
        "fat_family": fat_family,
        "support_families": support_families,
        "blueprint_diversity_penalty": diversity_penalty,
        "applied_blueprint_id": blueprint.id,
        "applied_blueprint_family": blueprint.structural_family,
        "applied_blueprint_visual_family": visual_family,
        "applied_blueprint_visual_continuity_group": blueprint.visual_continuity_group,
        "applied_blueprint_style_tags": sorted(blueprint.style_tags),
    }
