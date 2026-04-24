"""Light repair helpers for the diet generation v2 engine."""
from __future__ import annotations

from typing import Any

from app.services.diet.candidates import is_food_allowed_for_role_and_slot, iter_canonical_food_items
from app.services.diet.solver import get_food_macro_density
from app.services.diet_v2.families import food_matches_allowed_families
from app.services.diet_v2.portion_fitter import finalize_meal_candidate, fit_meal_portions
from app.services.food_preferences_service import is_food_allowed_for_user


def repair_meal_plan(
    *,
    blueprint,
    meal,
    meal_request: dict[str, Any],
    instantiation: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
) -> dict[str, Any] | None:
    candidate_plan, _attempt_logs = repair_meal_plan_with_diagnostics(
        blueprint=blueprint,
        meal=meal,
        meal_request=meal_request,
        instantiation=instantiation,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        daily_food_usage=daily_food_usage,
        weekly_food_usage=weekly_food_usage,
    )
    return candidate_plan


def _build_regeneration_candidate_ranking(candidate_plan: dict[str, Any]) -> tuple[float, ...]:
    nutrition_validation = dict(candidate_plan.get("nutrition_validation") or {})
    return (
        0.0 if nutrition_validation.get("within_tolerance") else 1.0,
        float(nutrition_validation.get("max_overflow_ratio") or 0.0),
        float(nutrition_validation.get("normalized_overflow_score") or 0.0),
        float(nutrition_validation.get("normalized_error_score") or 0.0),
        0.0 if candidate_plan.get("portion_fit_method", "exact") == "exact" else 1.0,
        float(candidate_plan.get("score") or 0.0),
    )


def _build_regeneration_support_variants(
    support_food_specs: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    variants: list[tuple[str, list[dict[str, Any]]]] = [("support:original", list(support_food_specs))]
    halved_supports = [
        {
            **support_food,
            "quantity": max(float(support_food.get("quantity") or 0.0) * 0.5, 0.0),
        }
        for support_food in support_food_specs
        if float(support_food.get("quantity") or 0.0) > 0.0
    ]
    if halved_supports and halved_supports != support_food_specs:
        variants.append(("support:halved", halved_supports))
    if support_food_specs:
        variants.append(("support:none", []))
    return variants


def _rank_candidate_codes_for_role(
    *,
    role: str,
    current_code: str,
    candidate_codes: list[str],
    nutrition_validation: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    current_food = food_lookup.get(current_code)
    normalized_candidates = [
        str(code or "").strip()
        for code in candidate_codes
        if str(code or "").strip() and str(code or "").strip() != current_code
    ]
    if current_food is None or not normalized_candidates:
        return normalized_candidates[:4]

    current_density = get_food_macro_density(current_food)
    current_calorie_density = (
        float(current_density["protein_grams"]) * 4.0
        + float(current_density["fat_grams"]) * 9.0
        + float(current_density["carb_grams"]) * 4.0
    )
    tolerances = dict(nutrition_validation.get("tolerances") or {})
    macro_differences = {
        "protein_grams": float(nutrition_validation.get("protein_difference") or 0.0),
        "carb_grams": float(nutrition_validation.get("carb_difference") or 0.0),
        "fat_grams": float(nutrition_validation.get("fat_difference") or 0.0),
    }
    calorie_difference = float(nutrition_validation.get("calorie_difference") or 0.0)
    dominant_macro_by_role = {
        "protein": "protein_grams",
        "carb": "carb_grams",
        "fat": "fat_grams",
    }

    ranked_candidates: list[tuple[float, int, str]] = []
    for pool_index, candidate_code in enumerate(normalized_candidates):
        candidate_food = food_lookup.get(candidate_code)
        if candidate_food is None:
            continue
        candidate_density = get_food_macro_density(candidate_food)
        candidate_calorie_density = (
            float(candidate_density["protein_grams"]) * 4.0
            + float(candidate_density["fat_grams"]) * 9.0
            + float(candidate_density["carb_grams"]) * 4.0
        )
        score = 0.0
        for macro_field, diff in macro_differences.items():
            tolerance = max(float(tolerances.get(macro_field) or 1.0), 1e-6)
            if abs(diff) <= tolerance:
                continue
            target_direction = -1.0 if diff > 0 else 1.0
            density_delta = float(candidate_density.get(macro_field, 0.0)) - float(current_density.get(macro_field, 0.0))
            macro_weight = abs(diff) / tolerance
            if macro_field == dominant_macro_by_role[role]:
                macro_weight *= 1.6
            score += target_direction * density_delta * macro_weight

        calorie_tolerance = max(float(tolerances.get("calories") or 1.0), 1e-6)
        if abs(calorie_difference) > calorie_tolerance:
            calorie_direction = -1.0 if calorie_difference > 0 else 1.0
            score += (
                calorie_direction
                * (candidate_calorie_density - current_calorie_density)
                * (abs(calorie_difference) / calorie_tolerance)
                * 0.35
            )
        ranked_candidates.append((-score, pool_index, candidate_code))

    ranked_candidates.sort()
    return [candidate_code for _, _, candidate_code in ranked_candidates[:4]]


def _rank_role_replacement_codes(
    *,
    role: str,
    selected_role_codes: dict[str, str],
    role_candidate_pool: dict[str, list[str]],
    nutrition_validation: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    return _rank_candidate_codes_for_role(
        role=role,
        current_code=str(selected_role_codes.get(role) or "").strip(),
        candidate_codes=list(role_candidate_pool.get(role, [])),
        nutrition_validation=nutrition_validation,
        food_lookup=food_lookup,
    )


def _collect_catalog_role_candidates(
    *,
    blueprint,
    role: str,
    meal_slot: str,
    selected_role_codes: dict[str, str],
    nutrition_validation: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
) -> list[str]:
    allowed_families = next(
        (
            component.allowed_families
            for component in blueprint.required_components
            if component.role == role
        ),
        tuple(),
    )
    if not allowed_families:
        return []

    candidate_codes: list[str] = []
    selected_codes = set(selected_role_codes.values())
    for candidate_code, candidate_food in iter_canonical_food_items(food_lookup):
        if candidate_code in selected_codes:
            continue
        if not is_food_allowed_for_role_and_slot(
            candidate_food,
            role=role,
            meal_slot=meal_slot,
        ):
            continue
        if not food_matches_allowed_families(
            candidate_food,
            allowed_families=allowed_families,
            role=role,
        ):
            continue
        if preference_profile:
            allowed, _reasons = is_food_allowed_for_user(candidate_food, preference_profile)
            if not allowed:
                continue
        candidate_codes.append(candidate_code)

    return _rank_candidate_codes_for_role(
        role=role,
        current_code=str(selected_role_codes.get(role) or "").strip(),
        candidate_codes=candidate_codes,
        nutrition_validation=nutrition_validation,
        food_lookup=food_lookup,
    )[:4]


def _collect_macro_rescue_candidates(
    *,
    role: str,
    selected_role_codes: dict[str, str],
    nutrition_validation: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
) -> list[str]:
    candidate_codes: list[str] = []
    selected_codes = set(selected_role_codes.values())
    for candidate_code, candidate_food in iter_canonical_food_items(food_lookup):
        if candidate_code in selected_codes:
            continue
        if preference_profile:
            allowed, _reasons = is_food_allowed_for_user(candidate_food, preference_profile)
            if not allowed:
                continue
        candidate_codes.append(candidate_code)

    return _rank_candidate_codes_for_role(
        role=role,
        current_code=str(selected_role_codes.get(role) or "").strip(),
        candidate_codes=candidate_codes,
        nutrition_validation=nutrition_validation,
        food_lookup=food_lookup,
    )[:2]


def _iter_regeneration_role_variants(
    *,
    selected_role_codes: dict[str, str],
    candidate_codes_by_role: dict[str, list[str]],
    prioritized_roles: list[str],
) -> list[tuple[str, dict[str, str]]]:
    variants: list[tuple[str, dict[str, str]]] = []
    seen_keys: set[tuple[tuple[str, str], ...]] = set()

    def register_variant(label: str, variant_role_codes: dict[str, str]) -> None:
        variant_key = tuple(sorted(variant_role_codes.items()))
        if variant_key in seen_keys or variant_role_codes == selected_role_codes:
            return
        seen_keys.add(variant_key)
        variants.append((label, variant_role_codes))

    ordered_roles = [role for role in prioritized_roles if role in ("protein", "carb", "fat")]
    for fallback_role in ("protein", "carb", "fat"):
        if fallback_role not in ordered_roles:
            ordered_roles.append(fallback_role)

    for role in ordered_roles:
        role_candidates = candidate_codes_by_role.get(role, [])[:4]
        for alternative_code in role_candidates:
            register_variant(
                f"single_role_swap:{role}:{alternative_code}",
                {
                    **selected_role_codes,
                    role: alternative_code,
                },
            )

    if len(ordered_roles) >= 2:
        primary_role = ordered_roles[0]
        secondary_role = ordered_roles[1]
        primary_candidates = candidate_codes_by_role.get(primary_role, [])[:2]
        secondary_candidates = candidate_codes_by_role.get(secondary_role, [])[:2]
        for primary_code in primary_candidates:
            for secondary_code in secondary_candidates:
                register_variant(
                    f"double_role_swap:{primary_role}+{secondary_role}:{primary_code}|{secondary_code}",
                    {
                        **selected_role_codes,
                        primary_role: primary_code,
                        secondary_role: secondary_code,
                    },
                )

    return variants


def repair_regenerated_meal_plan(
    *,
    blueprint,
    meal,
    meal_request: dict[str, Any],
    instantiation: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    attempt_logs: list[dict[str, Any]] = []
    best_candidate: dict[str, Any] | None = None
    best_ranking: tuple[float, ...] | None = None

    def attempt_variant(
        *,
        selected_role_codes: dict[str, str],
        attempt_label: str,
    ) -> dict[str, Any] | None:
        variant_best: dict[str, Any] | None = None
        variant_best_ranking: tuple[float, ...] | None = None
        for support_label, support_variant in _build_regeneration_support_variants(instantiation["support_food_specs"]):
            fitted_solution = fit_meal_portions(
                blueprint=blueprint,
                meal=meal,
                meal_request=meal_request,
                selected_role_codes=selected_role_codes,
                support_food_specs=support_variant,
                role_candidate_pool=instantiation["role_candidate_pool"],
                food_lookup=food_lookup,
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                weekly_food_usage=weekly_food_usage,
            )
            if fitted_solution is None:
                attempt_logs.append({
                    "attempt_label": f"{attempt_label}|{support_label}",
                    "status": "portion_fit_failed",
                    "selected_role_codes": dict(selected_role_codes),
                    "support_food_specs": list(support_variant),
                })
                continue

            finalized_solution = finalize_meal_candidate(
                meal=meal,
                meal_plan=fitted_solution,
                meal_slot=meal_request["meal_slot"],
                meal_role=meal_request["meal_role"],
                food_lookup=food_lookup,
            )
            nutrition_validation = dict(finalized_solution.get("nutrition_validation") or {})
            attempt_logs.append({
                "attempt_label": f"{attempt_label}|{support_label}",
                "status": "candidate_resolved",
                "selected_role_codes": dict(selected_role_codes),
                "support_food_specs": list(finalized_solution.get("support_food_specs") or support_variant),
                "fit_method": finalized_solution.get("portion_fit_method", "exact"),
                "within_tolerance": bool(nutrition_validation.get("within_tolerance")),
                "out_of_tolerance_fields": list(nutrition_validation.get("out_of_tolerance_fields") or []),
                "normalized_overflow_score": float(nutrition_validation.get("normalized_overflow_score") or 0.0),
                "max_overflow_ratio": float(nutrition_validation.get("max_overflow_ratio") or 0.0),
            })
            candidate_ranking = _build_regeneration_candidate_ranking(finalized_solution)
            if variant_best is None or variant_best_ranking is None or candidate_ranking < variant_best_ranking:
                variant_best = finalized_solution
                variant_best_ranking = candidate_ranking
            if nutrition_validation.get("within_tolerance"):
                return finalized_solution
        return variant_best

    initial_candidate = attempt_variant(
        selected_role_codes=dict(instantiation["selected_role_codes"]),
        attempt_label="initial_fit",
    )
    if initial_candidate is not None:
        best_candidate = initial_candidate
        best_ranking = _build_regeneration_candidate_ranking(initial_candidate)
        if initial_candidate["nutrition_validation"]["within_tolerance"]:
            return initial_candidate, attempt_logs

    prioritized_roles = (
        list((best_candidate or {}).get("nutrition_validation", {}).get("problem_roles") or [])
        if best_candidate is not None
        else ["protein", "carb", "fat"]
    )
    candidate_codes_by_role = {
        role: list(dict.fromkeys(
            _rank_role_replacement_codes(
                role=role,
                selected_role_codes=dict(instantiation["selected_role_codes"]),
                role_candidate_pool=instantiation["role_candidate_pool"],
                nutrition_validation=dict((best_candidate or {}).get("nutrition_validation") or {}),
                food_lookup=food_lookup,
            )
            + _collect_catalog_role_candidates(
                blueprint=blueprint,
                role=role,
                meal_slot=meal_request["meal_slot"],
                selected_role_codes=dict(instantiation["selected_role_codes"]),
                nutrition_validation=dict((best_candidate or {}).get("nutrition_validation") or {}),
                food_lookup=food_lookup,
                preference_profile=preference_profile,
            )
            + _collect_macro_rescue_candidates(
                role=role,
                selected_role_codes=dict(instantiation["selected_role_codes"]),
                nutrition_validation=dict((best_candidate or {}).get("nutrition_validation") or {}),
                food_lookup=food_lookup,
                preference_profile=preference_profile,
            )
        ))[:4]
        for role in ("protein", "carb", "fat")
    }
    for attempt_label, variant_role_codes in _iter_regeneration_role_variants(
        selected_role_codes=dict(instantiation["selected_role_codes"]),
        candidate_codes_by_role=candidate_codes_by_role,
        prioritized_roles=prioritized_roles,
    ):
        candidate_plan = attempt_variant(
            selected_role_codes=variant_role_codes,
            attempt_label=attempt_label,
        )
        if candidate_plan is None:
            continue
        candidate_ranking = _build_regeneration_candidate_ranking(candidate_plan)
        if best_candidate is None or best_ranking is None or candidate_ranking < best_ranking:
            best_candidate = candidate_plan
            best_ranking = candidate_ranking
        if candidate_plan["nutrition_validation"]["within_tolerance"]:
            return candidate_plan, attempt_logs

    return None, attempt_logs


def repair_meal_plan_with_diagnostics(
    *,
    blueprint,
    meal,
    meal_request: dict[str, Any],
    instantiation: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, Any] | None,
    weekly_food_usage: dict[str, int] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    return repair_regenerated_meal_plan(
        blueprint=blueprint,
        meal=meal,
        meal_request=meal_request,
        instantiation=instantiation,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        daily_food_usage=daily_food_usage,
        weekly_food_usage=weekly_food_usage,
    )
