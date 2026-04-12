"""Food-based diet generation and persistence."""
from datetime import UTC, datetime
from itertools import product

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietListItem, DietMeal, TrainingTimeOfDay, serialize_daily_diet, serialize_diet_list_item
from app.schemas.user import UserPublic
from app.services.food_catalog_service import get_food_catalog_version, get_internal_food_lookup, resolve_foods_by_codes
from app.services.meal_distribution_service import generate_meal_distribution_targets, round_distribution_value

DEFAULT_FOOD_DATA_SOURCE = "internal"
CACHE_FOOD_DATA_SOURCE = "cache"
SPOONACULAR_FOOD_DATA_SOURCE = "spoonacular"
CATALOG_SOURCE_STRATEGY_DEFAULT = "internal_catalog_with_optional_spoonacular_enrichment"
DIET_SOURCE_MAP = {
    "internal_catalog": DEFAULT_FOOD_DATA_SOURCE,
    "local_cache": CACHE_FOOD_DATA_SOURCE,
    "spoonacular": SPOONACULAR_FOOD_DATA_SOURCE,
    DEFAULT_FOOD_DATA_SOURCE: DEFAULT_FOOD_DATA_SOURCE,
    CACHE_FOOD_DATA_SOURCE: CACHE_FOOD_DATA_SOURCE,
    SPOONACULAR_FOOD_DATA_SOURCE: SPOONACULAR_FOOD_DATA_SOURCE,
}
EXACT_SOLVER_TOLERANCE = 1e-6
FOOD_VALUE_PRECISION = 2
FOOD_OMIT_THRESHOLD = {
    "g": 0.5,
    "ml": 1.0,
    "unidad": 0.05,
}
SOFT_ROLE_MINIMUMS = {
    "protein": {"g": 55.0, "ml": 125.0, "unidad": 0.5},
    "carb": {"g": 15.0, "ml": 50.0, "unidad": 0.2},
    "fat": {"g": 3.0, "ml": 3.0, "unidad": 0.1},
}
ROLE_DISPLAY_ORDER = {
    "protein": 0,
    "carb": 1,
    "fruit": 2,
    "vegetable": 3,
    "dairy": 4,
    "fat": 5,
}
CORE_MACRO_KEYS = ("protein_grams", "fat_grams", "carb_grams")
MACRO_CALORIE_FACTORS = {
    "protein_grams": 4.0,
    "fat_grams": 9.0,
    "carb_grams": 4.0,
}


def normalize_diet_food_source(value: str | None) -> str:
    return DIET_SOURCE_MAP.get(str(value or "").strip(), DEFAULT_FOOD_DATA_SOURCE)


def round_diet_value(value: float) -> float:
    rounded_value = round_distribution_value(value)
    return 0.0 if abs(rounded_value) < 0.05 else rounded_value


def round_food_value(value: float) -> float:
    rounded_value = round(value, FOOD_VALUE_PRECISION)
    return 0.0 if abs(rounded_value) < 10 ** (-FOOD_VALUE_PRECISION) else rounded_value


def calculate_macro_calories(protein_grams: float, fat_grams: float, carb_grams: float) -> float:
    return (
        (protein_grams * MACRO_CALORIE_FACTORS["protein_grams"])
        + (fat_grams * MACRO_CALORIE_FACTORS["fat_grams"])
        + (carb_grams * MACRO_CALORIE_FACTORS["carb_grams"])
    )


def calculate_difference(actual_value: float, target_value: float) -> float:
    return round_diet_value(actual_value - target_value)


def calculate_difference_summary(
    *,
    target_calories: float,
    target_protein_grams: float,
    target_fat_grams: float,
    target_carb_grams: float,
    actual_calories: float,
    actual_protein_grams: float,
    actual_fat_grams: float,
    actual_carb_grams: float,
) -> dict[str, float]:
    return {
        "calorie_difference": calculate_difference(actual_calories, target_calories),
        "protein_difference": calculate_difference(actual_protein_grams, target_protein_grams),
        "fat_difference": calculate_difference(actual_fat_grams, target_fat_grams),
        "carb_difference": calculate_difference(actual_carb_grams, target_carb_grams),
    }


def get_meal_slot(meal_index: int, meals_count: int) -> str:
    if meal_index == 0 or (meals_count >= 5 and meal_index == 1):
        return "early"
    if meal_index == meals_count - 1:
        return "late"
    return "main"


def rotate_codes(codes: list[str], rotation_seed: int) -> list[str]:
    if not codes:
        return []

    shift = rotation_seed % len(codes)
    return codes[shift:] + codes[:shift]


def get_role_candidate_codes(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
) -> dict[str, list[str]]:
    meal_slot = get_meal_slot(meal_index, meals_count)
    rotation_seed = meal_index + meals_count
    low_fat_focus = training_focus or meal.target_fat_grams <= 10

    if meal_slot == "early":
        if low_fat_focus:
            protein_codes = ["egg_whites", "turkey_breast", "greek_yogurt", "chicken_breast"]
        elif meal.target_carb_grams <= 14:
            protein_codes = ["eggs", "tuna", "turkey_breast", "chicken_breast"]
        else:
            protein_codes = ["turkey_breast", "egg_whites", "greek_yogurt", "eggs", "chicken_breast"]

        if meal.target_carb_grams >= 70:
            carb_codes = ["oats", "whole_wheat_bread", "rice", "banana", "potato"]
        elif meal.target_carb_grams >= 30:
            carb_codes = ["whole_wheat_bread", "oats", "rice", "banana", "potato"]
        else:
            carb_codes = ["potato", "whole_wheat_bread", "banana", "rice"]
    elif meal_slot == "late":
        if low_fat_focus:
            protein_codes = ["turkey_breast", "tuna", "chicken_breast", "egg_whites"]
        elif meal.target_carb_grams <= 14:
            protein_codes = ["tuna", "eggs", "turkey_breast", "chicken_breast"]
        else:
            protein_codes = ["turkey_breast", "tuna", "chicken_breast", "eggs"]

        if meal.target_carb_grams >= 100:
            carb_codes = ["rice", "pasta", "potato", "banana"]
        elif meal.target_carb_grams >= 35:
            carb_codes = ["rice", "potato", "pasta", "whole_wheat_bread", "banana"]
        else:
            carb_codes = ["potato", "whole_wheat_bread", "rice", "banana"]
    else:
        if low_fat_focus:
            protein_codes = ["chicken_breast", "turkey_breast", "tuna", "egg_whites"]
        elif meal.target_carb_grams <= 14:
            protein_codes = ["tuna", "eggs", "chicken_breast", "turkey_breast"]
        else:
            protein_codes = ["chicken_breast", "turkey_breast", "tuna", "eggs"]

        if meal.target_carb_grams >= 120:
            carb_codes = ["rice", "pasta", "potato"]
        elif meal.target_carb_grams >= 45:
            carb_codes = ["rice", "potato", "pasta", "whole_wheat_bread", "banana"]
        else:
            carb_codes = ["potato", "whole_wheat_bread", "rice", "banana"]

    fat_codes = ["olive_oil", "avocado", "mixed_nuts"]
    if meal.target_fat_grams >= 16 and not training_focus:
        fat_codes = ["avocado", "olive_oil", "mixed_nuts"]

    return {
        "protein": rotate_codes(protein_codes, rotation_seed),
        "carb": rotate_codes(carb_codes, rotation_seed + 1),
        "fat": rotate_codes(fat_codes, rotation_seed + 2),
    }


def get_support_option_specs(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
) -> list[list[dict]]:
    meal_slot = get_meal_slot(meal_index, meals_count)
    support_options: list[list[dict]] = [[]]

    if meal_slot != "early" and meal.target_calories >= 320 and meal.target_carb_grams >= 15:
        support_options.append(
            [
                {
                    "role": "vegetable",
                    "food_code": "mixed_vegetables",
                    "quantity": 80.0 if meal.target_calories < 520 else 120.0,
                }
            ]
        )

    if (meal_slot == "early" or training_focus) and meal.target_carb_grams >= 40:
        support_options.append(
            [
                {
                    "role": "fruit",
                    "food_code": "banana",
                    "quantity": 0.5 if meal.target_carb_grams < 80 else 1.0,
                }
            ]
        )

    if meal_slot == "early" and meal.target_calories <= 260 and meal.target_protein_grams <= 26:
        support_options.append(
            [
                {
                    "role": "dairy",
                    "food_code": "greek_yogurt",
                    "quantity": 1.0,
                }
            ]
        )

    return support_options


def get_food_macro_density(food: dict) -> dict[str, float]:
    reference_amount = float(food["reference_amount"])
    return {
        macro_key: float(food[macro_key]) / reference_amount
        for macro_key in CORE_MACRO_KEYS
    }


def build_precise_food_values(food: dict, quantity: float) -> dict[str, float]:
    scale = quantity / float(food["reference_amount"])
    grams = float(food["grams_per_reference"]) * scale
    protein_grams = float(food["protein_grams"]) * scale
    fat_grams = float(food["fat_grams"]) * scale
    carb_grams = float(food["carb_grams"]) * scale

    return {
        "quantity": quantity,
        "grams": grams,
        "protein_grams": protein_grams,
        "fat_grams": fat_grams,
        "carb_grams": carb_grams,
        "calories": calculate_macro_calories(protein_grams, fat_grams, carb_grams),
    }


def build_food_portion(food: dict, quantity: float) -> dict:
    precise_values = build_precise_food_values(food, quantity)
    food_source = normalize_diet_food_source(food.get("source"))
    origin_source = normalize_diet_food_source(food.get("origin_source", food.get("source")))
    return {
        "food_code": food["code"],
        "source": food_source,
        "origin_source": origin_source,
        "spoonacular_id": food.get("spoonacular_id"),
        "name": food["name"],
        "category": food["category"],
        "quantity": round_food_value(precise_values["quantity"]),
        "unit": food["reference_unit"],
        "grams": round_food_value(precise_values["grams"]),
        "calories": round_food_value(precise_values["calories"]),
        "protein_grams": round_food_value(precise_values["protein_grams"]),
        "fat_grams": round_food_value(precise_values["fat_grams"]),
        "carb_grams": round_food_value(precise_values["carb_grams"]),
    }


def calculate_support_totals(
    support_food_specs: list[dict],
    food_lookup: dict[str, dict],
) -> dict[str, float]:
    totals = {
        "calories": 0.0,
        "protein_grams": 0.0,
        "fat_grams": 0.0,
        "carb_grams": 0.0,
    }
    for support_food in support_food_specs:
        precise_values = build_precise_food_values(
            food_lookup[support_food["food_code"]],
            float(support_food["quantity"]),
        )
        for field_name in totals:
            totals[field_name] += precise_values[field_name]

    return totals


def solve_linear_system(matrix: list[list[float]], values: list[float]) -> list[float] | None:
    size = len(values)
    augmented = [row[:] + [values[index]] for index, row in enumerate(matrix)]

    for column in range(size):
        pivot_row = max(
            range(column, size),
            key=lambda row_index: abs(augmented[row_index][column]),
        )
        if abs(augmented[pivot_row][column]) <= EXACT_SOLVER_TOLERANCE:
            return None

        if pivot_row != column:
            augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]

        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]

        for row_index in range(size):
            if row_index == column:
                continue

            factor = augmented[row_index][column]
            augmented[row_index] = [
                current_value - (factor * pivot_component)
                for current_value, pivot_component in zip(augmented[row_index], augmented[column], strict=True)
            ]

    return [augmented[row_index][-1] for row_index in range(size)]


def get_soft_role_minimum(food: dict, role: str) -> float:
    unit = food["reference_unit"]
    return SOFT_ROLE_MINIMUMS.get(role, {}).get(unit, 0.0)


def get_food_visibility_threshold(food: dict) -> float:
    return FOOD_OMIT_THRESHOLD.get(food["reference_unit"], 0.0)


def build_solution_score(
    *,
    role_foods: dict[str, dict],
    role_quantities: dict[str, float],
    support_foods: list[dict],
    candidate_indexes: dict[str, int],
    training_focus: bool,
    meal_slot: str,
) -> float:
    score = 0.0

    for role, food in role_foods.items():
        quantity = role_quantities[role]
        preferred_quantity = float(food["default_quantity"])
        soft_minimum = get_soft_role_minimum(food, role)

        score += candidate_indexes[role] * 0.12
        score += abs(quantity - preferred_quantity) / max(preferred_quantity, 1.0) * 0.3

        if quantity < soft_minimum:
            score += ((soft_minimum - quantity) / max(soft_minimum, 1.0)) * 2.2

        if quantity > float(food["max_quantity"]) * 0.9:
            score += ((quantity - (float(food["max_quantity"]) * 0.9)) / max(float(food["max_quantity"]), 1.0)) * 6.0

        if role == "fat" and food["code"] == "olive_oil":
            score -= 0.15

        if role == "carb" and training_focus and food["code"] in {"rice", "pasta", "oats"}:
            score -= 0.2

        if role == "protein" and meal_slot == "early" and food["code"] in {"egg_whites", "greek_yogurt"}:
            score -= 0.1

    if support_foods:
        score += 0.15 * len(support_foods)

        if meal_slot != "early" and support_foods[0]["role"] == "vegetable":
            score -= 0.05
        if training_focus and support_foods[0]["role"] == "fruit":
            score -= 0.05

    return score


def build_exact_meal_solution(
    *,
    meal: DietMeal,
    role_foods: dict[str, dict],
    support_food_specs: list[dict],
    candidate_indexes: dict[str, int],
    food_lookup: dict[str, dict],
    training_focus: bool,
    meal_slot: str,
) -> dict | None:
    all_codes = [
        role_foods["protein"]["code"],
        role_foods["carb"]["code"],
        role_foods["fat"]["code"],
        *[support_food["food_code"] for support_food in support_food_specs],
    ]
    if len(set(all_codes)) != len(all_codes):
        return None

    support_totals = calculate_support_totals(support_food_specs, food_lookup)
    remaining_targets = {
        "protein_grams": meal.target_protein_grams - support_totals["protein_grams"],
        "fat_grams": meal.target_fat_grams - support_totals["fat_grams"],
        "carb_grams": meal.target_carb_grams - support_totals["carb_grams"],
    }

    if any(target_value < -EXACT_SOLVER_TOLERANCE for target_value in remaining_targets.values()):
        return None

    matrix = [
        [
            get_food_macro_density(role_foods["protein"])[macro_key],
            get_food_macro_density(role_foods["carb"])[macro_key],
            get_food_macro_density(role_foods["fat"])[macro_key],
        ]
        for macro_key in CORE_MACRO_KEYS
    ]
    target_vector = [remaining_targets[macro_key] for macro_key in CORE_MACRO_KEYS]
    solved_quantities = solve_linear_system(matrix, target_vector)
    if solved_quantities is None:
        return None

    role_quantities = {
        "protein": max(0.0, solved_quantities[0]),
        "carb": max(0.0, solved_quantities[1]),
        "fat": max(0.0, solved_quantities[2]),
    }

    for role, quantity in role_quantities.items():
        if quantity - float(role_foods[role]["max_quantity"]) > EXACT_SOLVER_TOLERANCE:
            return None

        visibility_threshold = get_food_visibility_threshold(role_foods[role])
        if role == "protein" and quantity < visibility_threshold:
            return None

    foods: list[dict] = []
    for role, food in role_foods.items():
        quantity = role_quantities[role]
        if quantity >= get_food_visibility_threshold(food):
            foods.append(
                {
                    "role": role,
                    **build_food_portion(food, quantity),
                }
            )

    for support_food in support_food_specs:
        foods.append(
            {
                "role": support_food["role"],
                **build_food_portion(
                    food_lookup[support_food["food_code"]],
                    float(support_food["quantity"]),
                ),
            }
        )

    foods.sort(key=lambda food: (ROLE_DISPLAY_ORDER.get(food["role"], 99), food["name"]))

    exact_actuals = {
        "actual_calories": round_diet_value(calculate_macro_calories(
            meal.target_protein_grams,
            meal.target_fat_grams,
            meal.target_carb_grams,
        )),
        "actual_protein_grams": round_diet_value(meal.target_protein_grams),
        "actual_fat_grams": round_diet_value(meal.target_fat_grams),
        "actual_carb_grams": round_diet_value(meal.target_carb_grams),
        "calorie_difference": 0.0,
        "protein_difference": 0.0,
        "fat_difference": 0.0,
        "carb_difference": 0.0,
    }

    return {
        "foods": [{key: value for key, value in food.items() if key != "role"} for food in foods],
        "selected_role_codes": {role: food["code"] for role, food in role_foods.items()},
        "support_food_specs": [
            {
                "role": support_food["role"],
                "food_code": support_food["food_code"],
                "quantity": float(support_food["quantity"]),
            }
            for support_food in support_food_specs
        ],
        "score": build_solution_score(
            role_foods=role_foods,
            role_quantities=role_quantities,
            support_foods=support_food_specs,
            candidate_indexes=candidate_indexes,
            training_focus=training_focus,
            meal_slot=meal_slot,
        ),
        **exact_actuals,
    }


def find_exact_solution_for_meal(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict],
) -> dict:
    candidate_codes = get_role_candidate_codes(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    support_options = get_support_option_specs(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    meal_slot = get_meal_slot(meal_index, meals_count)

    best_solution: dict | None = None

    def evaluate_candidate_sets(role_codes: dict[str, list[str]], extra_support_options: list[list[dict]]) -> None:
        nonlocal best_solution

        for support_food_specs in extra_support_options:
            for protein_index, carb_index, fat_index in product(
                range(len(role_codes["protein"])),
                range(len(role_codes["carb"])),
                range(len(role_codes["fat"])),
            ):
                role_foods = {
                    "protein": food_lookup[role_codes["protein"][protein_index]],
                    "carb": food_lookup[role_codes["carb"][carb_index]],
                    "fat": food_lookup[role_codes["fat"][fat_index]],
                }
                candidate_indexes = {
                    "protein": protein_index,
                    "carb": carb_index,
                    "fat": fat_index,
                }
                candidate_solution = build_exact_meal_solution(
                    meal=meal,
                    role_foods=role_foods,
                    support_food_specs=support_food_specs,
                    candidate_indexes=candidate_indexes,
                    food_lookup=food_lookup,
                    training_focus=training_focus,
                    meal_slot=meal_slot,
                )
                if not candidate_solution:
                    continue

                if best_solution is None or candidate_solution["score"] < best_solution["score"]:
                    best_solution = candidate_solution

    evaluate_candidate_sets(candidate_codes, support_options)
    if best_solution:
        return best_solution

    fallback_role_codes = {
        "protein": [
            "chicken_breast",
            "turkey_breast",
            "tuna",
            "egg_whites",
            "greek_yogurt",
            "eggs",
        ],
        "carb": [
            "rice",
            "potato",
            "pasta",
            "whole_wheat_bread",
            "banana",
            "oats",
        ],
        "fat": ["olive_oil", "avocado", "mixed_nuts"],
    }
    evaluate_candidate_sets(fallback_role_codes, [[]])

    if best_solution:
        return best_solution

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to fit meal exactly with current food catalog",
    )


def calculate_meal_totals_from_foods(foods: list[dict]) -> dict[str, float]:
    actual_protein_grams = round_diet_value(sum(float(food["protein_grams"]) for food in foods))
    actual_fat_grams = round_diet_value(sum(float(food["fat_grams"]) for food in foods))
    actual_carb_grams = round_diet_value(sum(float(food["carb_grams"]) for food in foods))
    actual_calories = round_diet_value(calculate_macro_calories(
        actual_protein_grams,
        actual_fat_grams,
        actual_carb_grams,
    ))

    return {
        "actual_calories": actual_calories,
        "actual_protein_grams": actual_protein_grams,
        "actual_fat_grams": actual_fat_grams,
        "actual_carb_grams": actual_carb_grams,
    }


def generate_food_based_meal(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    meal_plan: dict,
    food_lookup: dict[str, dict],
) -> dict:
    meal_slot = get_meal_slot(meal_index, meals_count)
    selected_role_codes = meal_plan.get("selected_role_codes", {})
    selected_role_foods = {
        role: food_lookup[food_code]
        for role, food_code in selected_role_codes.items()
    }
    meal_fit = build_exact_meal_solution(
        meal=meal,
        role_foods=selected_role_foods,
        support_food_specs=meal_plan.get("support_food_specs", []),
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=food_lookup,
        training_focus=training_focus,
        meal_slot=meal_slot,
    )
    if meal_fit is None:
        meal_fit = meal_plan

    return {
        "meal_number": meal.meal_number,
        "distribution_percentage": round_diet_value(meal.distribution_percentage or 0),
        "target_calories": round_diet_value(meal.target_calories),
        "target_protein_grams": round_diet_value(meal.target_protein_grams),
        "target_fat_grams": round_diet_value(meal.target_fat_grams),
        "target_carb_grams": round_diet_value(meal.target_carb_grams),
        "actual_calories": meal_fit["actual_calories"],
        "actual_protein_grams": meal_fit["actual_protein_grams"],
        "actual_fat_grams": meal_fit["actual_fat_grams"],
        "actual_carb_grams": meal_fit["actual_carb_grams"],
        "calorie_difference": meal_fit["calorie_difference"],
        "protein_difference": meal_fit["protein_difference"],
        "fat_difference": meal_fit["fat_difference"],
        "carb_difference": meal_fit["carb_difference"],
        "foods": meal_fit["foods"],
    }


def collect_selected_food_codes(meal_plans: list[dict]) -> list[str]:
    selected_codes: list[str] = []
    seen_codes: set[str] = set()

    def add_code(food_code: str) -> None:
        if food_code in seen_codes:
            return

        seen_codes.add(food_code)
        selected_codes.append(food_code)

    for meal_plan in meal_plans:
        for food_code in meal_plan.get("selected_role_codes", {}).values():
            add_code(food_code)

        for support_food in meal_plan.get("support_food_specs", []):
            add_code(support_food["food_code"])

    return selected_codes


def summarize_food_sources(meals: list[dict]) -> tuple[str, list[str]]:
    source_order = [DEFAULT_FOOD_DATA_SOURCE, CACHE_FOOD_DATA_SOURCE, SPOONACULAR_FOOD_DATA_SOURCE]
    used_sources = {
        normalize_diet_food_source(food.get("source", DEFAULT_FOOD_DATA_SOURCE))
        for meal in meals
        for food in meal.get("foods", [])
    }
    ordered_sources = [source for source in source_order if source in used_sources]
    if not ordered_sources:
        ordered_sources = [DEFAULT_FOOD_DATA_SOURCE]

    return (
        ordered_sources[0] if len(ordered_sources) == 1 else "mixed",
        ordered_sources,
    )


def calculate_daily_totals_from_meals(
    *,
    target_calories: float,
    target_protein_grams: float,
    target_fat_grams: float,
    target_carb_grams: float,
    meals: list[dict],
) -> dict[str, float]:
    actual_calories = round_diet_value(sum(meal["actual_calories"] for meal in meals))
    actual_protein_grams = round_diet_value(sum(meal["actual_protein_grams"] for meal in meals))
    actual_fat_grams = round_diet_value(sum(meal["actual_fat_grams"] for meal in meals))
    actual_carb_grams = round_diet_value(sum(meal["actual_carb_grams"] for meal in meals))

    return {
        "actual_calories": actual_calories,
        "actual_protein_grams": actual_protein_grams,
        "actual_fat_grams": actual_fat_grams,
        "actual_carb_grams": actual_carb_grams,
        **calculate_difference_summary(
            target_calories=target_calories,
            target_protein_grams=target_protein_grams,
            target_fat_grams=target_fat_grams,
            target_carb_grams=target_carb_grams,
            actual_calories=actual_calories,
            actual_protein_grams=actual_protein_grams,
            actual_fat_grams=actual_fat_grams,
            actual_carb_grams=actual_carb_grams,
        ),
    }


def generate_food_based_diet(
    database,
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    meal_distribution, focus_indexes = generate_meal_distribution_targets(
        user=user,
        meals_count=meals_count,
        custom_percentages=custom_percentages,
        training_time_of_day=training_time_of_day,
    )
    internal_food_lookup = get_internal_food_lookup()
    planned_meals = [
        find_exact_solution_for_meal(
            meal=DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=meal_distribution["training_optimization_applied"] and meal_index in focus_indexes,
            food_lookup=internal_food_lookup,
        )
        for meal_index, meal in enumerate(meal_distribution["meals"])
    ]
    selected_food_codes = collect_selected_food_codes(planned_meals)
    resolved_food_lookup, lookup_metadata = resolve_foods_by_codes(
        database,
        selected_food_codes,
    )
    food_lookup = {
        **internal_food_lookup,
        **resolved_food_lookup,
    }
    generated_meals = [
        generate_food_based_meal(
            meal=DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=meal_distribution["training_optimization_applied"] and meal_index in focus_indexes,
            meal_plan=planned_meals[meal_index],
            food_lookup=food_lookup,
        )
        for meal_index, meal in enumerate(meal_distribution["meals"])
    ]
    food_data_source, food_data_sources = summarize_food_sources(generated_meals)
    daily_totals = calculate_daily_totals_from_meals(
        target_calories=meal_distribution["target_calories"],
        target_protein_grams=meal_distribution["protein_grams"],
        target_fat_grams=meal_distribution["fat_grams"],
        target_carb_grams=meal_distribution["carb_grams"],
        meals=generated_meals,
    )

    return {
        "meals_count": meal_distribution["meals_count"],
        "target_calories": meal_distribution["target_calories"],
        "protein_grams": meal_distribution["protein_grams"],
        "fat_grams": meal_distribution["fat_grams"],
        "carb_grams": meal_distribution["carb_grams"],
        "actual_calories": daily_totals["actual_calories"],
        "actual_protein_grams": daily_totals["actual_protein_grams"],
        "actual_fat_grams": daily_totals["actual_fat_grams"],
        "actual_carb_grams": daily_totals["actual_carb_grams"],
        "calorie_difference": daily_totals["calorie_difference"],
        "protein_difference": daily_totals["protein_difference"],
        "fat_difference": daily_totals["fat_difference"],
        "carb_difference": daily_totals["carb_difference"],
        "distribution_percentages": meal_distribution["distribution_percentages"],
        "training_time_of_day": meal_distribution["training_time_of_day"],
        "training_optimization_applied": meal_distribution["training_optimization_applied"],
        "food_data_source": food_data_source,
        "food_data_sources": food_data_sources,
        "food_catalog_version": lookup_metadata.get("food_catalog_version", get_food_catalog_version()),
        "catalog_source_strategy": lookup_metadata.get("catalog_source_strategy", CATALOG_SOURCE_STRATEGY_DEFAULT),
        "spoonacular_attempted": lookup_metadata.get("spoonacular_attempted", False),
        "spoonacular_attempts": lookup_metadata.get("spoonacular_attempts", 0),
        "spoonacular_hits": lookup_metadata.get("spoonacular_hits", 0),
        "cache_hits": lookup_metadata.get("cache_hits", 0),
        "internal_fallbacks": lookup_metadata.get("internal_fallbacks", 0),
        "resolved_foods_count": lookup_metadata.get("resolved_foods_count", len(selected_food_codes)),
        "meals": generated_meals,
    }


def generate_daily_diet(
    database,
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    return generate_food_based_diet(
        database,
        user=user,
        meals_count=meals_count,
        custom_percentages=custom_percentages,
        training_time_of_day=training_time_of_day,
    )


def save_diet(database, user_id: str, diet_payload: dict) -> DailyDiet:
    diet_document = {
        "user_id": ObjectId(user_id),
        "created_at": datetime.now(UTC),
        "meals_count": diet_payload["meals_count"],
        "target_calories": round_diet_value(diet_payload["target_calories"]),
        "protein_grams": round_diet_value(diet_payload["protein_grams"]),
        "fat_grams": round_diet_value(diet_payload["fat_grams"]),
        "carb_grams": round_diet_value(diet_payload["carb_grams"]),
        "actual_calories": round_diet_value(diet_payload["actual_calories"]),
        "actual_protein_grams": round_diet_value(diet_payload["actual_protein_grams"]),
        "actual_fat_grams": round_diet_value(diet_payload["actual_fat_grams"]),
        "actual_carb_grams": round_diet_value(diet_payload["actual_carb_grams"]),
        "calorie_difference": round_diet_value(diet_payload["calorie_difference"]),
        "protein_difference": round_diet_value(diet_payload["protein_difference"]),
        "fat_difference": round_diet_value(diet_payload["fat_difference"]),
        "carb_difference": round_diet_value(diet_payload["carb_difference"]),
        "distribution_percentages": [
            round_diet_value(value) for value in diet_payload["distribution_percentages"]
        ],
        "training_time_of_day": diet_payload["training_time_of_day"],
        "training_optimization_applied": diet_payload["training_optimization_applied"],
        "food_data_source": diet_payload.get("food_data_source", DEFAULT_FOOD_DATA_SOURCE),
        "food_data_sources": diet_payload.get("food_data_sources", [diet_payload.get("food_data_source", DEFAULT_FOOD_DATA_SOURCE)]),
        "food_catalog_version": diet_payload.get("food_catalog_version"),
        "catalog_source_strategy": diet_payload.get("catalog_source_strategy", CATALOG_SOURCE_STRATEGY_DEFAULT),
        "spoonacular_attempted": diet_payload.get("spoonacular_attempted", False),
        "spoonacular_attempts": diet_payload.get("spoonacular_attempts", 0),
        "spoonacular_hits": diet_payload.get("spoonacular_hits", 0),
        "cache_hits": diet_payload.get("cache_hits", 0),
        "internal_fallbacks": diet_payload.get("internal_fallbacks", 0),
        "resolved_foods_count": diet_payload.get("resolved_foods_count", 0),
        "meals": [
            {
                "meal_number": meal["meal_number"],
                "distribution_percentage": round_diet_value(meal["distribution_percentage"]),
                "target_calories": round_diet_value(meal["target_calories"]),
                "target_protein_grams": round_diet_value(meal["target_protein_grams"]),
                "target_fat_grams": round_diet_value(meal["target_fat_grams"]),
                "target_carb_grams": round_diet_value(meal["target_carb_grams"]),
                "actual_calories": round_diet_value(meal["actual_calories"]),
                "actual_protein_grams": round_diet_value(meal["actual_protein_grams"]),
                "actual_fat_grams": round_diet_value(meal["actual_fat_grams"]),
                "actual_carb_grams": round_diet_value(meal["actual_carb_grams"]),
                "calorie_difference": round_diet_value(meal["calorie_difference"]),
                "protein_difference": round_diet_value(meal["protein_difference"]),
                "fat_difference": round_diet_value(meal["fat_difference"]),
                "carb_difference": round_diet_value(meal["carb_difference"]),
                "foods": [
                    {
                        "food_code": food.get("food_code"),
                        "source": normalize_diet_food_source(food.get("source", DEFAULT_FOOD_DATA_SOURCE)),
                        "origin_source": normalize_diet_food_source(
                            food.get("origin_source", food.get("source", DEFAULT_FOOD_DATA_SOURCE))
                        ),
                        "spoonacular_id": food.get("spoonacular_id"),
                        "name": food["name"],
                        "category": food["category"],
                        "quantity": round_food_value(float(food["quantity"])),
                        "unit": food["unit"],
                        "grams": round_food_value(float(food["grams"])) if food.get("grams") is not None else None,
                        "calories": round_food_value(float(food["calories"])),
                        "protein_grams": round_food_value(float(food["protein_grams"])),
                        "fat_grams": round_food_value(float(food["fat_grams"])),
                        "carb_grams": round_food_value(float(food["carb_grams"])),
                    }
                    for food in meal.get("foods", [])
                ],
            }
            for meal in diet_payload["meals"]
        ],
    }
    inserted = database.diets.insert_one(diet_document)
    created_diet = database.diets.find_one({"_id": inserted.inserted_id})
    return serialize_daily_diet(created_diet)


def list_user_diets(database, user_id: str) -> list[DietListItem]:
    documents = database.diets.find({"user_id": ObjectId(user_id)}).sort([("created_at", -1)])
    return [serialize_diet_list_item(document) for document in documents]


def get_user_diet_by_id(database, user_id: str, diet_id: str) -> DailyDiet:
    if not ObjectId.is_valid(diet_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet not found",
        )

    document = database.diets.find_one(
        {
            "_id": ObjectId(diet_id),
            "user_id": ObjectId(user_id),
        }
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet not found",
        )

    return serialize_daily_diet(document)


def get_latest_user_diet(database, user_id: str) -> DailyDiet | None:
    document = database.diets.find_one(
        {"user_id": ObjectId(user_id)},
        sort=[("created_at", -1)],
    )
    if not document:
        return None

    return serialize_daily_diet(document)
