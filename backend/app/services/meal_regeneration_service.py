"""Services to regenerate a single meal while preserving the rest of the diet."""
from __future__ import annotations

import logging
import time
from itertools import product
from typing import Any

from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietMeal, DietMutationResponse, DietMutationSummary
from app.schemas.user import UserPublic
from app.services.diet_runtime_audit import emit_runtime_audit
from app.services.diet_service import (
    build_exact_meal_solution,
    build_updated_diet_payload,
    collect_selected_food_codes,
    create_daily_food_usage_tracker,
    find_exact_solution_for_meal,
    generate_food_based_meal,
    get_role_candidate_codes,
    get_support_option_specs,
    get_user_diet_by_id,
    resolve_meal_context,
    save_diet,
    track_food_usage_across_day,
)
from app.services.diet.common import build_variety_seed
from app.services.food_catalog_service import (
    build_catalog_food_from_diet_food,
    get_food_by_code,
    get_internal_food_lookup,
    resolve_foods_by_codes,
)
from app.services.diet.candidates import build_weekly_food_usage
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import FoodPreferenceConflictError, build_user_food_preferences_profile
from app.services.diet_v2 import regenerate_meal_plan_v2
from app.services.diet_v2.portion_fitter import finalize_regeneration_candidate
from app.services.diet_v2.telemetry import get_last_regeneration_diagnostics, set_last_regeneration_diagnostics
from app.services.meal_coherence_service import (
    apply_generation_coherence,
    build_generation_food_lookup,
    build_regeneration_candidate_ranking,
    evaluate_regeneration_candidate,
)
from app.services.meal_distribution_service import get_training_focus_indexes

logger = logging.getLogger(__name__)


def get_training_focus_for_meal(diet: DailyDiet, meal_index: int) -> bool:
    if not diet.training_optimization_applied or not diet.training_time_of_day:
        return False

    primary_index, secondary_index = get_training_focus_indexes(
        diet.meals_count,
        diet.training_time_of_day,
    )
    return meal_index in {primary_index, secondary_index}


def build_diet_context_food_lookup(database, diet: DailyDiet) -> dict[str, dict[str, Any]]:
    food_lookup = get_internal_food_lookup()

    for meal in diet.meals:
        for food in meal.foods:
            food_code = str(food.food_code or "").strip()
            if not food_code or food_code in food_lookup:
                continue

            matched_food = get_food_by_code(database, food_code)
            food_lookup[food_code] = matched_food or build_catalog_food_from_diet_food(food.model_dump())

    return food_lookup


def _build_food_entry(food_lookup: dict[str, dict[str, Any]], food: Any) -> dict[str, Any]:
    food_code = str(food.food_code or "").strip()
    if food_code and food_code in food_lookup:
        return food_lookup[food_code]

    return build_catalog_food_from_diet_food(food.model_dump() if hasattr(food, "model_dump") else dict(food))


def _get_possible_roles(
    food_code: str,
    food_entry: dict[str, Any],
    candidate_role_codes: dict[str, list[str]],
) -> list[str]:
    exact_roles = [
        role
        for role, role_codes in candidate_role_codes.items()
        if food_code in role_codes
    ]
    if exact_roles:
        return exact_roles

    functional_group = derive_functional_group(food_entry)
    if functional_group in {"protein", "dairy"}:
        return ["protein"]
    if functional_group in {"carb", "fruit"}:
        return ["carb"]
    if functional_group == "fat":
        return ["fat"]

    return []


def _build_support_scenarios(
    meal: DietMeal,
    *,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    default_support_options = get_support_option_specs(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )
    meal_foods_by_code = {
        str(food.food_code): food
        for food in meal.foods
        if food.food_code
    }
    support_scenarios: list[list[dict[str, Any]]] = [[]]
    seen_keys: set[tuple[tuple[str, Any], ...]] = {tuple()}

    def add_support_scenario(role: str, food_code: str, quantity: float) -> None:
        scenario = [{
            "role": role,
            "food_code": food_code,
            "quantity": float(quantity),
        }]
        scenario_key = tuple(sorted((item["role"], item["food_code"], item["quantity"]) for item in scenario))
        if scenario_key in seen_keys:
            return

        support_scenarios.append(scenario)
        seen_keys.add(scenario_key)

    for support_option in default_support_options:
        if not support_option:
            continue

        support_food_code = support_option[0]["food_code"]
        if support_food_code not in meal_foods_by_code:
            continue

        add_support_scenario(
            support_option[0]["role"],
            support_food_code,
            float(meal_foods_by_code[support_food_code].quantity),
        )

    for food in meal.foods:
        food_code = str(food.food_code or "").strip()
        if not food_code:
            continue

        food_entry = _build_food_entry(food_lookup, food)
        functional_group = derive_functional_group(food_entry)
        if functional_group == "vegetable":
            add_support_scenario("vegetable", food_code, float(food.quantity))
        elif functional_group == "fruit":
            add_support_scenario("fruit", food_code, float(food.quantity))
        elif functional_group == "dairy":
            add_support_scenario("dairy", food_code, float(food.quantity))

    return support_scenarios


def _score_meal_similarity(candidate_solution: dict[str, Any], meal: DietMeal) -> float:
    current_foods = {
        str(food.food_code): food
        for food in meal.foods
        if food.food_code
    }
    candidate_foods = {
        str(food.get("food_code")): food
        for food in candidate_solution.get("foods", [])
        if food.get("food_code")
    }

    current_codes = set(current_foods)
    candidate_codes = set(candidate_foods)
    score = 0.0
    score += len(current_codes - candidate_codes) * 8.0
    score += len(candidate_codes - current_codes) * 6.0

    for food_code in current_codes & candidate_codes:
        current_quantity = float(current_foods[food_code].quantity)
        candidate_quantity = float(candidate_foods[food_code]["quantity"])
        score += abs(candidate_quantity - current_quantity) / max(current_quantity, 1.0)

    return score


def _build_heuristic_meal_plan(
    meal: DietMeal,
    *,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    meal_slot, _ = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    candidate_role_codes = get_role_candidate_codes(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    food_entries = [
        (str(food.food_code), _build_food_entry(food_lookup, food), food)
        for food in meal.foods
        if food.food_code
    ]
    if not food_entries:
        return find_exact_solution_for_meal(
            meal=meal,
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )

    chosen_codes: set[str] = set()
    selected_role_codes: dict[str, str] = {}
    for role, macro_key in (("protein", "protein_grams"), ("carb", "carb_grams"), ("fat", "fat_grams")):
        ranked_foods = sorted(
            (
                item
                for item in food_entries
                if item[0] not in chosen_codes and role in _get_possible_roles(item[0], item[1], candidate_role_codes)
            ),
            key=lambda item: float(item[1].get(macro_key) or 0.0),
            reverse=True,
        )
        if ranked_foods:
            selected_role_codes[role] = ranked_foods[0][0]
            chosen_codes.add(ranked_foods[0][0])
            continue

        fallback_code = next(
            (
                code
                for code in candidate_role_codes[role]
                if code not in chosen_codes and code in food_lookup
            ),
            None,
        )
        if fallback_code:
            selected_role_codes[role] = fallback_code
            chosen_codes.add(fallback_code)

    if len(selected_role_codes) != 3:
        return find_exact_solution_for_meal(
            meal=meal,
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
            food_lookup=food_lookup,
        )

    support_food_specs: list[dict[str, Any]] = []
    remaining_support = next(
        (
            item
            for item in food_entries
            if item[0] not in chosen_codes and derive_functional_group(item[1]) in {"fruit", "vegetable", "dairy"}
        ),
        None,
    )
    if remaining_support:
        support_food_specs = [{
            "role": derive_functional_group(remaining_support[1]),
            "food_code": remaining_support[0],
            "quantity": float(remaining_support[2].quantity),
        }]

    meal_solution = build_exact_meal_solution(
        meal=meal,
        role_foods={
            role: food_lookup[food_code]
            for role, food_code in selected_role_codes.items()
        },
        support_food_specs=support_food_specs,
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=food_lookup,
        training_focus=training_focus,
        meal_slot=meal_slot,
    )
    if meal_solution:
        return meal_solution

    return find_exact_solution_for_meal(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )


def infer_existing_meal_plan(
    meal: DietMeal,
    *,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    meal_slot, _ = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    candidate_role_codes = get_role_candidate_codes(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    support_scenarios = _build_support_scenarios(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )
    meal_food_codes = [
        str(food.food_code)
        for food in meal.foods
        if food.food_code
    ]
    best_solution: dict[str, Any] | None = None
    best_score: float | None = None

    for support_scenario in support_scenarios:
        support_codes = {support_food["food_code"] for support_food in support_scenario}
        remaining_codes = [
            food_code
            for food_code in meal_food_codes
            if food_code not in support_codes
        ]
        role_choice_pools = {
            role: [
                code
                for code in remaining_codes
                if role in _get_possible_roles(code, food_lookup[code], candidate_role_codes)
            ]
            for role in ("protein", "carb", "fat")
        }

        for role in role_choice_pools:
            fallback_codes = [
                code
                for code in candidate_role_codes[role]
                if code in food_lookup and code not in role_choice_pools[role]
            ]
            role_choice_pools[role].extend(fallback_codes)

        if any(not role_choice_pools[role] for role in role_choice_pools):
            continue

        for protein_code, carb_code, fat_code in product(
            role_choice_pools["protein"],
            role_choice_pools["carb"],
            role_choice_pools["fat"],
        ):
            if len({protein_code, carb_code, fat_code}) != 3:
                continue

            if support_codes & {protein_code, carb_code, fat_code}:
                continue

            candidate_solution = build_exact_meal_solution(
                meal=meal,
                role_foods={
                    "protein": food_lookup[protein_code],
                    "carb": food_lookup[carb_code],
                    "fat": food_lookup[fat_code],
                },
                support_food_specs=support_scenario,
                candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
                food_lookup=food_lookup,
                training_focus=training_focus,
                meal_slot=meal_slot,
            )
            if not candidate_solution:
                continue

            candidate_score = _score_meal_similarity(candidate_solution, meal)
            if best_solution is None or best_score is None or candidate_score < best_score:
                best_solution = candidate_solution
                best_score = candidate_score

    if best_solution is not None:
        return best_solution

    return _build_heuristic_meal_plan(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )


def track_daily_food_usage_excluding_current_meal(
    diet: DailyDiet,
    *,
    meal_index_to_exclude: int,
    food_lookup: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    daily_food_usage = create_daily_food_usage_tracker()

    for meal_index, meal in enumerate(diet.meals):
        if meal_index == meal_index_to_exclude:
            continue

        try:
            inferred_meal_plan = infer_existing_meal_plan(
                meal,
                meal_index=meal_index,
                meals_count=diet.meals_count,
                training_focus=get_training_focus_for_meal(diet, meal_index),
                food_lookup=food_lookup,
            )
            track_food_usage_across_day(daily_food_usage, inferred_meal_plan)
        except Exception:
            for food in meal.foods:
                food_code = str(food.food_code or "").strip()
                if not food_code:
                    continue

                daily_food_usage["food_counts"][food_code] = daily_food_usage["food_counts"].get(food_code, 0) + 1

    return daily_food_usage


def persist_updated_meal_in_diet(
    database,
    *,
    user: UserPublic,
    diet: DailyDiet,
    diet_id: str,
    meal_index: int,
    updated_meal: dict[str, Any],
    preference_profile: dict[str, Any] | None,
    metadata_overrides: dict[str, Any] | None = None,
) -> DailyDiet:
    # Guardamos una nueva versión activa para conservar el histórico del plan anterior.
    updated_meals = []
    for index, current_meal in enumerate(diet.meals):
        if index == meal_index:
            updated_meals.append(updated_meal)
        else:
            # Forzamos la conversión a dict para evitar conflictos de tipos.
            updated_meals.append(current_meal.model_dump())

    updated_diet_payload = build_updated_diet_payload(
        existing_diet=diet,
        meals=updated_meals,
        preference_profile=preference_profile,
        metadata_overrides=metadata_overrides,
    )
    return save_diet(
        database,
        user.id,
        updated_diet_payload,
        adjusted_from_diet_id=diet_id,
    )


def _rank_food_codes_for_partial_regeneration(
    current_food_codes: set[str],
    *,
    current_meal_plan: dict[str, Any] | None,
    food_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    ranked_codes: list[str] = []
    seen_codes: set[str] = set()

    def add_code(food_code: str) -> None:
        normalized_code = str(food_code or "").strip()
        if not normalized_code or normalized_code not in current_food_codes or normalized_code in seen_codes:
            return
        seen_codes.add(normalized_code)
        ranked_codes.append(normalized_code)

    if current_meal_plan:
        for support_food in current_meal_plan.get("support_food_specs", []):
            add_code(str(support_food.get("food_code") or ""))

        selected_role_codes = current_meal_plan.get("selected_role_codes", {})
        for role in ("fat", "carb", "protein"):
            add_code(str(selected_role_codes.get(role) or ""))

    group_priority = {
        "vegetable": 0,
        "fruit": 1,
        "dairy": 2,
        "fat": 3,
        "carb": 4,
        "protein": 5,
    }
    for food_code in sorted(
        current_food_codes - seen_codes,
        key=lambda code: (
            group_priority.get(derive_functional_group(food_lookup.get(code, {})), 99),
            code,
        ),
    ):
        add_code(food_code)

    return ranked_codes


def _build_partial_regeneration_exclusion_sets(
    current_food_codes: set[str],
    *,
    current_meal_plan: dict[str, Any] | None,
    food_lookup: dict[str, dict[str, Any]],
) -> list[set[str]]:
    if len(current_food_codes) <= 1:
        return []

    partial_exclusion_sets: list[set[str]] = []
    seen_keys: set[frozenset[str]] = set()

    def add_exclusion_set(excluded_codes: set[str]) -> None:
        normalized_codes = {
            str(code).strip()
            for code in excluded_codes
            if str(code).strip()
        }
        if not normalized_codes or normalized_codes == current_food_codes:
            return
        frozen_codes = frozenset(normalized_codes)
        if frozen_codes in seen_keys:
            return
        seen_keys.add(frozen_codes)
        partial_exclusion_sets.append(normalized_codes)

    if current_meal_plan:
        core_codes = {
            str(food_code).strip()
            for food_code in current_meal_plan.get("selected_role_codes", {}).values()
            if str(food_code).strip() in current_food_codes
        }
        add_exclusion_set(core_codes)

    for preserved_code in _rank_food_codes_for_partial_regeneration(
        current_food_codes,
        current_meal_plan=current_meal_plan,
        food_lookup=food_lookup,
    ):
        add_exclusion_set(current_food_codes - {preserved_code})

    return partial_exclusion_sets


def _build_regeneration_context(
    *,
    current_food_codes: set[str],
    current_meal_plan: dict[str, Any] | None,
    strict_exclusions: bool,
    expand_candidate_pool: bool,
) -> dict[str, Any]:
    return {
        "original_food_codes": set(current_food_codes),
        "original_selected_role_codes": dict((current_meal_plan or {}).get("selected_role_codes", {})),
        "original_support_food_specs": list((current_meal_plan or {}).get("support_food_specs", [])),
        "strict_exclusions": strict_exclusions,
        "prefer_visible_difference": True,
        "min_visual_difference": 2,
        "avoid_same_template": True,
        "expand_candidate_pool": expand_candidate_pool,
        "min_distinct_calorie_ratio": 0.45,
    }


def _solve_regenerated_meal_plan(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    full_food_lookup: dict[str, dict[str, Any]],
    current_meal_food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any] | None,
    daily_food_usage: dict[str, dict[str, Any]] | None,
    current_food_codes: set[str],
    variety_seed: int,
) -> dict[str, Any]:
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    current_meal_plan: dict[str, Any] | None = None
    if current_food_codes:
        try:
            inferred_current_plan = infer_existing_meal_plan(
                meal,
                meal_index=meal_index,
                meals_count=meals_count,
                training_focus=training_focus,
                food_lookup=current_meal_food_lookup,
            )
            current_meal_plan = {
                "selected_role_codes": {
                    role: food_code
                    for role, food_code in inferred_current_plan.get("selected_role_codes", {}).items()
                    if str(food_code).strip() in current_food_codes
                },
                "support_food_specs": [
                    support_food
                    for support_food in inferred_current_plan.get("support_food_specs", [])
                    if str(support_food.get("food_code") or "").strip() in current_food_codes
                ],
            }
        except Exception:
            current_meal_plan = None

    def attempt_regeneration(
        *,
        excluded_food_codes: set[str] | None,
        strict_exclusions: bool,
        expand_candidate_pool: bool,
        seed_offset: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        regeneration_context = _build_regeneration_context(
            current_food_codes=current_food_codes,
            current_meal_plan=current_meal_plan,
            strict_exclusions=strict_exclusions,
            expand_candidate_pool=expand_candidate_pool,
        )
        meal_plan = find_exact_solution_for_meal(
            meal=meal,
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
            food_lookup=full_food_lookup,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            excluded_food_codes=excluded_food_codes,
            variety_seed=variety_seed + seed_offset,
            expand_candidate_pool=expand_candidate_pool,
            regeneration_context=regeneration_context,
        )
        coherent_plan = apply_generation_coherence(
            meal=meal,
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus,
            meal_plan=meal_plan,
            food_lookup=full_food_lookup,
            preference_profile=preference_profile,
            daily_diversity_context=daily_food_usage,
            excluded_food_codes=excluded_food_codes,
            strict_exclusions=strict_exclusions,
            regeneration_context=regeneration_context,
            variety_seed=variety_seed + seed_offset,
        )
        return coherent_plan, regeneration_context

    def register_candidate(
        candidate_plan: dict[str, Any],
        *,
        regeneration_context: dict[str, Any],
        best_candidate: dict[str, Any] | None,
        best_candidate_ranking: tuple[Any, ...] | None,
    ) -> tuple[dict[str, Any] | None, tuple[Any, ...] | None, dict[str, Any], dict[str, Any] | None]:
        finalized_candidate = finalize_regeneration_candidate(
            meal=meal,
            meal_plan=candidate_plan,
            meal_slot=meal_slot,
            meal_role=meal_role,
            food_lookup=full_food_lookup,
        )
        nutrition_validation = dict(finalized_candidate.get("nutrition_validation") or {})
        candidate_ranking = build_regeneration_candidate_ranking(
            meal=meal,
            meal_plan=finalized_candidate,
            food_lookup=full_food_lookup,
            regeneration_context=regeneration_context,
        )
        difference_summary = evaluate_regeneration_candidate(
            meal=meal,
            meal_plan=finalized_candidate,
            food_lookup=full_food_lookup,
            regeneration_context=regeneration_context,
        )
        if not nutrition_validation.get("within_tolerance"):
            return best_candidate, best_candidate_ranking, difference_summary, None
        if best_candidate is None or best_candidate_ranking is None or candidate_ranking < best_candidate_ranking:
            return finalized_candidate, candidate_ranking, difference_summary, finalized_candidate
        return best_candidate, best_candidate_ranking, difference_summary, finalized_candidate

    best_candidate: dict[str, Any] | None = None
    best_candidate_ranking: tuple[Any, ...] | None = None
    last_error: Exception | None = None

    if current_food_codes:
        for attempt_index, expand_candidate_pool in enumerate((False, True)):
            try:
                candidate_plan, regeneration_context = attempt_regeneration(
                    excluded_food_codes=current_food_codes,
                    strict_exclusions=True,
                    expand_candidate_pool=expand_candidate_pool,
                    seed_offset=attempt_index,
                )
            except (FoodPreferenceConflictError, HTTPException) as exc:
                last_error = exc
                continue

            best_candidate, best_candidate_ranking, difference_summary, accepted_candidate = register_candidate(
                candidate_plan,
                regeneration_context=regeneration_context,
                best_candidate=best_candidate,
                best_candidate_ranking=best_candidate_ranking,
            )
            if (
                accepted_candidate is not None
                and difference_summary["passes_threshold"]
                and not difference_summary["same_visible_structure"]
            ):
                return accepted_candidate

        partial_exclusion_sets = _build_partial_regeneration_exclusion_sets(
            current_food_codes,
            current_meal_plan=current_meal_plan,
            food_lookup=current_meal_food_lookup,
        )
        for attempt_index, excluded_codes in enumerate(partial_exclusion_sets, start=10):
            try:
                candidate_plan, regeneration_context = attempt_regeneration(
                    excluded_food_codes=excluded_codes,
                    strict_exclusions=True,
                    expand_candidate_pool=True,
                    seed_offset=attempt_index,
                )
            except (FoodPreferenceConflictError, HTTPException) as exc:
                last_error = exc
                continue

            best_candidate, best_candidate_ranking, difference_summary, accepted_candidate = register_candidate(
                candidate_plan,
                regeneration_context=regeneration_context,
                best_candidate=best_candidate,
                best_candidate_ranking=best_candidate_ranking,
            )
            if (
                accepted_candidate is not None
                and difference_summary["passes_threshold"]
                and not difference_summary["same_visible_structure"]
            ):
                return accepted_candidate

    try:
        candidate_plan, regeneration_context = attempt_regeneration(
            excluded_food_codes=None,
            strict_exclusions=False,
            expand_candidate_pool=True,
            seed_offset=100,
        )
    except (FoodPreferenceConflictError, HTTPException) as exc:
        last_error = exc
    else:
        best_candidate, best_candidate_ranking, _difference_summary, accepted_candidate = register_candidate(
            candidate_plan,
            regeneration_context=regeneration_context,
            best_candidate=best_candidate,
            best_candidate_ranking=best_candidate_ranking,
        )
        if accepted_candidate is not None:
            return accepted_candidate if best_candidate is accepted_candidate else best_candidate

    if best_candidate is not None:
        return best_candidate
    if last_error is not None:
        raise last_error
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to regenerate meal with current food catalog",
    )


def regenerate_meal(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
) -> DietMutationResponse:
    regeneration_started_at = time.perf_counter()
    diet = get_user_diet_by_id(database, user.id, diet_id)
    meal_index = meal_number - 1
    if meal_index < 0 or meal_index >= len(diet.meals):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found in the selected diet",
        )

    meal = diet.meals[meal_index]
    emit_runtime_audit(
        "meal_regeneration_service_started",
        {
            "diet_id": diet_id,
            "meal_number": meal_number,
            "original_meal": meal.model_dump(mode="json"),
            "active_diet_id_before_regeneration": diet.id,
        },
    )
    preference_profile = build_user_food_preferences_profile(user)
    internal_food_lookup = get_internal_food_lookup()
    full_food_lookup = build_generation_food_lookup(
        database,
        internal_food_lookup=internal_food_lookup,
    )
    current_meal_food_lookup = build_diet_context_food_lookup(database, diet)
    daily_food_usage = track_daily_food_usage_excluding_current_meal(
        diet,
        meal_index_to_exclude=meal_index,
        food_lookup=current_meal_food_lookup,
    )
    current_food_codes = {
        str(food.food_code)
        for food in meal.foods
        if food.food_code
    }
    training_focus = get_training_focus_for_meal(diet, meal_index)
    weekly_food_usage = build_weekly_food_usage(database, user.id)

    variety_seed = build_variety_seed(
        user.id,
        diet_id,
        meal_number,
        meal.meal_slot,
        meal.meal_role,
        sorted(current_food_codes),
    )
    current_meal_plan: dict[str, Any] | None = None
    if current_food_codes:
        try:
            current_meal_plan = infer_existing_meal_plan(
                meal,
                meal_index=meal_index,
                meals_count=diet.meals_count,
                training_focus=training_focus,
                food_lookup=current_meal_food_lookup,
            )
        except Exception:
            current_meal_plan = None

    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=diet.meals_count,
        training_focus=training_focus,
    )
    regeneration_engine = "v2"
    try:
        regenerated_meal_plan = regenerate_meal_plan_v2(
            meal=meal,
            meal_index=meal_index,
            meals_count=diet.meals_count,
            training_focus=training_focus,
            meal_slot=meal_slot,
            meal_role=meal_role,
            food_lookup=full_food_lookup,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            weekly_food_usage=weekly_food_usage,
            current_food_codes=current_food_codes,
            current_meal_plan=current_meal_plan,
            variety_seed=variety_seed,
        )
        if regenerated_meal_plan is None:
            raise RuntimeError("diet_v2 regenerator returned no candidate")
    except Exception as exc:
        regeneration_engine = "legacy_fallback"
        regeneration_diagnostics = get_last_regeneration_diagnostics() or {}
        logger.warning(
            "Meal regeneration v2 failed for user=%s diet=%s meal=%s, falling back to legacy solver: %s diagnostics=%s",
            user.id,
            diet_id,
            meal_number,
            exc,
            regeneration_diagnostics,
        )
        emit_runtime_audit(
            "meal_regeneration_v2_failed",
            {
                "diet_id": diet_id,
                "meal_number": meal_number,
                "error_type": type(exc).__name__,
                "error_detail": str(exc),
                "regeneration_diagnostics": regeneration_diagnostics,
            },
        )
        regenerated_meal_plan = _solve_regenerated_meal_plan(
            meal=meal,
            meal_index=meal_index,
            meals_count=diet.meals_count,
            training_focus=training_focus,
            full_food_lookup=full_food_lookup,
            current_meal_food_lookup=current_meal_food_lookup,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            current_food_codes=current_food_codes,
            variety_seed=variety_seed,
        )

    regenerated_meal_plan = finalize_regeneration_candidate(
        meal=meal,
        meal_plan=regenerated_meal_plan,
        meal_slot=meal_slot,
        meal_role=meal_role,
        food_lookup=full_food_lookup,
    )
    regeneration_diagnostics = get_last_regeneration_diagnostics() or {}
    regeneration_diagnostics["regeneration_micro_adjustment"] = dict(
        regenerated_meal_plan.get("regeneration_micro_adjustment") or {},
    )
    regeneration_diagnostics["nutrition_validation"] = dict(
        regenerated_meal_plan.get("nutrition_validation") or {},
    )
    if regeneration_diagnostics["nutrition_validation"].get("accepted_with_residual_error"):
        regeneration_diagnostics["residual_reason"] = dict(
            regeneration_diagnostics["nutrition_validation"].get("residual_reason") or {},
        )
    set_last_regeneration_diagnostics(regeneration_diagnostics)

    selected_food_codes = collect_selected_food_codes([regenerated_meal_plan])
    internal_codes_to_resolve = [code for code in selected_food_codes if code in internal_food_lookup]
    if internal_codes_to_resolve:
        resolved_food_lookup, lookup_metadata = resolve_foods_by_codes(
            database,
            internal_codes_to_resolve,
            allow_external_enrichment=False,
        )
    else:
        resolved_food_lookup = {}
        lookup_metadata = {
            "food_catalog_version": diet.food_catalog_version,
            "catalog_source_strategy": diet.catalog_source_strategy,
            "spoonacular_attempted": False,
            "spoonacular_attempts": 0,
            "resolved_foods_count": len(selected_food_codes),
        }
    generated_meal = generate_food_based_meal(
        meal=meal,
        meal_index=meal_index,
        meals_count=diet.meals_count,
        training_focus=training_focus,
        meal_plan=regenerated_meal_plan,
        food_lookup={
            **full_food_lookup,
            **resolved_food_lookup,
        },
    )
    updated_diet = persist_updated_meal_in_diet(
        database,
        user=user,
        diet=diet,
        diet_id=diet_id,
        meal_index=meal_index,
        updated_meal=generated_meal,
        preference_profile=preference_profile,
        metadata_overrides={
            "food_catalog_version": lookup_metadata.get("food_catalog_version", diet.food_catalog_version),
            "catalog_source_strategy": lookup_metadata.get("catalog_source_strategy", diet.catalog_source_strategy),
            "spoonacular_attempted": diet.spoonacular_attempted or lookup_metadata.get("spoonacular_attempted", False),
            "spoonacular_attempts": diet.spoonacular_attempts + lookup_metadata.get("spoonacular_attempts", 0),
        },
    )

    changed_food_names = [food["name"] for food in generated_meal.get("foods", [])]
    strategy_notes = [
        "Se mantuvieron intactas las demas comidas del dia.",
        "Se priorizo una comida distinta evitando repetir innecesariamente alimentos ya usados ese dia.",
    ]
    if not current_food_codes.isdisjoint({food.get("food_code") for food in generated_meal.get("foods", [])}):
        strategy_notes[1] = "Se mantuvo la coherencia diaria usando variedad razonable dentro de las restricciones disponibles."

    logger.info(
        "Meal regeneration timings user=%s diet=%s meal=%s total=%.4fs selected_foods=%s",
        user.id,
        diet_id,
        meal_number,
        time.perf_counter() - regeneration_started_at,
        len(selected_food_codes),
    )
    logger.info(
        "Meal regeneration engine user=%s diet=%s meal=%s engine=%s",
        user.id,
        diet_id,
        meal_number,
        regeneration_engine,
    )
    regeneration_diagnostics = get_last_regeneration_diagnostics() or {}
    regeneration_diagnostics.update({
        "service_engine": regeneration_engine,
        "service_elapsed_seconds": time.perf_counter() - regeneration_started_at,
        "meal_number": meal_number,
        "diet_id": diet_id,
    })
    set_last_regeneration_diagnostics(regeneration_diagnostics)
    emit_runtime_audit(
        "meal_regeneration_service_completed",
        {
            "diet_id": diet_id,
            "meal_number": meal_number,
            "service_engine": regeneration_engine,
            "regeneration_diagnostics": regeneration_diagnostics,
            "regenerated_meal_plan": regenerated_meal_plan,
            "generated_meal": generated_meal,
            "persisted_diet_payload": updated_diet.model_dump(mode="json"),
            "summary": {
                "action": "meal_regenerated",
                "meal_number": meal_number,
                "changed_food_names": changed_food_names,
                "strategy_notes": strategy_notes,
            },
        },
    )

    return DietMutationResponse(
        diet=updated_diet,
        summary=DietMutationSummary(
            action="meal_regenerated",
            meal_number=meal_number,
            message=f"Se regenero la comida {meal_number} manteniendo el resto del dia sin cambios.",
            preserved_meal_numbers=[
                current_meal.meal_number
                for index, current_meal in enumerate(diet.meals)
                if index != meal_index
            ],
            changed_food_names=changed_food_names,
            strategy_notes=strategy_notes,
        ),
    )
