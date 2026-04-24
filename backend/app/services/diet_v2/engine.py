"""Main day-generation orchestrator for the diet generation v2 engine."""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from app.schemas.diet import DietMeal
from app.services.diet.candidates import track_food_usage_across_day
from app.services.diet_v2.blueprints import get_blueprint, get_blueprint_visual_family
from app.services.diet_v2.day_planner import plan_day_blueprints, rank_blueprints_for_meal
from app.services.diet_v2.diversity import create_diversity_state, register_instantiated_meal
from app.services.diet_v2.families import get_primary_family_id
from app.services.diet_v2.meal_instantiator import instantiate_blueprint
from app.services.diet_v2.repair import repair_meal_plan_with_diagnostics
from app.services.diet_v2.telemetry import set_last_generation_diagnostics

logger = logging.getLogger(__name__)


def _stable_noise(seed: int, *parts: object) -> float:
    digest = hashlib.blake2b(
        f"{seed}|{'|'.join(str(part) for part in parts)}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") / 2**64


def _build_meal_request(
    *,
    meal: dict[str, Any],
    meal_index: int,
    meals_count: int,
    meal_context: dict[str, Any],
    forced_role_codes: dict[str, str] | None,
    preferred_support_candidates: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    return {
        "meal": DietMeal.model_validate(meal),
        "meal_index": meal_index,
        "meals_count": meals_count,
        "meal_slot": meal_context["meal_slot"],
        "meal_role": meal_context["meal_role"],
        "training_focus": meal_context["training_focus"],
        "forced_role_codes": forced_role_codes or {},
        "preferred_support_candidates": preferred_support_candidates or [],
    }


def generate_day_meal_plans_v2(
    *,
    meal_distribution: dict[str, Any],
    meals_context: list[dict[str, Any]],
    meals_count: int,
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
    forced_role_codes_by_meal: dict[int, dict[str, str]] | None = None,
    preferred_support_candidates_by_meal: dict[int, list[dict[str, Any]]] | None = None,
    variety_seed: int,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    phase_timings: dict[str, float] = {}
    forced_role_codes_by_meal = forced_role_codes_by_meal or {}
    preferred_support_candidates_by_meal = preferred_support_candidates_by_meal or {}
    meal_diagnostics: list[dict[str, Any]] = []
    resolution_summary = {
        "meal_count": 0,
        "resolved_v2_meals": 0,
        "exact_fit_meals": 0,
        "approximate_fit_meals": 0,
        "failed_v2_meals": 0,
        "fallback_triggered": False,
        "fallback_reason": None,
        "fallback_failed_meal_index": None,
    }

    phase_started_at = time.perf_counter()
    meal_requests = [
        _build_meal_request(
            meal=meal,
            meal_index=meal_index,
            meals_count=meals_count,
            meal_context=meals_context[meal_index],
            forced_role_codes=forced_role_codes_by_meal.get(meal_index),
            preferred_support_candidates=preferred_support_candidates_by_meal.get(meal_index),
        )
        for meal_index, meal in enumerate(meal_distribution["meals"])
    ]
    phase_timings["request_build"] = time.perf_counter() - phase_started_at

    phase_started_at = time.perf_counter()
    blueprint_plan = plan_day_blueprints(
        meal_requests=meal_requests,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        variety_seed=variety_seed,
    )
    phase_timings["day_planning"] = time.perf_counter() - phase_started_at

    phase_started_at = time.perf_counter()
    diversity_state = create_diversity_state()
    meal_plans: list[dict[str, Any]] = []
    used_fallback = False

    for meal_request in meal_requests:
        meal_index = meal_request["meal_index"]
        meal_started_at = time.perf_counter()
        candidate_blueprint_ids = list(dict.fromkeys(
            [
                blueprint_plan["assignments"].get(meal_index),
                *blueprint_plan["fallback_blueprints_by_meal"].get(meal_index, []),
            ]
        ))
        if not candidate_blueprint_ids:
            candidate_blueprint_ids = [
                blueprint.id
                for blueprint in rank_blueprints_for_meal(
                    meal_request=meal_request,
                    food_lookup=food_lookup,
                    preference_profile=preference_profile,
                    variety_seed=variety_seed + meal_index,
                    diversity_state=diversity_state,
                )
            ]
        prioritized_blueprint_ids = candidate_blueprint_ids[:4]
        deferred_blueprint_ids = candidate_blueprint_ids[4:]

        resolved_plan: dict[str, Any] | None = None
        resolved_plan_score: float | None = None
        meal_diagnostic = {
            "meal_index": meal_index,
            "meal_slot": meal_request["meal_slot"],
            "meal_role": meal_request["meal_role"],
            "training_focus": meal_request["training_focus"],
            "planner_assignment": blueprint_plan["assignments"].get(meal_index),
            "candidate_blueprints": list(candidate_blueprint_ids),
            "attempts": [],
            "resolved": False,
            "resolved_blueprint_id": None,
            "fit_method": None,
            "failure_reason": None,
            "elapsed_seconds": 0.0,
        }
        resolution_summary["meal_count"] += 1
        attempted_blueprint_ids = prioritized_blueprint_ids or candidate_blueprint_ids
        if not attempted_blueprint_ids:
            attempted_blueprint_ids = candidate_blueprint_ids
        for candidate_rank, blueprint_id in enumerate(attempted_blueprint_ids):
            if not blueprint_id:
                meal_diagnostic["attempts"].append({
                    "blueprint_id": blueprint_id,
                    "status": "missing_blueprint_id",
                    "elapsed_seconds": 0.0,
                })
                continue
            blueprint = get_blueprint(blueprint_id)
            if blueprint is None:
                meal_diagnostic["attempts"].append({
                    "blueprint_id": blueprint_id,
                    "status": "unknown_blueprint",
                    "elapsed_seconds": 0.0,
                })
                continue
            if (
                not blueprint.allow_repeat
                and diversity_state["blueprint_counts"].get(blueprint.id, 0) >= blueprint.daily_max_repetitions
            ):
                meal_diagnostic["attempts"].append({
                    "blueprint_id": blueprint_id,
                    "status": "skipped_repeat_limit",
                    "elapsed_seconds": 0.0,
                })
                continue
            for instantiation_variant, instantiation_seed_offset in enumerate((0, 53, 97)):
                attempt_started_at = time.perf_counter()
                instantiation = instantiate_blueprint(
                    blueprint=blueprint,
                    meal_request=meal_request,
                    food_lookup=food_lookup,
                    preference_profile=preference_profile,
                    daily_food_usage=daily_food_usage,
                    weekly_food_usage=weekly_food_usage,
                    diversity_state=diversity_state,
                    variety_seed=variety_seed + meal_index + (candidate_rank * 17) + instantiation_seed_offset,
                )
                if instantiation is None:
                    meal_diagnostic["attempts"].append({
                        "blueprint_id": blueprint_id,
                        "instantiation_variant": instantiation_variant,
                        "status": "instantiation_failed",
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue
                candidate_plan, repair_attempts = repair_meal_plan_with_diagnostics(
                    blueprint=blueprint,
                    meal=meal_request["meal"],
                    meal_request=meal_request,
                    instantiation=instantiation,
                    food_lookup=food_lookup,
                    preference_profile=preference_profile,
                    daily_food_usage=daily_food_usage,
                    weekly_food_usage=weekly_food_usage,
                )
                if candidate_plan is None:
                    meal_diagnostic["attempts"].append({
                        "blueprint_id": blueprint_id,
                        "instantiation_variant": instantiation_variant,
                        "status": "no_strict_candidate",
                        "selected_role_codes": instantiation.get("selected_role_codes", {}),
                        "repair_attempts": repair_attempts,
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    continue
                nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
                selection_noise = _stable_noise(
                    variety_seed,
                    meal_index,
                    blueprint.id,
                    instantiation_variant,
                    candidate_plan.get("selected_role_codes", {}),
                )
                if meal_request["meal_role"] == "breakfast":
                    planner_rank_penalty = candidate_rank * 0.72
                else:
                    planner_rank_penalty = candidate_rank * (0.46 if meal_request["meal_slot"] == "early" else 0.16)
                breakfast_structure_penalty = 0.0
                candidate_visual_family = str(candidate_plan.get("applied_blueprint_visual_family") or "")
                candidate_visual_continuity = str(
                    candidate_plan.get("applied_blueprint_visual_continuity_group") or ""
                )
                continuity_bias = 0.0
                if meal_request["meal_role"] == "breakfast":
                    if candidate_visual_family == "cold_snack":
                        breakfast_structure_penalty += 0.44
                    elif candidate_visual_family == "breakfast_bowl":
                        breakfast_structure_penalty += 0.24
                    elif candidate_visual_family == "egg_breakfast_plate":
                        breakfast_structure_penalty -= 0.12
                    elif candidate_visual_family == "breakfast_wrap":
                        breakfast_structure_penalty -= 0.16
                    elif candidate_visual_family == "breakfast_toast":
                        breakfast_structure_penalty -= 0.18
                    elif candidate_visual_family == "stacked_snack":
                        breakfast_structure_penalty += 0.08
                elif meal_request["meal_slot"] in {"main", "late"}:
                    repeated_main_continuity = int(
                        diversity_state["visual_continuity_group_counts"].get(candidate_visual_continuity, 0)
                    )
                    if candidate_visual_continuity == "protein_starch_veg_meal":
                        continuity_bias += repeated_main_continuity * 0.32
                        if repeated_main_continuity:
                            continuity_bias += 0.18
                    elif (
                        candidate_visual_continuity == "bread_based_meal"
                        and diversity_state["visual_continuity_group_counts"].get("protein_starch_veg_meal", 0) > 0
                    ):
                        continuity_bias -= 0.12
                candidate_total_score = (
                    float(nutrition_validation.get("normalized_error_score") or 0.0) * 3.5
                    + float(candidate_plan.get("score") or 0.0)
                    + float(instantiation.get("blueprint_diversity_penalty") or 0.0)
                    + planner_rank_penalty
                    + breakfast_structure_penalty
                    + continuity_bias
                    - (selection_noise * (1.6 if meal_request["meal_slot"] == "early" else 0.15))
                )
                meal_diagnostic["attempts"].append({
                    "blueprint_id": blueprint_id,
                    "instantiation_variant": instantiation_variant,
                    "status": "candidate_resolved",
                    "fit_method": candidate_plan.get("portion_fit_method", "exact"),
                    "selected_role_codes": candidate_plan.get("selected_role_codes", {}),
                    "score": float(candidate_plan.get("score") or 0.0),
                    "candidate_total_score": candidate_total_score,
                    "within_tolerance": bool(nutrition_validation.get("within_tolerance")),
                    "out_of_tolerance_fields": list(nutrition_validation.get("out_of_tolerance_fields") or []),
                    "normalized_error_score": float(nutrition_validation.get("normalized_error_score") or 0.0),
                    "repair_attempts": repair_attempts,
                    "elapsed_seconds": time.perf_counter() - attempt_started_at,
                })
                if resolved_plan is None or resolved_plan_score is None or candidate_total_score < resolved_plan_score:
                    resolved_plan = candidate_plan
                    resolved_plan_score = candidate_total_score

        if resolved_plan is None and deferred_blueprint_ids:
            for deferred_offset, blueprint_id in enumerate(deferred_blueprint_ids, start=len(attempted_blueprint_ids)):
                if not blueprint_id:
                    meal_diagnostic["attempts"].append({
                        "blueprint_id": blueprint_id,
                        "status": "missing_blueprint_id",
                        "elapsed_seconds": 0.0,
                    })
                    continue
                blueprint = get_blueprint(blueprint_id)
                if blueprint is None:
                    meal_diagnostic["attempts"].append({
                        "blueprint_id": blueprint_id,
                        "status": "unknown_blueprint",
                        "elapsed_seconds": 0.0,
                    })
                    continue
                if (
                    not blueprint.allow_repeat
                    and diversity_state["blueprint_counts"].get(blueprint.id, 0) >= blueprint.daily_max_repetitions
                ):
                    meal_diagnostic["attempts"].append({
                        "blueprint_id": blueprint_id,
                        "status": "skipped_repeat_limit",
                        "elapsed_seconds": 0.0,
                    })
                    continue
                for instantiation_variant, instantiation_seed_offset in enumerate((0, 53, 97)):
                    attempt_started_at = time.perf_counter()
                    instantiation = instantiate_blueprint(
                        blueprint=blueprint,
                        meal_request=meal_request,
                        food_lookup=food_lookup,
                        preference_profile=preference_profile,
                        daily_food_usage=daily_food_usage,
                        weekly_food_usage=weekly_food_usage,
                        diversity_state=diversity_state,
                        variety_seed=(
                            variety_seed
                            + meal_index
                            + (deferred_offset * 17)
                            + instantiation_seed_offset
                        ),
                    )
                    if instantiation is None:
                        meal_diagnostic["attempts"].append({
                            "blueprint_id": blueprint_id,
                            "instantiation_variant": instantiation_variant,
                            "status": "instantiation_failed",
                            "elapsed_seconds": time.perf_counter() - attempt_started_at,
                        })
                        continue
                    candidate_plan, repair_attempts = repair_meal_plan_with_diagnostics(
                        blueprint=blueprint,
                        meal=meal_request["meal"],
                        meal_request=meal_request,
                        instantiation=instantiation,
                        food_lookup=food_lookup,
                        preference_profile=preference_profile,
                        daily_food_usage=daily_food_usage,
                        weekly_food_usage=weekly_food_usage,
                    )
                    if candidate_plan is None:
                        meal_diagnostic["attempts"].append({
                            "blueprint_id": blueprint_id,
                            "instantiation_variant": instantiation_variant,
                            "status": "no_strict_candidate",
                            "selected_role_codes": instantiation.get("selected_role_codes", {}),
                            "repair_attempts": repair_attempts,
                            "elapsed_seconds": time.perf_counter() - attempt_started_at,
                        })
                        continue
                    nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
                    selection_noise = _stable_noise(
                        variety_seed,
                        meal_index,
                        blueprint.id,
                        instantiation_variant,
                        candidate_plan.get("selected_role_codes", {}),
                    )
                    if meal_request["meal_role"] == "breakfast":
                        planner_rank_penalty = deferred_offset * 0.72
                    else:
                        planner_rank_penalty = deferred_offset * (
                            0.46 if meal_request["meal_slot"] == "early" else 0.16
                        )
                    breakfast_structure_penalty = 0.0
                    candidate_visual_family = str(candidate_plan.get("applied_blueprint_visual_family") or "")
                    candidate_visual_continuity = str(
                        candidate_plan.get("applied_blueprint_visual_continuity_group") or ""
                    )
                    continuity_bias = 0.0
                    if meal_request["meal_role"] == "breakfast":
                        if candidate_visual_family == "cold_snack":
                            breakfast_structure_penalty += 0.44
                        elif candidate_visual_family == "breakfast_bowl":
                            breakfast_structure_penalty += 0.24
                        elif candidate_visual_family == "egg_breakfast_plate":
                            breakfast_structure_penalty -= 0.12
                        elif candidate_visual_family == "breakfast_wrap":
                            breakfast_structure_penalty -= 0.16
                        elif candidate_visual_family == "breakfast_toast":
                            breakfast_structure_penalty -= 0.18
                        elif candidate_visual_family == "stacked_snack":
                            breakfast_structure_penalty += 0.08
                    elif meal_request["meal_slot"] in {"main", "late"}:
                        repeated_main_continuity = int(
                            diversity_state["visual_continuity_group_counts"].get(candidate_visual_continuity, 0)
                        )
                        if candidate_visual_continuity == "protein_starch_veg_meal":
                            continuity_bias += repeated_main_continuity * 0.32
                            if repeated_main_continuity:
                                continuity_bias += 0.18
                        elif (
                            candidate_visual_continuity == "bread_based_meal"
                            and diversity_state["visual_continuity_group_counts"].get(
                                "protein_starch_veg_meal",
                                0,
                            ) > 0
                        ):
                            continuity_bias -= 0.12
                    candidate_total_score = (
                        float(nutrition_validation.get("normalized_error_score") or 0.0) * 3.5
                        + float(candidate_plan.get("score") or 0.0)
                        + float(instantiation.get("blueprint_diversity_penalty") or 0.0)
                        + planner_rank_penalty
                        + breakfast_structure_penalty
                        + continuity_bias
                        - (selection_noise * (1.6 if meal_request["meal_slot"] == "early" else 0.15))
                    )
                    meal_diagnostic["attempts"].append({
                        "blueprint_id": blueprint_id,
                        "instantiation_variant": instantiation_variant,
                        "status": "candidate_resolved",
                        "fit_method": candidate_plan.get("portion_fit_method", "exact"),
                        "selected_role_codes": candidate_plan.get("selected_role_codes", {}),
                        "score": float(candidate_plan.get("score") or 0.0),
                        "candidate_total_score": candidate_total_score,
                        "within_tolerance": bool(nutrition_validation.get("within_tolerance")),
                        "out_of_tolerance_fields": list(nutrition_validation.get("out_of_tolerance_fields") or []),
                        "normalized_error_score": float(nutrition_validation.get("normalized_error_score") or 0.0),
                        "repair_attempts": repair_attempts,
                        "elapsed_seconds": time.perf_counter() - attempt_started_at,
                    })
                    if resolved_plan is None or resolved_plan_score is None or candidate_total_score < resolved_plan_score:
                        resolved_plan = candidate_plan
                        resolved_plan_score = candidate_total_score

        if resolved_plan is None:
            used_fallback = True
            resolution_summary["failed_v2_meals"] += 1
            resolution_summary["fallback_triggered"] = True
            resolution_summary["fallback_reason"] = "unresolved_meal_after_blueprint_attempts"
            resolution_summary["fallback_failed_meal_index"] = meal_index
            meal_diagnostic["failure_reason"] = "unresolved_meal_after_blueprint_attempts"
            meal_diagnostic["elapsed_seconds"] = time.perf_counter() - meal_started_at
            meal_diagnostics.append(meal_diagnostic)
            break

        meal_diagnostic["resolved"] = True
        meal_diagnostic["resolved_blueprint_id"] = resolved_plan.get("applied_blueprint_id")
        meal_diagnostic["fit_method"] = resolved_plan.get("portion_fit_method", "exact")
        meal_diagnostic["selected_role_codes"] = dict(resolved_plan.get("selected_role_codes", {}))
        meal_diagnostic["elapsed_seconds"] = time.perf_counter() - meal_started_at
        meal_diagnostics.append(meal_diagnostic)
        resolution_summary["resolved_v2_meals"] += 1
        if meal_diagnostic["fit_method"] == "approximate_v2":
            resolution_summary["approximate_fit_meals"] += 1
        else:
            resolution_summary["exact_fit_meals"] += 1
        resolved_blueprint = get_blueprint(str(resolved_plan.get("applied_blueprint_id") or ""))
        protein_family = get_primary_family_id(
            food_lookup[resolved_plan["selected_role_codes"]["protein"]],
            role="protein",
        )
        carb_family = get_primary_family_id(
            food_lookup[resolved_plan["selected_role_codes"]["carb"]],
            role="carb",
        )
        fat_family = get_primary_family_id(
            food_lookup[resolved_plan["selected_role_codes"]["fat"]],
            role="fat",
        )
        support_families = [
            get_primary_family_id(
                food_lookup[support_food["food_code"]],
                role=support_food["role"],
            )
            for support_food in resolved_plan.get("support_food_specs", [])
            if support_food["food_code"] in food_lookup
        ]
        register_instantiated_meal(
            diversity_state,
            blueprint_id=str(resolved_plan.get("applied_blueprint_id") or ""),
            structural_family=str(resolved_plan.get("applied_blueprint_family") or ""),
            visual_family=str(
                resolved_plan.get("applied_blueprint_visual_family")
                or (
                    get_blueprint_visual_family(
                        resolved_blueprint,
                        meal_slot=meal_request["meal_slot"],
                    )
                    if resolved_blueprint is not None
                    else ""
                )
            ),
            visual_continuity_group=str(
                resolved_plan.get("applied_blueprint_visual_continuity_group")
                or (resolved_blueprint.visual_continuity_group if resolved_blueprint is not None else "")
            ),
            style_tags=resolved_plan.get("applied_blueprint_style_tags", []),
            meal_slot=meal_request["meal_slot"],
            meal_role=meal_request["meal_role"],
            protein_family=protein_family,
            carb_family=carb_family,
            fat_family=fat_family,
            support_families=support_families,
            selected_role_codes=resolved_plan["selected_role_codes"],
        )
        meal_plans.append(resolved_plan)
        if daily_food_usage is not None:
            track_food_usage_across_day(daily_food_usage, resolved_plan)

    phase_timings["instantiation_and_fit"] = time.perf_counter() - phase_started_at
    phase_timings["total"] = time.perf_counter() - started_at
    diagnostics_payload = {
        "phase_timings": phase_timings,
        "resolution_summary": resolution_summary,
        "meal_diagnostics": meal_diagnostics,
        "generated_meal_summaries": [
            {
                "meal_index": index,
                "meal_slot": meal_requests[index]["meal_slot"] if index < len(meal_requests) else None,
                "meal_role": meal_requests[index]["meal_role"] if index < len(meal_requests) else None,
                "applied_blueprint_id": meal_plan.get("applied_blueprint_id"),
                "applied_blueprint_family": meal_plan.get("applied_blueprint_family"),
                "applied_blueprint_visual_family": meal_plan.get("applied_blueprint_visual_family"),
                "applied_blueprint_visual_continuity_group": meal_plan.get("applied_blueprint_visual_continuity_group"),
                "fit_method": meal_plan.get("portion_fit_method", "exact"),
                "selected_role_codes": dict(meal_plan.get("selected_role_codes", {})),
                "support_food_specs": list(meal_plan.get("support_food_specs", [])),
            }
            for index, meal_plan in enumerate(meal_plans)
        ],
        "planner_assignments": blueprint_plan.get("assignments", {}),
        "strict_blueprints_by_meal": blueprint_plan.get("strict_blueprints_by_meal", {}),
        "fallback_blueprints_by_meal": blueprint_plan.get("fallback_blueprints_by_meal", {}),
        "generated_meal_count": len(meal_plans),
        "used_legacy_fallback": used_fallback,
    }
    set_last_generation_diagnostics(diagnostics_payload)

    logger.info(
        "Diet v2 timings request_build=%.4fs day_planning=%.4fs instantiation=%.4fs total=%.4fs meals=%s fallback=%s exact=%s approx=%s failed=%s reason=%s",
        phase_timings.get("request_build", 0.0),
        phase_timings.get("day_planning", 0.0),
        phase_timings.get("instantiation_and_fit", 0.0),
        phase_timings["total"],
        len(meal_plans),
        used_fallback,
        resolution_summary["exact_fit_meals"],
        resolution_summary["approximate_fit_meals"],
        resolution_summary["failed_v2_meals"],
        resolution_summary["fallback_reason"],
    )

    return {
        "meal_plans": meal_plans,
        "phase_timings": phase_timings,
        "used_legacy_fallback": used_fallback,
        "diagnostics": diagnostics_payload,
    }
