"""Services to replace a single food inside an existing meal."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.schemas.diet import (
    DietMutationResponse,
    DietMutationSummary,
    FoodReplacementOption,
    FoodReplacementOptionsResponse,
    ReplaceFoodRequest,
)
from app.schemas.user import UserPublic
from app.services.diet_service import (
    build_exact_meal_solution,
    find_exact_solution_for_meal,
    get_meal_slot,
    get_user_diet_by_id,
)
from app.services.food_catalog_service import (
    build_catalog_food_from_diet_food,
    find_food_by_code_or_name,
    get_internal_food_lookup,
)
from app.services.food_preferences_service import (
    FoodPreferenceConflictError,
    build_user_food_preferences_profile,
    count_food_preference_matches,
    is_food_allowed_for_user,
)
from app.services.food_group_service import derive_functional_group
from app.services.meal_regeneration_service import (
    build_diet_context_food_lookup,
    get_training_focus_for_meal,
    infer_existing_meal_plan,
    persist_updated_meal_in_diet,
    track_daily_food_usage_excluding_current_meal,
)
from app.utils.normalization import normalize_food_name

COMPATIBLE_GROUPS_BY_SLOT = {
    ("role", "protein"): {"protein", "dairy"},
    ("role", "carb"): {"carb", "fruit"},
    ("role", "fat"): {"fat"},
    ("support", "dairy"): {"dairy", "protein"},
    ("support", "fruit"): {"fruit", "carb"},
    ("support", "vegetable"): {"vegetable"},
}


def _find_current_food_in_meal(meal, *, current_food_name: str, current_food_code: str | None = None):
    normalized_target_name = normalize_food_name(current_food_name)

    for food in meal.foods:
        if current_food_code and food.food_code == current_food_code:
            return food

        if normalize_food_name(food.name) == normalized_target_name:
            return food

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No se encontro el alimento '{current_food_name}' en la comida seleccionada.",
    )


def _build_current_meal_food_lookup(base_lookup: dict[str, dict[str, Any]], meal) -> dict[str, dict[str, Any]]:
    meal_lookup = dict(base_lookup)
    for food in meal.foods:
        food_code = str(food.food_code or "").strip()
        if not food_code:
            continue

        meal_lookup[food_code] = build_catalog_food_from_diet_food(food.model_dump())

    return meal_lookup


def _build_food_replacement_context(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
    current_food_name: str,
    current_food_code: str | None = None,
) -> dict[str, Any]:
    diet = get_user_diet_by_id(database, user.id, diet_id)
    meal_index = meal_number - 1
    if meal_index < 0 or meal_index >= len(diet.meals):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found in the selected diet",
        )

    meal = diet.meals[meal_index]
    current_food = _find_current_food_in_meal(
        meal,
        current_food_name=current_food_name,
        current_food_code=current_food_code,
    )
    context_food_lookup = build_diet_context_food_lookup(database, diet)
    meal_food_lookup = _build_current_meal_food_lookup(context_food_lookup, meal)
    current_food_entry = meal_food_lookup.get(str(current_food.food_code or "")) or build_catalog_food_from_diet_food(
        current_food.model_dump()
    )
    preference_profile = build_user_food_preferences_profile(user)
    training_focus = get_training_focus_for_meal(diet, meal_index)
    inferred_plan = infer_existing_meal_plan(
        meal,
        meal_index=meal_index,
        meals_count=diet.meals_count,
        training_focus=training_focus,
        food_lookup=meal_food_lookup,
    )
    slot = _derive_replacement_slot(str(current_food.food_code or ""), inferred_plan, current_food_entry)
    daily_food_usage = track_daily_food_usage_excluding_current_meal(
        diet,
        meal_index_to_exclude=meal_index,
        food_lookup=context_food_lookup,
    )

    return {
        "diet": diet,
        "meal": meal,
        "meal_index": meal_index,
        "current_food": current_food,
        "current_food_entry": current_food_entry,
        "context_food_lookup": context_food_lookup,
        "meal_food_lookup": meal_food_lookup,
        "preference_profile": preference_profile,
        "training_focus": training_focus,
        "inferred_plan": inferred_plan,
        "slot": slot,
        "daily_food_usage": daily_food_usage,
    }


def _derive_replacement_slot(current_food_code: str, inferred_plan: dict[str, Any], current_food_entry: dict[str, Any]) -> dict[str, str]:
    for role, food_code in inferred_plan.get("selected_role_codes", {}).items():
        if food_code == current_food_code:
            return {"kind": "role", "role": role}

    for support_food in inferred_plan.get("support_food_specs", []):
        if support_food["food_code"] == current_food_code:
            return {"kind": "support", "role": support_food["role"]}

    functional_group = derive_functional_group(current_food_entry)
    if functional_group == "vegetable":
        return {"kind": "support", "role": "vegetable"}
    if functional_group == "fruit":
        return {"kind": "support", "role": "fruit"}
    if functional_group == "dairy":
        return {"kind": "support", "role": "dairy"}
    if functional_group in {"protein", "dairy"}:
        return {"kind": "role", "role": "protein"}
    if functional_group in {"carb", "fruit"}:
        return {"kind": "role", "role": "carb"}

    return {"kind": "role", "role": "fat"}


def _is_candidate_compatible(candidate_food: dict[str, Any], slot: dict[str, str]) -> bool:
    compatible_groups = COMPATIBLE_GROUPS_BY_SLOT.get((slot["kind"], slot["role"]), set())
    return derive_functional_group(candidate_food) in compatible_groups


def _validate_candidate_for_user(candidate_food: dict[str, Any], preference_profile: dict[str, Any]) -> None:
    is_allowed, reasons = is_food_allowed_for_user(candidate_food, preference_profile)
    if is_allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            f"El alimento '{candidate_food['name']}' no es compatible con las preferencias o restricciones del usuario: "
            + ", ".join(reasons)
            + "."
        ),
    )


def _get_macro_density(food: dict[str, Any]) -> dict[str, float]:
    reference_amount = max(float(food.get("reference_amount") or 0.0), 1e-6)
    return {
        "protein_grams": float(food.get("protein_grams") or 0.0) / reference_amount,
        "fat_grams": float(food.get("fat_grams") or 0.0) / reference_amount,
        "carb_grams": float(food.get("carb_grams") or 0.0) / reference_amount,
        "calories": float(food.get("calories") or 0.0) / reference_amount,
    }


def _score_candidate_similarity(
    candidate_food: dict[str, Any],
    current_food_entry: dict[str, Any],
    *,
    daily_food_usage: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any],
    slot: dict[str, str],
) -> float:
    candidate_density = _get_macro_density(candidate_food)
    current_density = _get_macro_density(current_food_entry)
    macro_distance = (
        abs(candidate_density["protein_grams"] - current_density["protein_grams"]) * 4.0
        + abs(candidate_density["fat_grams"] - current_density["fat_grams"]) * 3.0
        + abs(candidate_density["carb_grams"] - current_density["carb_grams"]) * 3.0
        + abs(candidate_density["calories"] - current_density["calories"])
    )
    usage_penalty = float(daily_food_usage.get("food_counts", {}).get(candidate_food["code"], 0)) * 2.5
    preference_bonus = float(count_food_preference_matches(candidate_food, preference_profile)) * 0.6
    slot_bonus = 0.0 if derive_functional_group(candidate_food) == derive_functional_group(current_food_entry) else 0.4

    if slot["kind"] == "support":
        macro_distance *= 0.8

    return macro_distance + usage_penalty + slot_bonus - preference_bonus


def find_equivalent_food_candidates(
    *,
    current_food_entry: dict[str, Any],
    slot: dict[str, str],
    preference_profile: dict[str, Any],
    daily_food_usage: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    current_food_code = str(current_food_entry["code"])
    internal_food_lookup = get_internal_food_lookup()
    compatible_candidates: list[dict[str, Any]] = []

    for candidate_food in internal_food_lookup.values():
        if candidate_food["code"] == current_food_code:
            continue
        if not _is_candidate_compatible(candidate_food, slot):
            continue

        is_allowed, _ = is_food_allowed_for_user(candidate_food, preference_profile)
        if not is_allowed:
            continue

        compatible_candidates.append(candidate_food)

    return sorted(
        compatible_candidates,
        key=lambda candidate_food: _score_candidate_similarity(
            candidate_food,
            current_food_entry,
            daily_food_usage=daily_food_usage,
            preference_profile=preference_profile,
            slot=slot,
        ),
    )


def _resolve_requested_replacement_food(
    database,
    *,
    payload: ReplaceFoodRequest,
    slot: dict[str, str],
    preference_profile: dict[str, Any],
) -> dict[str, Any]:
    replacement_food = find_food_by_code_or_name(
        database,
        food_code=payload.replacement_food_code,
        food_name=payload.replacement_food_name,
        include_external=True,
    )
    if not replacement_food:
        requested_name = payload.replacement_food_name or payload.replacement_food_code or "el alimento propuesto"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se pudo localizar '{requested_name}' como alimento de sustitucion.",
        )

    _validate_candidate_for_user(replacement_food, preference_profile)
    if not _is_candidate_compatible(replacement_food, slot):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El alimento '{replacement_food['name']}' no encaja como sustituto funcional para esta comida. "
                "Prueba con un alimento de categoria o funcion nutricional similar."
            ),
        )

    return replacement_food


def _iter_quantity_candidates(food: dict[str, Any], estimated_quantity: float) -> list[float]:
    min_quantity = float(food.get("min_quantity") or food.get("reference_amount") or 1.0)
    max_quantity = float(food.get("max_quantity") or max(min_quantity + 1.0, estimated_quantity * 2.0))
    step = float(food.get("step") or 1.0)
    if step <= 0:
        step = 1.0

    quantities: list[float] = []
    current_quantity = min_quantity
    while current_quantity <= max_quantity + 1e-6:
        quantities.append(round(current_quantity, 2))
        current_quantity += step

    if not quantities:
        quantities = [round(max(min_quantity, estimated_quantity), 2)]

    quantities.sort(key=lambda quantity: abs(quantity - estimated_quantity))
    return quantities[:40]


def _estimate_support_quantity(current_food, replacement_food: dict[str, Any]) -> float:
    replacement_calories = float(replacement_food.get("calories") or 0.0)
    replacement_reference = max(float(replacement_food.get("reference_amount") or 0.0), 1e-6)
    if replacement_calories <= 0:
        return float(replacement_food.get("default_quantity") or replacement_reference)

    return replacement_reference * (float(current_food.calories) / replacement_calories)


def _score_support_solution(
    solution: dict[str, Any],
    *,
    current_food,
    replacement_food_code: str,
) -> float:
    replacement_portion = next(
        (
            food
            for food in solution.get("foods", [])
            if food.get("food_code") == replacement_food_code
        ),
        None,
    )
    if not replacement_portion:
        return float("inf")

    return (
        abs(float(replacement_portion["calories"]) - float(current_food.calories))
        + abs(float(replacement_portion["protein_grams"]) - float(current_food.protein_grams)) * 4.0
        + abs(float(replacement_portion["fat_grams"]) - float(current_food.fat_grams)) * 3.0
        + abs(float(replacement_portion["carb_grams"]) - float(current_food.carb_grams)) * 3.0
    )


def rebuild_meal_after_food_replacement(
    *,
    meal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    current_food,
    replacement_food: dict[str, Any],
    slot: dict[str, str],
    inferred_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any],
    daily_food_usage: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    meal_slot = get_meal_slot(meal_index, meals_count)
    current_food_code = str(current_food.food_code or "")
    candidate_food_lookup = {
        **food_lookup,
        replacement_food["code"]: replacement_food,
    }
    base_role_foods = {
        role: candidate_food_lookup[food_code]
        for role, food_code in inferred_plan.get("selected_role_codes", {}).items()
    }
    base_support_foods = [
        {
            "role": support_food["role"],
            "food_code": support_food["food_code"],
            "quantity": float(support_food["quantity"]),
        }
        for support_food in inferred_plan.get("support_food_specs", [])
    ]

    if slot["kind"] == "role":
        if len(base_role_foods) == 3:
            strict_role_foods = dict(base_role_foods)
            strict_role_foods[slot["role"]] = replacement_food
            strict_solution = build_exact_meal_solution(
                meal=meal,
                role_foods=strict_role_foods,
                support_food_specs=base_support_foods,
                candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
                food_lookup=candidate_food_lookup,
                training_focus=training_focus,
                meal_slot=meal_slot,
            )
            if strict_solution:
                return strict_solution, "strict"

        try:
            relaxed_solution = find_exact_solution_for_meal(
                meal=meal,
                meal_index=meal_index,
                meals_count=meals_count,
                training_focus=training_focus,
                food_lookup={
                    **get_internal_food_lookup(),
                    **candidate_food_lookup,
                },
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                forced_role_codes={slot["role"]: replacement_food["code"]},
                forced_support_foods=base_support_foods,
                excluded_food_codes={current_food_code},
            )
            return relaxed_solution, "relaxed"
        except (FoodPreferenceConflictError, HTTPException):
            relaxed_solution = find_exact_solution_for_meal(
                meal=meal,
                meal_index=meal_index,
                meals_count=meals_count,
                training_focus=training_focus,
                food_lookup={
                    **get_internal_food_lookup(),
                    **candidate_food_lookup,
                },
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                forced_role_codes={slot["role"]: replacement_food["code"]},
                excluded_food_codes={current_food_code},
            )
            return relaxed_solution, "relaxed"

    existing_support_foods = [
        support_food
        for support_food in base_support_foods
        if support_food["food_code"] != current_food_code
    ]
    if not base_support_foods:
        existing_support_foods = []

    estimated_quantity = _estimate_support_quantity(current_food, replacement_food)
    best_solution: dict[str, Any] | None = None
    best_score: float | None = None
    if len(base_role_foods) == 3:
        for quantity in _iter_quantity_candidates(replacement_food, estimated_quantity):
            support_foods = [
                *existing_support_foods,
                {
                    "role": slot["role"],
                    "food_code": replacement_food["code"],
                    "quantity": quantity,
                },
            ]
            strict_solution = build_exact_meal_solution(
                meal=meal,
                role_foods=base_role_foods,
                support_food_specs=support_foods,
                candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
                food_lookup=candidate_food_lookup,
                training_focus=training_focus,
                meal_slot=meal_slot,
            )
            if strict_solution:
                candidate_score = _score_support_solution(
                    strict_solution,
                    current_food=current_food,
                    replacement_food_code=replacement_food["code"],
                )
                if best_solution is None or best_score is None or candidate_score < best_score:
                    best_solution = strict_solution
                    best_score = candidate_score

    if best_solution is not None:
        return best_solution, "strict"

    for quantity in _iter_quantity_candidates(replacement_food, estimated_quantity):
        support_foods = [
            *existing_support_foods,
            {
                "role": slot["role"],
                "food_code": replacement_food["code"],
                "quantity": quantity,
            },
        ]
        try:
            relaxed_solution = find_exact_solution_for_meal(
                meal=meal,
                meal_index=meal_index,
                meals_count=meals_count,
                training_focus=training_focus,
                food_lookup={
                    **get_internal_food_lookup(),
                    **candidate_food_lookup,
                },
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                forced_support_foods=support_foods,
                excluded_food_codes={current_food_code},
            )
        except (FoodPreferenceConflictError, HTTPException):
            continue

        if relaxed_solution:
            return relaxed_solution, "relaxed"

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            f"No se pudo reconstruir la comida usando '{replacement_food['name']}' como sustituto compatible. "
            "Prueba con otra alternativa o regenera la comida completa."
        ),
    )


def _build_updated_meal_payload(meal, meal_solution: dict[str, Any]) -> dict[str, Any]:
    return {
        "meal_number": meal.meal_number,
        "distribution_percentage": meal.distribution_percentage or 0.0,
        "target_calories": meal.target_calories,
        "target_protein_grams": meal.target_protein_grams,
        "target_fat_grams": meal.target_fat_grams,
        "target_carb_grams": meal.target_carb_grams,
        "actual_calories": meal_solution["actual_calories"],
        "actual_protein_grams": meal_solution["actual_protein_grams"],
        "actual_fat_grams": meal_solution["actual_fat_grams"],
        "actual_carb_grams": meal_solution["actual_carb_grams"],
        "calorie_difference": meal_solution["calorie_difference"],
        "protein_difference": meal_solution["protein_difference"],
        "fat_difference": meal_solution["fat_difference"],
        "carb_difference": meal_solution["carb_difference"],
        "foods": meal_solution["foods"],
    }


def _extract_food_portion(meal_solution: dict[str, Any], food_code: str) -> dict[str, Any] | None:
    return next(
        (
            food
            for food in meal_solution.get("foods", [])
            if food.get("food_code") == food_code
        ),
        None,
    )


def _build_replacement_option(
    *,
    current_food,
    replacement_food: dict[str, Any],
    meal_solution: dict[str, Any],
    rebuild_strategy: str,
) -> FoodReplacementOption | None:
    replacement_portion = _extract_food_portion(meal_solution, replacement_food["code"])
    if not replacement_portion:
        return None

    note = (
        "Encaja ajustando solo la pieza sustituida dentro de la comida."
        if rebuild_strategy == "strict"
        else "Necesita un reajuste mas flexible del resto de la comida para cuadrar macros."
    )

    return FoodReplacementOption(
        food_code=replacement_food["code"],
        name=replacement_food["name"],
        category=replacement_food.get("category", "otros"),
        functional_group=derive_functional_group(replacement_food),
        source=str(replacement_food.get("source") or "internal"),
        recommended_quantity=float(replacement_portion["quantity"]),
        recommended_unit=str(replacement_portion["unit"]),
        recommended_grams=float(replacement_portion["grams"]) if replacement_portion.get("grams") is not None else None,
        calories=float(replacement_portion["calories"]),
        protein_grams=float(replacement_portion["protein_grams"]),
        fat_grams=float(replacement_portion["fat_grams"]),
        carb_grams=float(replacement_portion["carb_grams"]),
        calorie_delta_vs_current=float(replacement_portion["calories"]) - float(current_food.calories),
        protein_delta_vs_current=float(replacement_portion["protein_grams"]) - float(current_food.protein_grams),
        fat_delta_vs_current=float(replacement_portion["fat_grams"]) - float(current_food.fat_grams),
        carb_delta_vs_current=float(replacement_portion["carb_grams"]) - float(current_food.carb_grams),
        meal_calorie_difference=float(meal_solution["calorie_difference"]),
        meal_protein_difference=float(meal_solution["protein_difference"]),
        meal_fat_difference=float(meal_solution["fat_difference"]),
        meal_carb_difference=float(meal_solution["carb_difference"]),
        strategy=rebuild_strategy,  # type: ignore[arg-type]
        note=note,
    )


def _build_replacement_option_sort_score(
    option: FoodReplacementOption,
    *,
    current_food,
    replacement_food: dict[str, Any],
    slot: dict[str, str],
) -> float:
    current_reference_quantity = float(current_food.grams or current_food.quantity or 0.0)
    replacement_reference_quantity = float(option.recommended_grams or option.recommended_quantity or 0.0)
    quantity_penalty = 0.0

    if current_reference_quantity > 0 and replacement_reference_quantity > 0:
        quantity_ratio = max(current_reference_quantity, replacement_reference_quantity) / max(
            min(current_reference_quantity, replacement_reference_quantity),
            1.0,
        )
        tolerance = 2.4 if slot["role"] == "fat" else 2.0 if slot["kind"] == "support" else 1.75
        quantity_penalty += max(0.0, quantity_ratio - tolerance) * 3.2

    replacement_quantity = float(option.recommended_quantity or 0.0)
    default_quantity = float(replacement_food.get("default_quantity") or 0.0)
    if default_quantity > 0 and replacement_quantity > 0:
        relative_deviation = abs(replacement_quantity - default_quantity) / default_quantity
        deviation_tolerance = 1.1 if slot["kind"] == "support" else 0.85
        quantity_penalty += max(0.0, relative_deviation - deviation_tolerance) * 2.4

    min_quantity = float(replacement_food.get("min_quantity") or 0.0)
    if min_quantity > 0 and replacement_quantity < min_quantity * 0.7:
        quantity_penalty += ((min_quantity * 0.7) - replacement_quantity) / max(min_quantity, 1.0) * 12.0

    max_quantity = float(replacement_food.get("max_quantity") or 0.0)
    if max_quantity > 0 and replacement_quantity > max_quantity * 1.1:
        quantity_penalty += (replacement_quantity - (max_quantity * 1.1)) / max(max_quantity, 1.0) * 10.0

    return (
        (8.0 if option.strategy == "relaxed" else 0.0)
        + abs(option.meal_calorie_difference) * 0.12
        + abs(option.meal_protein_difference) * 1.6
        + abs(option.meal_fat_difference) * 1.6
        + abs(option.meal_carb_difference) * 1.2
        + quantity_penalty
    )


def _evaluate_replacement_candidate(
    *,
    current_food,
    replacement_food: dict[str, Any],
    meal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    slot: dict[str, str],
    inferred_plan: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    preference_profile: dict[str, Any],
    daily_food_usage: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    updated_meal_solution, rebuild_strategy = rebuild_meal_after_food_replacement(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        current_food=current_food,
        replacement_food=replacement_food,
        slot=slot,
        inferred_plan=inferred_plan,
        food_lookup=food_lookup,
        preference_profile=preference_profile,
        daily_food_usage=daily_food_usage,
    )
    replacement_option = _build_replacement_option(
        current_food=current_food,
        replacement_food=replacement_food,
        meal_solution=updated_meal_solution,
        rebuild_strategy=rebuild_strategy,
    )
    if replacement_option is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo estimar una cantidad valida para '{replacement_food['name']}'.",
        )

    return {
        "replacement_food": replacement_food,
        "meal_solution": updated_meal_solution,
        "rebuild_strategy": rebuild_strategy,
        "replacement_option": replacement_option,
        "score": _build_replacement_option_sort_score(
            replacement_option,
            current_food=current_food,
            replacement_food=replacement_food,
            slot=slot,
        ),
    }


def list_food_replacement_options(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
    limit: int = 6,
) -> FoodReplacementOptionsResponse:
    context = _build_food_replacement_context(
        database,
        user=user,
        diet_id=diet_id,
        meal_number=meal_number,
        current_food_name=payload.current_food_name,
        current_food_code=payload.current_food_code,
    )
    candidate_foods = find_equivalent_food_candidates(
        current_food_entry=context["current_food_entry"],
        slot=context["slot"],
        preference_profile=context["preference_profile"],
        daily_food_usage=context["daily_food_usage"],
    )
    scored_options: list[tuple[float, FoodReplacementOption]] = []
    seen_food_codes: set[str] = set()

    for candidate_food in candidate_foods:
        if candidate_food["code"] in seen_food_codes:
            continue

        try:
            candidate_evaluation = _evaluate_replacement_candidate(
                current_food=context["current_food"],
                replacement_food=candidate_food,
                meal=context["meal"],
                meal_index=context["meal_index"],
                meals_count=context["diet"].meals_count,
                training_focus=context["training_focus"],
                slot=context["slot"],
                inferred_plan=context["inferred_plan"],
                food_lookup=context["meal_food_lookup"],
                preference_profile=context["preference_profile"],
                daily_food_usage=context["daily_food_usage"],
            )
        except (FoodPreferenceConflictError, HTTPException):
            continue

        scored_options.append(
            (
                float(candidate_evaluation["score"]),
                candidate_evaluation["replacement_option"],
            )
        )
        seen_food_codes.add(candidate_food["code"])

    if not scored_options:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No se encontraron sustitutos compatibles para '{context['current_food'].name}' con el estado actual de la dieta."
            ),
        )

    scored_options.sort(key=lambda item: (item[0], item[1].name.lower()))
    replacement_options = [option for _, option in scored_options[:limit]]
    return FoodReplacementOptionsResponse(
        meal_number=meal_number,
        current_food_name=context["current_food"].name,
        current_food_code=context["current_food"].food_code,
        current_food_quantity=float(context["current_food"].quantity),
        current_food_unit=context["current_food"].unit,
        current_food_grams=float(context["current_food"].grams) if context["current_food"].grams is not None else None,
        options=replacement_options,
    )


def replace_food_in_meal(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
) -> DietMutationResponse:
    context = _build_food_replacement_context(
        database,
        user=user,
        diet_id=diet_id,
        meal_number=meal_number,
        current_food_name=payload.current_food_name,
        current_food_code=payload.current_food_code,
    )

    if payload.replacement_food_name or payload.replacement_food_code:
        candidate_foods = [
            _resolve_requested_replacement_food(
                database,
                payload=payload,
                slot=context["slot"],
                preference_profile=context["preference_profile"],
            )
        ]
        candidate_strategy = "user_requested"
    else:
        candidate_foods = find_equivalent_food_candidates(
            current_food_entry=context["current_food_entry"],
            slot=context["slot"],
            preference_profile=context["preference_profile"],
            daily_food_usage=context["daily_food_usage"],
        )
        if not candidate_foods:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"No se encontraron sustitutos compatibles para '{context['current_food'].name}' con las preferencias y restricciones actuales."
                ),
            )
        candidate_strategy = "auto_equivalent"

    replacement_food: dict[str, Any] | None = None
    updated_meal: dict[str, Any] | None = None
    rebuild_strategy = "strict"
    last_error: Exception | None = None
    if candidate_strategy == "user_requested":
        requested_food = candidate_foods[0]
        candidate_evaluation = _evaluate_replacement_candidate(
            current_food=context["current_food"],
            replacement_food=requested_food,
            meal=context["meal"],
            meal_index=context["meal_index"],
            meals_count=context["diet"].meals_count,
            training_focus=context["training_focus"],
            slot=context["slot"],
            inferred_plan=context["inferred_plan"],
            food_lookup=context["meal_food_lookup"],
            preference_profile=context["preference_profile"],
            daily_food_usage=context["daily_food_usage"],
        )
        replacement_food = requested_food
        updated_meal = candidate_evaluation["meal_solution"]
        rebuild_strategy = candidate_evaluation["rebuild_strategy"]
    else:
        best_candidate_evaluation: dict[str, Any] | None = None
        for candidate_food in candidate_foods:
            if candidate_food["code"] == context["current_food_entry"]["code"]:
                continue

            try:
                candidate_evaluation = _evaluate_replacement_candidate(
                    current_food=context["current_food"],
                    replacement_food=candidate_food,
                    meal=context["meal"],
                    meal_index=context["meal_index"],
                    meals_count=context["diet"].meals_count,
                    training_focus=context["training_focus"],
                    slot=context["slot"],
                    inferred_plan=context["inferred_plan"],
                    food_lookup=context["meal_food_lookup"],
                    preference_profile=context["preference_profile"],
                    daily_food_usage=context["daily_food_usage"],
                )
            except (FoodPreferenceConflictError, HTTPException) as exc:
                last_error = exc
                continue

            if best_candidate_evaluation is None or float(candidate_evaluation["score"]) < float(best_candidate_evaluation["score"]):
                best_candidate_evaluation = candidate_evaluation

        if best_candidate_evaluation is not None:
            replacement_food = best_candidate_evaluation["replacement_food"]
            updated_meal = best_candidate_evaluation["meal_solution"]
            rebuild_strategy = best_candidate_evaluation["rebuild_strategy"]

    if replacement_food is None or updated_meal is None:
        if last_error is not None:
            raise last_error

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo encontrar un sustituto valido distinto al alimento actual.",
        )
    updated_meal_payload = _build_updated_meal_payload(context["meal"], updated_meal)
    updated_diet = persist_updated_meal_in_diet(
        database,
        user=user,
        diet=context["diet"],
        diet_id=diet_id,
        meal_index=context["meal_index"],
        updated_meal=updated_meal_payload,
        preference_profile=context["preference_profile"],
        metadata_overrides={
            "food_catalog_version": context["diet"].food_catalog_version,
            "catalog_source_strategy": context["diet"].catalog_source_strategy,
            "spoonacular_attempted": context["diet"].spoonacular_attempted or replacement_food.get("source") == "spoonacular",
            "spoonacular_attempts": context["diet"].spoonacular_attempts + int(replacement_food.get("source") == "spoonacular"),
        },
    )

    strategy_notes = [
        "Se mantuvieron intactas las demas comidas del dia.",
        "Se reajustaron las cantidades de la comida afectada para acercarse a sus calorias y macros objetivo.",
    ]
    if candidate_strategy == "auto_equivalent":
        strategy_notes.insert(0, "Se eligio un sustituto funcional equivalente priorizando variedad diaria y compatibilidad nutricional.")
    else:
        strategy_notes.insert(0, "Se intento respetar el sustituto propuesto por el usuario dentro de la compatibilidad de la comida.")
    if rebuild_strategy == "relaxed":
        strategy_notes.append("Fue necesario relajar la composicion de la comida para que el sustituto encajara sin rehacer el resto del dia.")

    return DietMutationResponse(
        diet=updated_diet,
        summary=DietMutationSummary(
            action="food_replaced",
            meal_number=meal_number,
            message=(
                f"Se sustituyo '{context['current_food'].name}' por '{replacement_food['name']}' en la comida {meal_number}."
            ),
            current_food_name=context["current_food"].name,
            replacement_food_name=replacement_food["name"],
            preserved_meal_numbers=[
                current_meal.meal_number
                for index, current_meal in enumerate(context["diet"].meals)
                if index != context["meal_index"]
            ],
            changed_food_names=[food["name"] for food in updated_meal_payload.get("foods", [])],
            strategy_notes=strategy_notes,
        ),
    )
