"""Meal regeneration v2 for the diet generation engine."""
from __future__ import annotations

import time
from typing import Any

from app.services.diet.candidates import get_meal_structure_signature
from app.services.diet_v2.blueprints import get_blueprint
from app.services.diet_v2.day_planner import rank_blueprints_for_meal
from app.services.diet_v2.diversity import create_diversity_state
from app.services.diet_v2.meal_instantiator import instantiate_blueprint
from app.services.diet_v2.repair import repair_meal_plan
from app.services.diet_v2.families import get_primary_family_id
from app.services.diet_v2.telemetry import set_last_regeneration_diagnostics


def _infer_current_blueprint_id(
    *,
    current_meal_plan: dict[str, Any] | None,
    meal_request: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    variety_seed: int,
) -> str | None:
    if not current_meal_plan:
        return None
    role_codes = current_meal_plan.get("selected_role_codes", {})
    if not role_codes:
        return None

    best_blueprint_id: str | None = None
    best_score: tuple[int, int] | None = None
    for blueprint in rank_blueprints_for_meal(
        meal_request=meal_request,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        variety_seed=variety_seed,
    ):
        score = 0
        for component in blueprint.required_components:
            if component.role not in role_codes:
                continue
            food_code = str(role_codes.get(component.role) or "").strip()
            if not food_code or food_code not in food_lookup:
                continue
            if get_primary_family_id(food_lookup[food_code], role=component.role) in component.allowed_families:
                score += 2
        if best_score is None or (score, int(blueprint.id == best_blueprint_id)) > best_score:
            best_score = (score, 0)
            best_blueprint_id = blueprint.id
    return best_blueprint_id


def summarize_visible_difference(
    *,
    current_meal_plan: dict[str, Any] | None,
    current_food_codes: set[str],
    candidate_plan: dict[str, Any],
) -> dict[str, Any]:
    candidate_food_codes = {
        str(food.get("food_code") or "").strip()
        for food in candidate_plan.get("foods", [])
        if str(food.get("food_code") or "").strip()
    }
    current_role_codes = (current_meal_plan or {}).get("selected_role_codes", {})
    candidate_role_codes = candidate_plan.get("selected_role_codes", {})
    changed_roles = [
        role
        for role in ("protein", "carb", "fat")
        if str(current_role_codes.get(role) or "").strip() != str(candidate_role_codes.get(role) or "").strip()
    ]
    visible_change_count = len(current_food_codes.symmetric_difference(candidate_food_codes))
    current_structure = get_meal_structure_signature(
        selected_role_codes=current_role_codes,
        support_food_specs=(current_meal_plan or {}).get("support_food_specs", []),
    ) if current_role_codes else None
    candidate_structure = get_meal_structure_signature(
        selected_role_codes=candidate_role_codes,
        support_food_specs=candidate_plan.get("support_food_specs", []),
    )
    return {
        "visible_change_count": visible_change_count,
        "changed_roles": changed_roles,
        "same_visible_structure": current_structure == candidate_structure if current_structure else False,
        "structure_changed": current_structure != candidate_structure if current_structure else True,
    }


def regenerate_meal_plan_v2(
    *,
    meal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    meal_slot: str,
    meal_role: str,
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
    current_food_codes: set[str],
    current_meal_plan: dict[str, Any] | None,
    variety_seed: int,
) -> dict[str, Any] | None:
    started_at = time.perf_counter()
    meal_request = {
        "meal": meal,
        "meal_index": meal_index,
        "meals_count": meals_count,
        "training_focus": training_focus,
        "meal_slot": meal_slot,
        "meal_role": meal_role,
        "forced_role_codes": {},
        "preferred_support_candidates": [],
    }
    current_blueprint_id = _infer_current_blueprint_id(
        current_meal_plan=current_meal_plan,
        meal_request=meal_request,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        variety_seed=variety_seed,
    )
    ranked_blueprints = rank_blueprints_for_meal(
        meal_request=meal_request,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        variety_seed=variety_seed,
        diversity_state=create_diversity_state(),
    )

    best_candidate: dict[str, Any] | None = None
    best_difference: tuple[int, int, int, float] | None = None
    diagnostics = {
        "meal_index": meal_index,
        "meal_slot": meal_slot,
        "meal_role": meal_role,
        "current_blueprint_id": current_blueprint_id,
        "attempts": [],
        "selected_phase": None,
        "selected_blueprint_id": None,
        "used_v2": False,
        "returned_candidate": False,
        "fallback_reason": None,
        "elapsed_seconds": 0.0,
    }

    phases = (
        {
            "name": "different_blueprint_strict",
            "allow_same_blueprint": False,
            "excluded_food_codes": set(current_food_codes),
            "min_visible_difference": 2,
        },
        {
            "name": "same_or_different_blueprint_strict",
            "allow_same_blueprint": True,
            "excluded_food_codes": set(current_food_codes),
            "min_visible_difference": 2,
        },
        {
            "name": "same_or_different_blueprint_relaxed",
            "allow_same_blueprint": True,
            "excluded_food_codes": set(),
            "min_visible_difference": 1,
        },
    )

    for phase_index, phase in enumerate(phases):
        for blueprint in ranked_blueprints:
            attempt_started_at = time.perf_counter()
            if not phase["allow_same_blueprint"] and blueprint.id == current_blueprint_id:
                diagnostics["attempts"].append({
                    "phase": phase["name"],
                    "blueprint_id": blueprint.id,
                    "status": "skipped_same_blueprint",
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                continue
            instantiation = instantiate_blueprint(
                blueprint=blueprint,
                meal_request=meal_request,
                food_lookup=food_lookup,
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                weekly_food_usage=weekly_food_usage,
                diversity_state=create_diversity_state(),
                variety_seed=variety_seed + phase_index,
                excluded_food_codes=phase["excluded_food_codes"],
            )
            if instantiation is None:
                diagnostics["attempts"].append({
                    "phase": phase["name"],
                    "blueprint_id": blueprint.id,
                    "status": "instantiation_failed",
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                continue
            candidate_plan = repair_meal_plan(
                blueprint=blueprint,
                meal=meal,
                meal_request=meal_request,
                instantiation=instantiation,
                food_lookup=food_lookup,
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                weekly_food_usage=weekly_food_usage,
            )
            if candidate_plan is None:
                diagnostics["attempts"].append({
                    "phase": phase["name"],
                    "blueprint_id": blueprint.id,
                    "status": "portion_fit_failed",
                    "selected_role_codes": instantiation.get("selected_role_codes", {}),
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                continue

            difference = summarize_visible_difference(
                current_meal_plan=current_meal_plan,
                current_food_codes=current_food_codes,
                candidate_plan=candidate_plan,
            )
            blueprint_changed = int(str(candidate_plan.get("applied_blueprint_id") or "") != str(current_blueprint_id or ""))
            changed_primary = int(any(role in difference["changed_roles"] for role in ("protein", "carb")))
            ranking = (
                -blueprint_changed,
                -changed_primary,
                -difference["visible_change_count"],
                float(candidate_plan.get("score") or 0.0),
            )
            diagnostics["attempts"].append({
                "phase": phase["name"],
                "blueprint_id": blueprint.id,
                "status": "candidate_resolved",
                "fit_method": candidate_plan.get("portion_fit_method", "exact"),
                "selected_role_codes": candidate_plan.get("selected_role_codes", {}),
                "difference": difference,
                "elapsed_seconds": time.perf_counter() - attempt_started_at,
            })
            if best_candidate is None or best_difference is None or ranking < best_difference:
                best_candidate = candidate_plan
                best_difference = ranking
            if (
                difference["visible_change_count"] >= phase["min_visible_difference"]
                and (blueprint_changed or changed_primary or len(difference["changed_roles"]) >= 2)
            ):
                candidate_plan["regeneration_difference"] = difference
                candidate_plan["regeneration_source_blueprint_id"] = current_blueprint_id
                diagnostics["selected_phase"] = phase["name"]
                diagnostics["selected_blueprint_id"] = candidate_plan.get("applied_blueprint_id")
                diagnostics["used_v2"] = True
                diagnostics["returned_candidate"] = True
                diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
                candidate_plan["regeneration_diagnostics"] = diagnostics
                set_last_regeneration_diagnostics(diagnostics)
                return candidate_plan

    if best_candidate is not None:
        best_candidate["regeneration_difference"] = summarize_visible_difference(
            current_meal_plan=current_meal_plan,
            current_food_codes=current_food_codes,
            candidate_plan=best_candidate,
        )
        best_candidate["regeneration_source_blueprint_id"] = current_blueprint_id
        diagnostics["selected_phase"] = "best_candidate_after_phases"
        diagnostics["selected_blueprint_id"] = best_candidate.get("applied_blueprint_id")
        diagnostics["used_v2"] = True
        diagnostics["returned_candidate"] = True
        diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
        best_candidate["regeneration_diagnostics"] = diagnostics
        set_last_regeneration_diagnostics(diagnostics)
        return best_candidate

    if current_blueprint_id:
        sibling_ids = tuple(get_blueprint(current_blueprint_id).sibling_blueprints) if get_blueprint(current_blueprint_id) else tuple()
        for sibling_blueprint_id in sibling_ids:
            attempt_started_at = time.perf_counter()
            sibling_blueprint = get_blueprint(sibling_blueprint_id)
            if sibling_blueprint is None:
                diagnostics["attempts"].append({
                    "phase": "sibling_blueprint_fallback",
                    "blueprint_id": sibling_blueprint_id,
                    "status": "unknown_blueprint",
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                continue
            instantiation = instantiate_blueprint(
                blueprint=sibling_blueprint,
                meal_request=meal_request,
                food_lookup=food_lookup,
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                weekly_food_usage=weekly_food_usage,
                diversity_state=create_diversity_state(),
                variety_seed=variety_seed + 50,
                excluded_food_codes=current_food_codes,
            )
            if instantiation is None:
                diagnostics["attempts"].append({
                    "phase": "sibling_blueprint_fallback",
                    "blueprint_id": sibling_blueprint_id,
                    "status": "instantiation_failed",
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                continue
            candidate_plan = repair_meal_plan(
                blueprint=sibling_blueprint,
                meal=meal,
                meal_request=meal_request,
                instantiation=instantiation,
                food_lookup=food_lookup,
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                weekly_food_usage=weekly_food_usage,
            )
            if candidate_plan is not None:
                candidate_plan["regeneration_difference"] = summarize_visible_difference(
                    current_meal_plan=current_meal_plan,
                    current_food_codes=current_food_codes,
                    candidate_plan=candidate_plan,
                )
                candidate_plan["regeneration_source_blueprint_id"] = current_blueprint_id
                diagnostics["attempts"].append({
                    "phase": "sibling_blueprint_fallback",
                    "blueprint_id": sibling_blueprint_id,
                    "status": "candidate_resolved",
                    "fit_method": candidate_plan.get("portion_fit_method", "exact"),
                    "selected_role_codes": candidate_plan.get("selected_role_codes", {}),
                    "difference": candidate_plan["regeneration_difference"],
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                diagnostics["selected_phase"] = "sibling_blueprint_fallback"
                diagnostics["selected_blueprint_id"] = candidate_plan.get("applied_blueprint_id")
                diagnostics["used_v2"] = True
                diagnostics["returned_candidate"] = True
                diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
                candidate_plan["regeneration_diagnostics"] = diagnostics
                set_last_regeneration_diagnostics(diagnostics)
                return candidate_plan
            diagnostics["attempts"].append({
                "phase": "sibling_blueprint_fallback",
                "blueprint_id": sibling_blueprint_id,
                "status": "portion_fit_failed",
                "selected_role_codes": instantiation.get("selected_role_codes", {}),
                "elapsed_seconds": time.perf_counter() - attempt_started_at,
            })

    diagnostics["fallback_reason"] = "no_v2_regeneration_candidate"
    diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
    set_last_regeneration_diagnostics(diagnostics)
    return None
