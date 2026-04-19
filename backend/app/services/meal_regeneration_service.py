"""Services to regenerate a single meal while preserving the rest of the diet."""
from __future__ import annotations

import random
from itertools import product
from typing import Any

from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietMeal, DietMutationResponse, DietMutationSummary
from app.schemas.user import UserPublic
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
from app.services.food_catalog_service import (
    build_catalog_food_from_diet_food,
    get_food_by_code,
    get_internal_food_lookup,
    resolve_foods_by_codes,
)
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import FoodPreferenceConflictError, build_user_food_preferences_profile
from app.services.meal_distribution_service import get_training_focus_indexes


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

def regenerate_meal(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
) -> DietMutationResponse:
    diet = get_user_diet_by_id(database, user.id, diet_id)
    meal_index = meal_number - 1
    if meal_index < 0 or meal_index >= len(diet.meals):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found in the selected diet",
        )

    meal = diet.meals[meal_index]
    preference_profile = build_user_food_preferences_profile(user)
    internal_food_lookup = get_internal_food_lookup()
    daily_food_usage = track_daily_food_usage_excluding_current_meal(
        diet,
        meal_index_to_exclude=meal_index,
        food_lookup=build_diet_context_food_lookup(database, diet),
    )
    current_food_codes = {
        str(food.food_code)
        for food in meal.foods
        if food.food_code
    }
    training_focus = get_training_focus_for_meal(diet, meal_index)

    # Semilla de variedad: garantiza que cada regeneración explore combinaciones distintas
    variety_seed = random.randint(0, 9999)

    try:
        regenerated_meal_plan = find_exact_solution_for_meal(
            meal=meal,
            meal_index=meal_index,
            meals_count=diet.meals_count,
            training_focus=training_focus,
            food_lookup=internal_food_lookup,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            excluded_food_codes=current_food_codes,
            variety_seed=variety_seed,
        )
    except (FoodPreferenceConflictError, HTTPException):
        regenerated_meal_plan = find_exact_solution_for_meal(
            meal=meal,
            meal_index=meal_index,
            meals_count=diet.meals_count,
            training_focus=training_focus,
            food_lookup=internal_food_lookup,
            preference_profile=preference_profile,
            daily_food_usage=daily_food_usage,
            variety_seed=variety_seed,
        )

    selected_food_codes = collect_selected_food_codes([regenerated_meal_plan])
    resolved_food_lookup, lookup_metadata = resolve_foods_by_codes(
        database,
        selected_food_codes,
    )
    generated_meal = generate_food_based_meal(
        meal=meal,
        meal_index=meal_index,
        meals_count=diet.meals_count,
        training_focus=training_focus,
        meal_plan=regenerated_meal_plan,
        food_lookup={
            **internal_food_lookup,
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
