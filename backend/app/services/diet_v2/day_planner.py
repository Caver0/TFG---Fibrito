"""Global day blueprint planner for the diet generation v2 engine."""
from __future__ import annotations

import hashlib
from typing import Any

from app.services.diet.candidates import (
    get_role_candidate_codes,
    get_support_candidate_foods,
    is_food_allowed_for_role_and_slot,
    iter_canonical_food_items,
)
from app.services.diet_v2.blueprints import (
    MealBlueprint,
    blueprint_is_compatible_with_context,
    get_blueprint_visual_family,
    iter_blueprints,
)
from app.services.diet_v2.diversity import (
    build_blueprint_choice_penalty,
    create_diversity_state,
    register_blueprint_choice,
)
from app.services.diet_v2.families import food_matches_allowed_families
from app.services.food_preferences_service import is_food_allowed_for_user


def _stable_noise(seed: int, *parts: object) -> float:
    digest = hashlib.blake2b(
        f"{seed}|{'|'.join(str(part) for part in parts)}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") / 2**64


def _build_visual_rotation_bonus(
    *,
    meal_request: dict[str, Any],
    visual_family: str,
    variety_seed: int,
) -> float:
    family_noise = _stable_noise(
        variety_seed,
        "visual_rotation",
        meal_request["meal_slot"],
        meal_request["meal_role"],
        visual_family,
    )
    if meal_request["meal_slot"] == "early":
        if meal_request["meal_role"] == "breakfast":
            preferred_families = sorted(
                (
                    "breakfast_toast",
                    "breakfast_wrap",
                    "egg_breakfast_plate",
                    "stacked_snack",
                    "cold_snack",
                    "breakfast_bowl",
                ),
                key=lambda family: _stable_noise(
                    variety_seed,
                    "breakfast_visual_order",
                    meal_request["meal_index"],
                    family,
                ),
            )
            family_rank = preferred_families.index(visual_family) if visual_family in preferred_families else len(preferred_families)
            bonus = max(0.0, 0.5 - (family_rank * 0.09))
            bonus += family_noise * 0.12
            if visual_family == "breakfast_bowl":
                bonus -= 0.1
            elif visual_family in {"breakfast_toast", "breakfast_wrap", "egg_breakfast_plate"}:
                bonus += 0.1
            elif visual_family == "stacked_snack":
                bonus += 0.02
            elif visual_family == "cold_snack":
                bonus += 0.02
            return bonus

        bonus = family_noise * 0.18
        if visual_family != "breakfast_bowl":
            bonus += 0.12
        if visual_family in {"breakfast_toast", "breakfast_wrap", "egg_breakfast_plate"}:
            bonus += 0.05
        return bonus
    return family_noise * 0.08


def _food_is_compatible(
    food: dict[str, Any],
    *,
    role: str,
    allowed_families: tuple[str, ...],
    meal_slot: str,
    preference_profile: dict[str, Any] | None,
) -> bool:
    if role in {"protein", "carb", "fat"} and not is_food_allowed_for_role_and_slot(
        food,
        role=role,
        meal_slot=meal_slot,
    ):
        return False
    if not food_matches_allowed_families(food, allowed_families=allowed_families, role=role):
        return False
    if preference_profile:
        allowed, _reasons = is_food_allowed_for_user(food, preference_profile)
        if not allowed:
            return False
    return True


def blueprint_is_feasible(
    blueprint: MealBlueprint,
    *,
    meal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    meal_slot: str,
    meal_role: str,
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    forced_role_codes: dict[str, str] | None = None,
) -> bool:
    if not blueprint_is_compatible_with_context(
        blueprint,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
    ):
        return False

    forced_role_codes = forced_role_codes or {}
    role_candidate_codes = get_role_candidate_codes(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )
    for component in blueprint.required_components:
        if component.role in {"protein", "carb", "fat"}:
            forced_code = str(forced_role_codes.get(component.role) or "").strip()
            if forced_code:
                forced_food = food_lookup.get(forced_code)
                if not forced_food:
                    return False
                if not _food_is_compatible(
                    forced_food,
                    role=component.role,
                    allowed_families=component.allowed_families,
                    meal_slot=meal_slot,
                    preference_profile=preference_profile,
                ):
                    return False
                continue

            if any(
                _food_is_compatible(
                    food_lookup[food_code],
                    role=component.role,
                    allowed_families=component.allowed_families,
                    meal_slot=meal_slot,
                    preference_profile=preference_profile,
                )
                for food_code in role_candidate_codes.get(component.role, [])
                if food_code in food_lookup
            ):
                continue
            if any(
                _food_is_compatible(
                    food,
                    role=component.role,
                    allowed_families=component.allowed_families,
                    meal_slot=meal_slot,
                    preference_profile=preference_profile,
                )
                for _food_code, food in iter_canonical_food_items(food_lookup)
            ):
                continue
            return False

        support_candidates = get_support_candidate_foods(
            food_lookup,
            support_role=component.role,
            meal_slot=meal_slot,
            meal_role=meal_role,
            training_focus=training_focus,
        )
        if any(
            _food_is_compatible(
                support_food,
                role=component.role,
                allowed_families=component.allowed_families,
                meal_slot=meal_slot,
                preference_profile=preference_profile,
            )
            for support_food in support_candidates
        ):
            continue
        if any(
            _food_is_compatible(
                support_food,
                role=component.role,
                allowed_families=component.allowed_families,
                meal_slot=meal_slot,
                preference_profile=preference_profile,
            )
            for _food_code, support_food in iter_canonical_food_items(food_lookup)
        ):
            continue
        return False

    return True


def rank_blueprints_for_meal(
    *,
    meal_request: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    variety_seed: int,
    diversity_state: dict[str, Any] | None = None,
) -> list[MealBlueprint]:
    diversity_state = diversity_state or create_diversity_state()
    ranked_candidates: list[tuple[float, MealBlueprint]] = []

    for blueprint in iter_blueprints():
        visual_family = get_blueprint_visual_family(
            blueprint,
            meal_slot=meal_request["meal_slot"],
        )
        if not blueprint_is_feasible(
            blueprint,
            meal=meal_request["meal"],
            meal_index=meal_request["meal_index"],
            meals_count=meal_request["meals_count"],
            training_focus=meal_request["training_focus"],
            meal_slot=meal_request["meal_slot"],
            meal_role=meal_request["meal_role"],
            food_lookup=food_lookup,
            preference_profile=preference_profile,
            forced_role_codes=meal_request.get("forced_role_codes"),
        ):
            continue

        repetition_penalty = build_blueprint_choice_penalty(
            blueprint_id=blueprint.id,
            structural_family=blueprint.structural_family,
            visual_family=visual_family,
            visual_continuity_group=blueprint.visual_continuity_group,
            style_tags=blueprint.style_tags,
            meal_slot=meal_request["meal_slot"],
            meal_role=meal_request["meal_role"],
            diversity_state=diversity_state,
        )
        if not blueprint.allow_repeat and diversity_state["blueprint_counts"].get(blueprint.id, 0) >= blueprint.daily_max_repetitions:
            repetition_penalty += 100.0
        if diversity_state["structural_family_counts"].get(blueprint.structural_family, 0) >= max(1, blueprint.daily_max_repetitions + 1):
            repetition_penalty += 12.0
        if diversity_state["visual_family_counts"].get(visual_family, 0) >= max(1, blueprint.daily_max_repetitions + 1):
            repetition_penalty += 8.0
        if diversity_state["visual_continuity_group_counts"].get(blueprint.visual_continuity_group, 0) >= 2:
            repetition_penalty += 4.5

        if meal_request["training_focus"] and meal_request["meal_role"] in blueprint.training_focus_compatibility:
            focus_bonus = 0.25
        elif meal_request["training_focus"] and "any" not in blueprint.training_focus_compatibility:
            focus_bonus = -0.25
        else:
            focus_bonus = 0.0

        visual_rotation_bonus = _build_visual_rotation_bonus(
            meal_request=meal_request,
            visual_family=visual_family,
            variety_seed=variety_seed,
        )
        noise = _stable_noise(variety_seed, meal_request["meal_index"], blueprint.id) * 0.08
        score = repetition_penalty - blueprint.base_priority - focus_bonus - visual_rotation_bonus - noise
        ranked_candidates.append((score, blueprint))

    ranked_candidates.sort(key=lambda item: (item[0], item[1].id))
    return [blueprint for _score, blueprint in ranked_candidates]


def plan_day_blueprints(
    *,
    meal_requests: list[dict[str, Any]],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    variety_seed: int,
    beam_width: int = 6,
) -> dict[str, Any]:
    ranked_options_by_index: dict[int, list[MealBlueprint]] = {}
    planner_options_by_index: dict[int, list[MealBlueprint]] = {}
    for meal_request in meal_requests:
        strict_candidates = rank_blueprints_for_meal(
            meal_request=meal_request,
            food_lookup=food_lookup,
            preference_profile=preference_profile,
            variety_seed=variety_seed,
        )
        meal_index = meal_request["meal_index"]
        ranked_options_by_index[meal_index] = strict_candidates
        if strict_candidates:
            planner_options_by_index[meal_index] = strict_candidates
            continue
        planner_options_by_index[meal_index] = [
            blueprint
            for blueprint in iter_blueprints()
            if blueprint_is_compatible_with_context(
                blueprint,
                meal_slot=meal_request["meal_slot"],
                meal_role=meal_request["meal_role"],
                training_focus=meal_request["training_focus"],
            )
        ]

    beam: list[dict[str, Any]] = [{
        "score": 0.0,
        "assignments": {},
        "diversity_state": create_diversity_state(),
    }]

    for meal_request in meal_requests:
        meal_index = meal_request["meal_index"]
        candidate_blueprints = planner_options_by_index.get(meal_index, [])
        if not candidate_blueprints:
            continue

        next_beam: list[dict[str, Any]] = []
        for beam_entry in beam:
            for candidate_rank, candidate_blueprint in enumerate(candidate_blueprints[:beam_width]):
                diversity_state = beam_entry["diversity_state"]
                visual_family = get_blueprint_visual_family(
                    candidate_blueprint,
                    meal_slot=meal_request["meal_slot"],
                )
                choice_penalty = build_blueprint_choice_penalty(
                    blueprint_id=candidate_blueprint.id,
                    structural_family=candidate_blueprint.structural_family,
                    visual_family=visual_family,
                    visual_continuity_group=candidate_blueprint.visual_continuity_group,
                    style_tags=candidate_blueprint.style_tags,
                    meal_slot=meal_request["meal_slot"],
                    meal_role=meal_request["meal_role"],
                    diversity_state=diversity_state,
                )
                if (
                    not candidate_blueprint.allow_repeat
                    and diversity_state["blueprint_counts"].get(candidate_blueprint.id, 0) >= candidate_blueprint.daily_max_repetitions
                ):
                    continue

                rank_penalty = candidate_rank * (0.34 if meal_request["meal_role"] == "breakfast" else 0.08)
                next_state = register_blueprint_choice(
                    diversity_state,
                    blueprint_id=candidate_blueprint.id,
                    structural_family=candidate_blueprint.structural_family,
                    visual_family=visual_family,
                    visual_continuity_group=candidate_blueprint.visual_continuity_group,
                    style_tags=list(candidate_blueprint.style_tags),
                    meal_slot=meal_request["meal_slot"],
                    meal_role=meal_request["meal_role"],
                )
                next_beam.append({
                    "score": beam_entry["score"] + choice_penalty - candidate_blueprint.base_priority + rank_penalty,
                    "assignments": {
                        **beam_entry["assignments"],
                        meal_index: candidate_blueprint.id,
                    },
                    "diversity_state": next_state,
                })

        if not next_beam and candidate_blueprints:
            for beam_entry in beam:
                candidate_blueprint = candidate_blueprints[0]
                diversity_state = beam_entry["diversity_state"]
                visual_family = get_blueprint_visual_family(
                    candidate_blueprint,
                    meal_slot=meal_request["meal_slot"],
                )
                choice_penalty = build_blueprint_choice_penalty(
                    blueprint_id=candidate_blueprint.id,
                    structural_family=candidate_blueprint.structural_family,
                    visual_family=visual_family,
                    visual_continuity_group=candidate_blueprint.visual_continuity_group,
                    style_tags=candidate_blueprint.style_tags,
                    meal_slot=meal_request["meal_slot"],
                    meal_role=meal_request["meal_role"],
                    diversity_state=diversity_state,
                )
                next_state = register_blueprint_choice(
                    diversity_state,
                    blueprint_id=candidate_blueprint.id,
                    structural_family=candidate_blueprint.structural_family,
                    visual_family=visual_family,
                    visual_continuity_group=candidate_blueprint.visual_continuity_group,
                    style_tags=list(candidate_blueprint.style_tags),
                    meal_slot=meal_request["meal_slot"],
                    meal_role=meal_request["meal_role"],
                )
                next_beam.append({
                    "score": beam_entry["score"] + choice_penalty - candidate_blueprint.base_priority,
                    "assignments": {
                        **beam_entry["assignments"],
                        meal_index: candidate_blueprint.id,
                    },
                    "diversity_state": next_state,
                })

        next_beam.sort(key=lambda entry: entry["score"])
        beam = next_beam[:beam_width] or beam

    best_plan = beam[0] if beam else {
        "score": 0.0,
        "assignments": {},
        "diversity_state": create_diversity_state(),
    }
    fallback_blueprints_by_meal = {
        meal_request["meal_index"]: [blueprint.id for blueprint in planner_options_by_index.get(meal_request["meal_index"], [])]
        for meal_request in meal_requests
    }
    strict_blueprints_by_meal = {
        meal_request["meal_index"]: [blueprint.id for blueprint in ranked_options_by_index.get(meal_request["meal_index"], [])]
        for meal_request in meal_requests
    }
    return {
        "assignments": best_plan["assignments"],
        "fallback_blueprints_by_meal": fallback_blueprints_by_meal,
        "strict_blueprints_by_meal": strict_blueprints_by_meal,
        "planner_diversity_state": best_plan["diversity_state"],
    }
