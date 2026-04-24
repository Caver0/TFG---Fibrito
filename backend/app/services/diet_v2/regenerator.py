"""Meal regeneration v2 for the diet generation engine."""
from __future__ import annotations

import time
from typing import Any

from app.services.diet.candidates import get_meal_structure_signature
from app.services.diet_v2.blueprints import get_blueprint, get_blueprint_visual_family
from app.services.diet_v2.day_planner import rank_blueprints_for_meal
from app.services.diet_v2.diversity import create_diversity_state, register_instantiated_meal
from app.services.diet_v2.meal_instantiator import instantiate_blueprint
from app.services.diet_v2.repair import repair_regenerated_meal_plan
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
    current_visual_family = str((current_meal_plan or {}).get("applied_blueprint_visual_family") or "")
    candidate_visual_family = str(candidate_plan.get("applied_blueprint_visual_family") or "")
    current_visual_continuity = str((current_meal_plan or {}).get("applied_blueprint_visual_continuity_group") or "")
    candidate_visual_continuity = str(candidate_plan.get("applied_blueprint_visual_continuity_group") or "")
    return {
        "visible_change_count": visible_change_count,
        "changed_roles": changed_roles,
        "same_visible_structure": current_structure == candidate_structure if current_structure else False,
        "structure_changed": current_structure != candidate_structure if current_structure else True,
        "visual_family_changed": bool(current_visual_family) and current_visual_family != candidate_visual_family,
        "visual_continuity_changed": bool(current_visual_continuity) and current_visual_continuity != candidate_visual_continuity,
    }


def _build_regeneration_candidate_ranking(
    *,
    candidate_plan: dict[str, Any],
    difference: dict[str, Any],
    current_blueprint_id: str | None,
) -> tuple[float, ...]:
    nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
    blueprint_changed = int(str(candidate_plan.get("applied_blueprint_id") or "") != str(current_blueprint_id or ""))
    visual_family_changed = int(difference["visual_family_changed"])
    visual_continuity_changed = int(difference["visual_continuity_changed"])
    changed_primary = int(any(role in difference["changed_roles"] for role in ("protein", "carb")))
    return (
        0.0 if nutrition_validation.get("within_tolerance") else 1.0,
        float(nutrition_validation.get("max_overflow_ratio") or 0.0),
        float(nutrition_validation.get("normalized_overflow_score") or 0.0),
        float(nutrition_validation.get("normalized_error_score") or 0.0),
        -float(visual_family_changed),
        -float(visual_continuity_changed),
        -float(blueprint_changed),
        -float(changed_primary),
        -float(difference["visible_change_count"]),
        0.0 if candidate_plan.get("portion_fit_method", "exact") == "exact" else 1.0,
        float(candidate_plan.get("score") or 0.0),
    )


def _build_regeneration_residual_reason(candidate_plan: dict[str, Any]) -> dict[str, Any]:
    nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
    existing_reason = nutrition_validation.get("residual_reason")
    if existing_reason:
        return dict(existing_reason)
    return {
        "code": "strict_tolerance_unreachable_after_regeneration_search",
        "out_of_tolerance_fields": list(nutrition_validation.get("out_of_tolerance_fields") or []),
        "problem_roles": list(nutrition_validation.get("problem_roles") or []),
        "bound_signals": list(nutrition_validation.get("bound_signals") or []),
    }


def _build_regeneration_diversity_state(
    *,
    current_meal_plan: dict[str, Any] | None,
    current_blueprint_id: str | None,
    meal_slot: str,
    meal_role: str,
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    diversity_state = create_diversity_state()
    if not current_meal_plan or not current_blueprint_id:
        return diversity_state

    blueprint = get_blueprint(current_blueprint_id)
    role_codes = current_meal_plan.get("selected_role_codes", {})
    if blueprint is None or not role_codes:
        return diversity_state

    protein_code = str(role_codes.get("protein") or "").strip()
    carb_code = str(role_codes.get("carb") or "").strip()
    fat_code = str(role_codes.get("fat") or "").strip()
    if protein_code not in food_lookup or carb_code not in food_lookup or fat_code not in food_lookup:
        return diversity_state

    support_families = [
        get_primary_family_id(
            food_lookup[support_food["food_code"]],
            role=support_food["role"],
        )
        for support_food in current_meal_plan.get("support_food_specs", [])
        if support_food["food_code"] in food_lookup
    ]
    register_instantiated_meal(
        diversity_state,
        blueprint_id=current_blueprint_id,
        structural_family=str(current_meal_plan.get("applied_blueprint_family") or blueprint.structural_family),
        visual_family=str(
            current_meal_plan.get("applied_blueprint_visual_family")
            or get_blueprint_visual_family(blueprint, meal_slot=meal_slot)
        ),
        visual_continuity_group=str(
            current_meal_plan.get("applied_blueprint_visual_continuity_group")
            or blueprint.visual_continuity_group
        ),
        style_tags=current_meal_plan.get("applied_blueprint_style_tags", list(blueprint.style_tags)),
        meal_slot=meal_slot,
        meal_role=meal_role,
        protein_family=get_primary_family_id(food_lookup[protein_code], role="protein"),
        carb_family=get_primary_family_id(food_lookup[carb_code], role="carb"),
        fat_family=get_primary_family_id(food_lookup[fat_code], role="fat"),
        support_families=support_families,
        selected_role_codes=role_codes,
    )
    return diversity_state


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
    if current_meal_plan and current_blueprint_id:
        current_blueprint = get_blueprint(current_blueprint_id)
        if current_blueprint is not None:
            current_meal_plan = {
                **current_meal_plan,
                "applied_blueprint_visual_family": (
                    current_meal_plan.get("applied_blueprint_visual_family")
                    or get_blueprint_visual_family(current_blueprint, meal_slot=meal_slot)
                ),
                "applied_blueprint_visual_continuity_group": (
                    current_meal_plan.get("applied_blueprint_visual_continuity_group")
                    or current_blueprint.visual_continuity_group
                ),
            }
    regeneration_diversity_state = _build_regeneration_diversity_state(
        current_meal_plan=current_meal_plan,
        current_blueprint_id=current_blueprint_id,
        meal_slot=meal_slot,
        meal_role=meal_role,
        food_lookup=food_lookup,
    )
    ranked_blueprints = rank_blueprints_for_meal(
        meal_request=meal_request,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        variety_seed=variety_seed,
        diversity_state=regeneration_diversity_state,
    )

    best_candidate: dict[str, Any] | None = None
    best_difference: tuple[float, ...] | None = None
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
        "accepted_with_residual_error": False,
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
            if not phase["allow_same_blueprint"] and blueprint.id == current_blueprint_id:
                diagnostics["attempts"].append({
                    "phase": phase["name"],
                    "blueprint_id": blueprint.id,
                    "status": "skipped_same_blueprint",
                    "elapsed_seconds": 0.0,
                })
                continue
            for instantiation_variant, instantiation_seed_offset in enumerate((0, 97)):
                attempt_started_at = time.perf_counter()
                instantiation = instantiate_blueprint(
                    blueprint=blueprint,
                    meal_request=meal_request,
                    food_lookup=food_lookup,
                    preference_profile=preference_profile,
                    daily_food_usage=daily_food_usage,
                    weekly_food_usage=weekly_food_usage,
                    diversity_state=regeneration_diversity_state,
                    variety_seed=variety_seed + phase_index + instantiation_seed_offset,
                    excluded_food_codes=phase["excluded_food_codes"],
                )
                if instantiation is None:
                    diagnostics["attempts"].append({
                        "phase": phase["name"],
                        "blueprint_id": blueprint.id,
                        "instantiation_variant": instantiation_variant,
                        "status": "instantiation_failed",
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue
                candidate_plan, repair_attempts = repair_regenerated_meal_plan(
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
                        "instantiation_variant": instantiation_variant,
                        "status": "portion_fit_failed",
                        "selected_role_codes": instantiation.get("selected_role_codes", {}),
                        "repair_attempts": repair_attempts,
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue

                difference = summarize_visible_difference(
                    current_meal_plan=current_meal_plan,
                    current_food_codes=current_food_codes,
                    candidate_plan=candidate_plan,
                )
                nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
                blueprint_changed = int(str(candidate_plan.get("applied_blueprint_id") or "") != str(current_blueprint_id or ""))
                visual_family_changed = int(difference["visual_family_changed"])
                changed_primary = int(any(role in difference["changed_roles"] for role in ("protein", "carb")))
                ranking = _build_regeneration_candidate_ranking(
                    candidate_plan=candidate_plan,
                    difference=difference,
                    current_blueprint_id=current_blueprint_id,
                )
                diagnostics["attempts"].append({
                    "phase": phase["name"],
                    "blueprint_id": blueprint.id,
                    "instantiation_variant": instantiation_variant,
                    "status": "candidate_resolved"
                    if nutrition_validation.get("within_tolerance")
                    else "candidate_rejected_outside_tolerance",
                    "fit_method": candidate_plan.get("portion_fit_method", "exact"),
                    "selected_role_codes": candidate_plan.get("selected_role_codes", {}),
                    "difference": difference,
                    "within_tolerance": bool(nutrition_validation.get("within_tolerance")),
                    "out_of_tolerance_fields": list(nutrition_validation.get("out_of_tolerance_fields") or []),
                    "normalized_overflow_score": float(nutrition_validation.get("normalized_overflow_score") or 0.0),
                    "repair_attempts": repair_attempts,
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                if best_candidate is None or best_difference is None or ranking < best_difference:
                    best_candidate = candidate_plan
                    best_difference = ranking
                if (
                    bool(nutrition_validation.get("within_tolerance"))
                    and difference["visible_change_count"] >= phase["min_visible_difference"]
                    and (
                        visual_family_changed
                        or blueprint_changed
                        or changed_primary
                        or len(difference["changed_roles"]) >= 2
                    )
                ):
                    candidate_plan["regeneration_difference"] = difference
                    candidate_plan["regeneration_source_blueprint_id"] = current_blueprint_id
                    candidate_plan["nutrition_validation"]["accepted_with_residual_error"] = False
                    diagnostics["selected_phase"] = phase["name"]
                    diagnostics["selected_blueprint_id"] = candidate_plan.get("applied_blueprint_id")
                    diagnostics["used_v2"] = True
                    diagnostics["returned_candidate"] = True
                    diagnostics["accepted_with_residual_error"] = False
                    diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
                    candidate_plan["regeneration_diagnostics"] = diagnostics
                    set_last_regeneration_diagnostics(diagnostics)
                    return candidate_plan

    if current_blueprint_id:
        sibling_ids = tuple(get_blueprint(current_blueprint_id).sibling_blueprints) if get_blueprint(current_blueprint_id) else tuple()
        for sibling_blueprint_id in sibling_ids:
            sibling_blueprint = get_blueprint(sibling_blueprint_id)
            if sibling_blueprint is None:
                diagnostics["attempts"].append({
                    "phase": "sibling_blueprint_fallback",
                    "blueprint_id": sibling_blueprint_id,
                    "status": "unknown_blueprint",
                    "elapsed_seconds": 0.0,
                })
                continue
            for instantiation_variant, instantiation_seed_offset in enumerate((50, 147)):
                attempt_started_at = time.perf_counter()
                instantiation = instantiate_blueprint(
                    blueprint=sibling_blueprint,
                    meal_request=meal_request,
                    food_lookup=food_lookup,
                    preference_profile=preference_profile,
                    daily_food_usage=daily_food_usage,
                    weekly_food_usage=weekly_food_usage,
                    diversity_state=regeneration_diversity_state,
                    variety_seed=variety_seed + instantiation_seed_offset,
                    excluded_food_codes=current_food_codes,
                )
                if instantiation is None:
                    diagnostics["attempts"].append({
                        "phase": "sibling_blueprint_fallback",
                        "blueprint_id": sibling_blueprint_id,
                        "instantiation_variant": instantiation_variant,
                        "status": "instantiation_failed",
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue
                candidate_plan, repair_attempts = repair_regenerated_meal_plan(
                    blueprint=sibling_blueprint,
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
                        "phase": "sibling_blueprint_fallback",
                        "blueprint_id": sibling_blueprint_id,
                        "instantiation_variant": instantiation_variant,
                        "status": "portion_fit_failed",
                        "selected_role_codes": instantiation.get("selected_role_codes", {}),
                        "repair_attempts": repair_attempts,
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue

                difference = summarize_visible_difference(
                    current_meal_plan=current_meal_plan,
                    current_food_codes=current_food_codes,
                    candidate_plan=candidate_plan,
                )
                nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
                ranking = _build_regeneration_candidate_ranking(
                    candidate_plan=candidate_plan,
                    difference=difference,
                    current_blueprint_id=current_blueprint_id,
                )
                diagnostics["attempts"].append({
                    "phase": "sibling_blueprint_fallback",
                    "blueprint_id": sibling_blueprint_id,
                    "instantiation_variant": instantiation_variant,
                    "status": "candidate_resolved"
                    if nutrition_validation.get("within_tolerance")
                    else "candidate_rejected_outside_tolerance",
                    "fit_method": candidate_plan.get("portion_fit_method", "exact"),
                    "selected_role_codes": candidate_plan.get("selected_role_codes", {}),
                    "difference": difference,
                    "within_tolerance": bool(nutrition_validation.get("within_tolerance")),
                    "out_of_tolerance_fields": list(nutrition_validation.get("out_of_tolerance_fields") or []),
                    "normalized_overflow_score": float(nutrition_validation.get("normalized_overflow_score") or 0.0),
                    "repair_attempts": repair_attempts,
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                if best_candidate is None or best_difference is None or ranking < best_difference:
                    best_candidate = candidate_plan
                    best_difference = ranking
                if nutrition_validation.get("within_tolerance"):
                    candidate_plan["regeneration_difference"] = difference
                    candidate_plan["regeneration_source_blueprint_id"] = current_blueprint_id
                    candidate_plan["nutrition_validation"]["accepted_with_residual_error"] = False
                    candidate_plan["accepted_with_residual_error"] = False
                    diagnostics["selected_phase"] = "sibling_blueprint_fallback"
                    diagnostics["selected_blueprint_id"] = candidate_plan.get("applied_blueprint_id")
                    diagnostics["used_v2"] = True
                    diagnostics["returned_candidate"] = True
                    diagnostics["accepted_with_residual_error"] = False
                    diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
                    candidate_plan["regeneration_diagnostics"] = diagnostics
                    set_last_regeneration_diagnostics(diagnostics)
                    return candidate_plan

    if best_candidate is None or not best_candidate.get("nutrition_validation", {}).get("within_tolerance"):
        rescue_blueprints = ranked_blueprints[: min(len(ranked_blueprints), 8)]
        for blueprint in rescue_blueprints:
            for instantiation_variant, instantiation_seed_offset in enumerate((193, 389)):
                attempt_started_at = time.perf_counter()
                instantiation = instantiate_blueprint(
                    blueprint=blueprint,
                    meal_request=meal_request,
                    food_lookup=food_lookup,
                    preference_profile=preference_profile,
                    daily_food_usage=daily_food_usage,
                    weekly_food_usage=weekly_food_usage,
                    diversity_state=regeneration_diversity_state,
                    variety_seed=variety_seed + instantiation_seed_offset,
                    excluded_food_codes=set(),
                )
                if instantiation is None:
                    diagnostics["attempts"].append({
                        "phase": "nutrition_rescue",
                        "blueprint_id": blueprint.id,
                        "instantiation_variant": instantiation_variant,
                        "status": "instantiation_failed",
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue
                candidate_plan, repair_attempts = repair_regenerated_meal_plan(
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
                        "phase": "nutrition_rescue",
                        "blueprint_id": blueprint.id,
                        "instantiation_variant": instantiation_variant,
                        "status": "portion_fit_failed",
                        "selected_role_codes": instantiation.get("selected_role_codes", {}),
                        "repair_attempts": repair_attempts,
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue

                difference = summarize_visible_difference(
                    current_meal_plan=current_meal_plan,
                    current_food_codes=current_food_codes,
                    candidate_plan=candidate_plan,
                )
                nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
                ranking = _build_regeneration_candidate_ranking(
                    candidate_plan=candidate_plan,
                    difference=difference,
                    current_blueprint_id=current_blueprint_id,
                )
                diagnostics["attempts"].append({
                    "phase": "nutrition_rescue",
                    "blueprint_id": blueprint.id,
                    "instantiation_variant": instantiation_variant,
                    "status": "candidate_resolved"
                    if nutrition_validation.get("within_tolerance")
                    else "candidate_rejected_outside_tolerance",
                    "fit_method": candidate_plan.get("portion_fit_method", "exact"),
                    "selected_role_codes": candidate_plan.get("selected_role_codes", {}),
                    "difference": difference,
                    "within_tolerance": bool(nutrition_validation.get("within_tolerance")),
                    "out_of_tolerance_fields": list(nutrition_validation.get("out_of_tolerance_fields") or []),
                    "normalized_overflow_score": float(nutrition_validation.get("normalized_overflow_score") or 0.0),
                    "repair_attempts": repair_attempts,
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                if best_candidate is None or best_difference is None or ranking < best_difference:
                    best_candidate = candidate_plan
                    best_difference = ranking
                if (
                    nutrition_validation.get("within_tolerance")
                    and (
                        difference["visible_change_count"] >= 1
                        or bool(difference["changed_roles"])
                        or str(candidate_plan.get("applied_blueprint_id") or "") != str(current_blueprint_id or "")
                    )
                ):
                    candidate_plan["regeneration_difference"] = difference
                    candidate_plan["regeneration_source_blueprint_id"] = current_blueprint_id
                    candidate_plan["nutrition_validation"]["accepted_with_residual_error"] = False
                    candidate_plan["accepted_with_residual_error"] = False
                    diagnostics["selected_phase"] = "nutrition_rescue"
                    diagnostics["selected_blueprint_id"] = candidate_plan.get("applied_blueprint_id")
                    diagnostics["used_v2"] = True
                    diagnostics["returned_candidate"] = True
                    diagnostics["accepted_with_residual_error"] = False
                    diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
                    candidate_plan["regeneration_diagnostics"] = diagnostics
                    set_last_regeneration_diagnostics(diagnostics)
                    return candidate_plan

    if best_candidate is not None and bool(best_candidate.get("nutrition_validation", {}).get("within_tolerance")):
        nutrition_validation = dict(best_candidate.get("nutrition_validation") or {})
        best_candidate["regeneration_difference"] = summarize_visible_difference(
            current_meal_plan=current_meal_plan,
            current_food_codes=current_food_codes,
            candidate_plan=best_candidate,
        )
        best_candidate["regeneration_source_blueprint_id"] = current_blueprint_id
        best_candidate["nutrition_validation"]["accepted_with_residual_error"] = False
        best_candidate["nutrition_validation"]["residual_reason"] = None
        best_candidate["accepted_with_residual_error"] = False
        diagnostics["selected_phase"] = "best_candidate_after_phases"
        diagnostics["selected_blueprint_id"] = best_candidate.get("applied_blueprint_id")
        diagnostics["used_v2"] = True
        diagnostics["returned_candidate"] = True
        diagnostics["accepted_with_residual_error"] = False
        diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
        best_candidate["regeneration_diagnostics"] = diagnostics
        set_last_regeneration_diagnostics(diagnostics)
        return best_candidate

    diagnostics["fallback_reason"] = (
        "no_v2_regeneration_candidate"
        if best_candidate is None
        else "no_strict_regeneration_candidate"
    )
    if best_candidate is not None:
        diagnostics["best_candidate_rejected"] = {
            "applied_blueprint_id": best_candidate.get("applied_blueprint_id"),
            "selected_role_codes": dict(best_candidate.get("selected_role_codes", {})),
            "nutrition_validation": dict(best_candidate.get("nutrition_validation") or {}),
        }
    diagnostics["elapsed_seconds"] = time.perf_counter() - started_at
    set_last_regeneration_diagnostics(diagnostics)
    return None
