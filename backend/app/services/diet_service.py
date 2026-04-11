"""Food-based diet generation and persistence."""
from datetime import UTC, datetime
from itertools import product

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietListItem, DietMeal, TrainingTimeOfDay, serialize_daily_diet, serialize_diet_list_item
from app.schemas.user import UserPublic
from app.services.food_catalog_service import get_food_catalog_version, get_food_lookup
from app.services.meal_distribution_service import generate_meal_distribution_targets, round_distribution_value

FOOD_DATA_SOURCE = "internal_catalog"
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


def get_support_options(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict],
) -> list[list[dict]]:
    meal_slot = get_meal_slot(meal_index, meals_count)
    support_options: list[list[dict]] = [[]]

    if meal_slot != "early" and meal.target_calories >= 320 and meal.target_carb_grams >= 15:
        support_options.append(
            [
                {
                    "role": "vegetable",
                    "food": food_lookup["mixed_vegetables"],
                    "quantity": 80.0 if meal.target_calories < 520 else 120.0,
                }
            ]
        )

    if (meal_slot == "early" or training_focus) and meal.target_carb_grams >= 40:
        support_options.append(
            [
                {
                    "role": "fruit",
                    "food": food_lookup["banana"],
                    "quantity": 0.5 if meal.target_carb_grams < 80 else 1.0,
                }
            ]
        )

    if meal_slot == "early" and meal.target_calories <= 260 and meal.target_protein_grams <= 26:
        support_options.append(
            [
                {
                    "role": "dairy",
                    "food": food_lookup["greek_yogurt"],
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


def build_food_portion(food: dict, quantity: float, source: str) -> dict:
    precise_values = build_precise_food_values(food, quantity)
    return {
        "food_code": food["code"],
        "source": source,
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


def calculate_support_totals(support_foods: list[dict]) -> dict[str, float]:
    totals = {
        "calories": 0.0,
        "protein_grams": 0.0,
        "fat_grams": 0.0,
        "carb_grams": 0.0,
    }
    for support_food in support_foods:
        precise_values = build_precise_food_values(
            support_food["food"],
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
    support_foods: list[dict],
    candidate_indexes: dict[str, int],
    food_data_source: str,
    training_focus: bool,
    meal_slot: str,
) -> dict | None:
    all_codes = [
        role_foods["protein"]["code"],
        role_foods["carb"]["code"],
        role_foods["fat"]["code"],
        *[support_food["food"]["code"] for support_food in support_foods],
    ]
    if len(set(all_codes)) != len(all_codes):
        return None

    support_totals = calculate_support_totals(support_foods)
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
                    **build_food_portion(food, quantity, food_data_source),
                }
            )

    for support_food in support_foods:
        foods.append(
            {
                "role": support_food["role"],
                **build_food_portion(
                    support_food["food"],
                    float(support_food["quantity"]),
                    food_data_source,
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
        "score": build_solution_score(
            role_foods=role_foods,
            role_quantities=role_quantities,
            support_foods=support_foods,
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
    food_data_source: str,
) -> dict:
    candidate_codes = get_role_candidate_codes(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
    )
    support_options = get_support_options(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )
    meal_slot = get_meal_slot(meal_index, meals_count)

    best_solution: dict | None = None

    def evaluate_candidate_sets(role_codes: dict[str, list[str]], extra_support_options: list[list[dict]]) -> None:
        nonlocal best_solution

        for support_foods in extra_support_options:
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
                    support_foods=support_foods,
                    candidate_indexes=candidate_indexes,
                    food_data_source=food_data_source,
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
    food_lookup: dict[str, dict],
    food_data_source: str,
) -> dict:
    meal_fit = find_exact_solution_for_meal(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
        food_data_source=food_data_source,
    )

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
    food_lookup = get_food_lookup()
    generated_meals = [
        generate_food_based_meal(
            meal=DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=meal_distribution["training_optimization_applied"] and meal_index in focus_indexes,
            food_lookup=food_lookup,
            food_data_source=FOOD_DATA_SOURCE,
        )
        for meal_index, meal in enumerate(meal_distribution["meals"])
    ]
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
        "food_data_source": FOOD_DATA_SOURCE,
        "food_catalog_version": get_food_catalog_version(),
        "meals": generated_meals,
    }


def generate_daily_diet(
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    return generate_food_based_diet(
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
        "food_data_source": diet_payload.get("food_data_source", FOOD_DATA_SOURCE),
        "food_catalog_version": diet_payload.get("food_catalog_version"),
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
                        "source": food.get("source", FOOD_DATA_SOURCE),
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
