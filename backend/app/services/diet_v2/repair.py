"""Light repair helpers for the diet generation v2 engine."""
from __future__ import annotations

from typing import Any

from app.services.diet_v2.portion_fitter import fit_meal_portions


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
    fitted_solution = fit_meal_portions(
        blueprint=blueprint,
        meal=meal,
        meal_request=meal_request,
        selected_role_codes=instantiation["selected_role_codes"],
        support_food_specs=instantiation["support_food_specs"],
        role_candidate_pool=instantiation["role_candidate_pool"],
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        daily_food_usage=daily_food_usage,
        weekly_food_usage=weekly_food_usage,
    )
    if fitted_solution is not None:
        return fitted_solution

    for role in ("protein", "carb", "fat"):
        role_candidates = instantiation["role_candidate_pool"].get(role, [])
        for alternative_code in role_candidates[1:]:
            repaired_role_codes = dict(instantiation["selected_role_codes"])
            repaired_role_codes[role] = alternative_code
            fitted_solution = fit_meal_portions(
                blueprint=blueprint,
                meal=meal,
                meal_request=meal_request,
                selected_role_codes=repaired_role_codes,
                support_food_specs=instantiation["support_food_specs"],
                role_candidate_pool=instantiation["role_candidate_pool"],
                food_lookup=food_lookup,
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                weekly_food_usage=weekly_food_usage,
            )
            if fitted_solution is not None:
                return fitted_solution

    return None
