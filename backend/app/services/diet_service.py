"""Food-based diet generation and persistence."""
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietListItem, DietMeal, TrainingTimeOfDay, serialize_daily_diet, serialize_diet_list_item
from app.schemas.user import UserPublic
from app.services.food_catalog_service import get_food_catalog_version, get_food_lookup
from app.services.meal_distribution_service import generate_meal_distribution_targets, round_distribution_value

LOW_CARB_THRESHOLD = 15.0
SIGNIFICANT_CARB_THRESHOLD = 16.0
SIGNIFICANT_FAT_THRESHOLD = 7.0
TRAINING_FAT_THRESHOLD = 7.0
PROTEIN_GAP_THRESHOLD = 4.0
CARB_GAP_THRESHOLD = 6.0
FAT_GAP_THRESHOLD = 2.5
CALORIE_GAP_THRESHOLD = 45.0
FOOD_DATA_SOURCE = "internal_catalog"
FIT_SCORE_TOLERANCES = {
    "calories": 20.0,
    "protein": 3.0,
    "fat": 2.5,
    "carbs": 4.0,
}
PRIMARY_PASS_WEIGHTS = {
    "protein": {"calories": 0.6, "fat": 0.9, "carbs": 0.8},
    "carbs": {"calories": 0.7, "protein": 0.7, "fat": 0.9},
    "fat": {"calories": 0.6, "protein": 0.7, "carbs": 0.7},
    "calories": {"protein": 1.2, "fat": 1.1, "carbs": 1.0},
}
ROLE_PRIORITIES = {
    "protein": ("protein", "dairy", "carb", "fat", "fruit", "vegetable"),
    "carbs": ("carb", "fruit", "dairy", "vegetable", "fat", "protein"),
    "fat": ("fat", "protein", "carb", "dairy", "fruit", "vegetable"),
    "calories": ("carb", "fat", "protein", "fruit", "dairy", "vegetable"),
}
GENERAL_ROLE_PRIORITY = ("protein", "carb", "fat", "fruit", "dairy", "vegetable")


def round_diet_value(value: float) -> float:
    return round_distribution_value(value)


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


def pick_rotating_food(food_lookup: dict[str, dict], codes: list[str], rotation_seed: int) -> dict:
    available_codes = [code for code in codes if code in food_lookup]
    if not available_codes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Food catalog is missing required items",
        )

    selected_code = available_codes[rotation_seed % len(available_codes)]
    return food_lookup[selected_code]


def select_foods_for_meal(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict],
) -> list[dict]:
    meal_slot = get_meal_slot(meal_index, meals_count)
    needs_carb_source = meal.target_carb_grams >= SIGNIFICANT_CARB_THRESHOLD or (
        meal.target_carb_grams >= 10 and meal.target_calories >= 200
    )
    needs_fat_source = meal.target_fat_grams >= (
        TRAINING_FAT_THRESHOLD if training_focus else SIGNIFICANT_FAT_THRESHOLD
    )
    rotation_seed = meal_index + meals_count

    if meal_slot == "early":
        if training_focus or meal.target_fat_grams <= 10:
            protein_codes = ["egg_whites", "greek_yogurt", "turkey_breast"]
        elif meal.target_carb_grams <= LOW_CARB_THRESHOLD:
            protein_codes = ["eggs", "tuna", "turkey_breast"]
        else:
            protein_codes = ["greek_yogurt", "eggs", "egg_whites", "turkey_breast"]
        if meal.target_carb_grams >= 75:
            carb_codes = ["oats", "potato", "whole_wheat_bread"]
        elif meal.target_carb_grams >= 25:
            carb_codes = ["whole_wheat_bread", "oats", "potato"]
        else:
            carb_codes = ["potato", "whole_wheat_bread"]
        fat_codes = (
            ["olive_oil", "mixed_nuts", "avocado"]
            if meal.target_fat_grams <= 10 or meal.target_calories <= 320
            else ["mixed_nuts", "avocado", "olive_oil"]
        )
    elif meal_slot == "late":
        if training_focus or meal.target_fat_grams <= 10:
            protein_codes = ["turkey_breast", "tuna", "chicken_breast"]
        elif meal.target_carb_grams <= LOW_CARB_THRESHOLD:
            protein_codes = ["tuna", "eggs", "turkey_breast"]
        else:
            protein_codes = ["turkey_breast", "tuna", "chicken_breast", "eggs"]
        if meal.target_carb_grams >= 110:
            carb_codes = ["rice", "pasta"]
        elif meal.target_carb_grams >= 65:
            carb_codes = ["rice", "potato", "whole_wheat_bread"]
        elif meal.target_carb_grams >= 20:
            carb_codes = ["potato", "whole_wheat_bread", "rice"]
        else:
            carb_codes = ["potato", "whole_wheat_bread"]
        fat_codes = (
            ["olive_oil", "avocado", "mixed_nuts"]
            if meal.target_fat_grams <= 10 or meal.target_calories <= 360
            else ["avocado", "olive_oil", "mixed_nuts"]
        )
    else:
        if training_focus or meal.target_fat_grams <= 10:
            protein_codes = ["chicken_breast", "turkey_breast", "tuna"]
        elif meal.target_carb_grams <= LOW_CARB_THRESHOLD:
            protein_codes = ["tuna", "eggs", "chicken_breast"]
        else:
            protein_codes = ["chicken_breast", "turkey_breast", "eggs", "tuna"]
        if meal.target_carb_grams >= 140:
            carb_codes = ["rice", "pasta"]
        elif meal.target_carb_grams >= 80:
            carb_codes = ["rice", "pasta", "potato"]
        elif meal.target_carb_grams >= 45:
            carb_codes = ["rice", "potato", "pasta", "whole_wheat_bread"]
        elif meal.target_carb_grams >= 20:
            carb_codes = ["whole_wheat_bread", "potato", "rice", "pasta"]
        else:
            carb_codes = ["potato", "whole_wheat_bread"]
        fat_codes = (
            ["olive_oil", "avocado", "mixed_nuts"]
            if meal.target_fat_grams <= 10 or meal.target_calories <= 360
            else ["avocado", "olive_oil", "mixed_nuts"]
        )

    selected_foods = [
        {
            "role": "protein",
            "food": pick_rotating_food(food_lookup, protein_codes, rotation_seed),
        }
    ]

    if needs_carb_source:
        selected_foods.append(
            {
                "role": "carb",
                "food": pick_rotating_food(food_lookup, carb_codes, rotation_seed + 1),
            }
        )

    should_add_fruit = meal.target_carb_grams >= 24 and (
        training_focus or (meal_slot == "early" and meal.target_carb_grams >= 32)
    )
    if should_add_fruit:
        selected_foods.append({"role": "fruit", "food": food_lookup["banana"]})

    should_add_vegetables = meal_slot != "early" and meal.target_calories >= 280
    if should_add_vegetables:
        selected_foods.append({"role": "vegetable", "food": food_lookup["mixed_vegetables"]})

    should_add_dairy = (
        meal_slot == "early"
        and meal.target_calories <= 260
        and meal.target_protein_grams <= 24
        and meal.target_carb_grams >= 14
        and selected_foods[0]["food"]["code"] != "greek_yogurt"
    )
    if should_add_dairy:
        selected_foods.append({"role": "dairy", "food": food_lookup["semi_skimmed_milk"]})

    if needs_fat_source:
        selected_foods.append(
            {
                "role": "fat",
                "food": pick_rotating_food(food_lookup, fat_codes, rotation_seed + 2),
            }
        )

    return selected_foods


def round_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value

    rounded_steps = round(value / step)
    return round_diet_value(rounded_steps * step)


def clamp_food_quantity(food: dict, quantity: float) -> float:
    bounded_quantity = min(
        max(quantity, float(food["min_quantity"])),
        float(food["max_quantity"]),
    )
    return round_to_step(bounded_quantity, float(food["step"]))


def build_food_portion(food: dict, quantity: float, source: str) -> dict:
    scale = quantity / float(food["reference_amount"])
    grams = float(food["grams_per_reference"]) * scale

    return {
        "food_code": food["code"],
        "source": source,
        "name": food["name"],
        "category": food["category"],
        "quantity": round_diet_value(quantity),
        "unit": food["reference_unit"],
        "grams": round_diet_value(grams),
        "calories": round_diet_value(float(food["calories"]) * scale),
        "protein_grams": round_diet_value(float(food["protein_grams"]) * scale),
        "fat_grams": round_diet_value(float(food["fat_grams"]) * scale),
        "carb_grams": round_diet_value(float(food["carb_grams"]) * scale),
    }


def find_selection_by_role(selected_foods: list[dict], role: str) -> dict | None:
    for selection in selected_foods:
        if selection["role"] == role:
            return selection
    return None


def build_foods_from_quantities(
    *,
    selected_foods: list[dict],
    quantities: dict[str, float],
    source: str,
) -> list[dict]:
    foods: list[dict] = []
    for selection in selected_foods:
        quantity = quantities.get(selection["role"])
        if quantity is None:
            continue

        foods.append(build_food_portion(selection["food"], quantity, source))

    return foods


def calculate_meal_totals_from_foods(foods: list[dict]) -> dict[str, float]:
    return {
        "actual_calories": round_diet_value(sum(food["calories"] for food in foods)),
        "actual_protein_grams": round_diet_value(sum(food["protein_grams"] for food in foods)),
        "actual_fat_grams": round_diet_value(sum(food["fat_grams"] for food in foods)),
        "actual_carb_grams": round_diet_value(sum(food["carb_grams"] for food in foods)),
    }


def summarize_meal_fit(
    *,
    meal: DietMeal,
    selected_foods: list[dict],
    quantities: dict[str, float],
    food_data_source: str,
) -> dict:
    foods = build_foods_from_quantities(
        selected_foods=selected_foods,
        quantities=quantities,
        source=food_data_source,
    )
    actuals = calculate_meal_totals_from_foods(foods)
    differences = calculate_difference_summary(
        target_calories=meal.target_calories,
        target_protein_grams=meal.target_protein_grams,
        target_fat_grams=meal.target_fat_grams,
        target_carb_grams=meal.target_carb_grams,
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
    )
    return {
        "foods": foods,
        **actuals,
        **differences,
    }


def get_support_quantity(
    role: str,
    meal: DietMeal,
    training_focus: bool,
    selected_foods: list[dict],
) -> float:
    if role == "vegetable":
        return 150.0 if meal.target_calories >= 420 else 120.0
    if role == "fruit":
        has_primary_carb = find_selection_by_role(selected_foods, "carb") is not None
        if meal.target_carb_grams >= 80:
            return 1.0 if has_primary_carb else 1.5
        if meal.target_carb_grams >= 45:
            return 0.5 if has_primary_carb else 1.0
        if meal.target_carb_grams >= 24 or training_focus:
            return 0.5
        return 0.5
    if role == "dairy":
        if meal.target_calories >= 280:
            return 250.0
        return 125.0

    raise ValueError(f"Unsupported support role: {role}")


def estimate_quantity_for_macro(
    *,
    food: dict,
    target_value: float,
    current_value: float,
    metric_key: str,
    minimum_ratio: float,
) -> float:
    metric_density = float(food[metric_key]) / float(food["reference_amount"])
    if metric_density <= 0:
        return clamp_food_quantity(food, float(food["default_quantity"]))

    desired_value = max(target_value - current_value, target_value * minimum_ratio)
    estimated_quantity = desired_value / metric_density
    return clamp_food_quantity(food, estimated_quantity)


def adjust_quantity_by_gap(
    *,
    current_quantity: float,
    food: dict,
    metric_key: str,
    gap: float,
    damping: float,
) -> float:
    metric_density = float(food[metric_key]) / float(food["reference_amount"])
    if metric_density <= 0:
        return current_quantity

    adjusted_quantity = current_quantity + ((gap / metric_density) * damping)
    return clamp_food_quantity(food, adjusted_quantity)


def get_normalized_fit_errors(summary: dict) -> dict[str, float]:
    return {
        "calories": abs(summary["calorie_difference"]) / FIT_SCORE_TOLERANCES["calories"],
        "protein": abs(summary["protein_difference"]) / FIT_SCORE_TOLERANCES["protein"],
        "fat": abs(summary["fat_difference"]) / FIT_SCORE_TOLERANCES["fat"],
        "carbs": abs(summary["carb_difference"]) / FIT_SCORE_TOLERANCES["carbs"],
    }


def build_primary_metric_score(summary: dict, primary_metric: str) -> float:
    normalized_errors = get_normalized_fit_errors(summary)
    secondary_score = sum(
        normalized_errors[metric_name] * weight
        for metric_name, weight in PRIMARY_PASS_WEIGHTS[primary_metric].items()
    )
    return round((normalized_errors[primary_metric] * 8) + secondary_score, 6)


def build_general_fit_score(summary: dict) -> float:
    normalized_errors = get_normalized_fit_errors(summary)
    return round(
        (
            normalized_errors["calories"] * 0.9
            + normalized_errors["protein"] * 1.0
            + normalized_errors["fat"] * 1.0
            + normalized_errors["carbs"] * 1.0
        ),
        6,
    )


def get_adjustable_roles(selected_foods: list[dict], quantities: dict[str, float], role_priority: tuple[str, ...]) -> list[str]:
    return [
        role
        for role in role_priority
        if find_selection_by_role(selected_foods, role) and role in quantities
    ]


def find_best_quantity_adjustment(
    *,
    meal: DietMeal,
    selected_foods: list[dict],
    quantities: dict[str, float],
    food_data_source: str,
    score_builder,
    role_priority: tuple[str, ...],
) -> dict | None:
    adjustable_roles = get_adjustable_roles(selected_foods, quantities, role_priority)
    if not adjustable_roles:
        return None

    best_candidate: dict | None = None

    for role_index, role in enumerate(adjustable_roles):
        selection = find_selection_by_role(selected_foods, role)
        if not selection:
            continue

        food = selection["food"]
        current_quantity = quantities[role]
        step = float(food["step"])

        for direction in (-1, 1):
            candidate_quantity = clamp_food_quantity(
                food,
                current_quantity + (step * direction),
            )
            if candidate_quantity == current_quantity:
                continue

            candidate_quantities = quantities.copy()
            candidate_quantities[role] = candidate_quantity
            candidate_summary = summarize_meal_fit(
                meal=meal,
                selected_foods=selected_foods,
                quantities=candidate_quantities,
                food_data_source=food_data_source,
            )
            candidate_score = score_builder(candidate_summary)

            if (
                best_candidate is None
                or candidate_score < best_candidate["score"] - 1e-6
                or (
                    abs(candidate_score - best_candidate["score"]) <= 1e-6
                    and role_index < best_candidate["role_index"]
                )
            ):
                best_candidate = {
                    "quantities": candidate_quantities,
                    "summary": candidate_summary,
                    "score": candidate_score,
                    "role_index": role_index,
                }

    return best_candidate


def run_adjustment_pass(
    *,
    meal: DietMeal,
    selected_foods: list[dict],
    quantities: dict[str, float],
    food_data_source: str,
    score_builder,
    role_priority: tuple[str, ...],
    iterations: int,
) -> tuple[dict[str, float], dict]:
    current_quantities = quantities.copy()
    current_summary = summarize_meal_fit(
        meal=meal,
        selected_foods=selected_foods,
        quantities=current_quantities,
        food_data_source=food_data_source,
    )
    current_score = score_builder(current_summary)

    for _ in range(iterations):
        candidate = find_best_quantity_adjustment(
            meal=meal,
            selected_foods=selected_foods,
            quantities=current_quantities,
            food_data_source=food_data_source,
            score_builder=score_builder,
            role_priority=role_priority,
        )
        if not candidate or candidate["score"] >= current_score - 1e-6:
            break

        current_quantities = candidate["quantities"]
        current_summary = candidate["summary"]
        current_score = candidate["score"]

    return current_quantities, current_summary


def fine_tune_quantities_for_meal(
    *,
    meal: DietMeal,
    selected_foods: list[dict],
    quantities: dict[str, float],
    food_data_source: str,
) -> dict[str, float]:
    adjusted_quantities = quantities.copy()

    for _ in range(2):
        for primary_metric in ("protein", "carbs", "fat", "calories"):
            adjusted_quantities, _ = run_adjustment_pass(
                meal=meal,
                selected_foods=selected_foods,
                quantities=adjusted_quantities,
                food_data_source=food_data_source,
                score_builder=lambda summary, metric=primary_metric: build_primary_metric_score(summary, metric),
                role_priority=ROLE_PRIORITIES[primary_metric],
                iterations=12,
            )

    adjusted_quantities, _ = run_adjustment_pass(
        meal=meal,
        selected_foods=selected_foods,
        quantities=adjusted_quantities,
        food_data_source=food_data_source,
        score_builder=build_general_fit_score,
        role_priority=GENERAL_ROLE_PRIORITY,
        iterations=16,
    )

    adjusted_quantities, _ = run_adjustment_pass(
        meal=meal,
        selected_foods=selected_foods,
        quantities=adjusted_quantities,
        food_data_source=food_data_source,
        score_builder=lambda summary: build_primary_metric_score(summary, "calories"),
        role_priority=ROLE_PRIORITIES["calories"],
        iterations=8,
    )

    return adjusted_quantities


def estimate_food_quantities_for_meal(
    *,
    meal: DietMeal,
    selected_foods: list[dict],
    training_focus: bool,
    food_data_source: str,
) -> dict:
    quantities: dict[str, float] = {}

    for role in ("vegetable", "fruit", "dairy"):
        selection = find_selection_by_role(selected_foods, role)
        if selection:
            quantities[role] = clamp_food_quantity(
                selection["food"],
                get_support_quantity(role, meal, training_focus, selected_foods),
            )

    support_summary = summarize_meal_fit(
        meal=meal,
        selected_foods=selected_foods,
        quantities=quantities,
        food_data_source=food_data_source,
    )

    protein_selection = find_selection_by_role(selected_foods, "protein")
    if protein_selection:
        quantities["protein"] = estimate_quantity_for_macro(
            food=protein_selection["food"],
            target_value=meal.target_protein_grams,
            current_value=support_summary["actual_protein_grams"],
            metric_key="protein_grams",
            minimum_ratio=0.76,
        )

    after_protein_summary = summarize_meal_fit(
        meal=meal,
        selected_foods=selected_foods,
        quantities=quantities,
        food_data_source=food_data_source,
    )

    carb_selection = find_selection_by_role(selected_foods, "carb")
    if carb_selection:
        minimum_ratio = 0.58 if find_selection_by_role(selected_foods, "fruit") else 0.82
        quantities["carb"] = estimate_quantity_for_macro(
            food=carb_selection["food"],
            target_value=meal.target_carb_grams,
            current_value=after_protein_summary["actual_carb_grams"],
            metric_key="carb_grams",
            minimum_ratio=minimum_ratio,
        )

    after_carb_summary = summarize_meal_fit(
        meal=meal,
        selected_foods=selected_foods,
        quantities=quantities,
        food_data_source=food_data_source,
    )

    fat_selection = find_selection_by_role(selected_foods, "fat")
    if fat_selection:
        quantities["fat"] = estimate_quantity_for_macro(
            food=fat_selection["food"],
            target_value=meal.target_fat_grams,
            current_value=after_carb_summary["actual_fat_grams"],
            metric_key="fat_grams",
            minimum_ratio=0.72,
        )

    for _ in range(2):
        current_summary = summarize_meal_fit(
            meal=meal,
            selected_foods=selected_foods,
            quantities=quantities,
            food_data_source=food_data_source,
        )

        protein_gap = meal.target_protein_grams - current_summary["actual_protein_grams"]
        carb_gap = meal.target_carb_grams - current_summary["actual_carb_grams"]
        fat_gap = meal.target_fat_grams - current_summary["actual_fat_grams"]

        if abs(protein_gap) > PROTEIN_GAP_THRESHOLD and protein_selection:
            quantities["protein"] = adjust_quantity_by_gap(
                current_quantity=quantities["protein"],
                food=protein_selection["food"],
                metric_key="protein_grams",
                gap=protein_gap,
                damping=0.72,
            )

        if abs(carb_gap) > CARB_GAP_THRESHOLD and carb_selection:
            quantities["carb"] = adjust_quantity_by_gap(
                current_quantity=quantities["carb"],
                food=carb_selection["food"],
                metric_key="carb_grams",
                gap=carb_gap,
                damping=0.78,
            )

        if abs(fat_gap) > FAT_GAP_THRESHOLD and fat_selection:
            quantities["fat"] = adjust_quantity_by_gap(
                current_quantity=quantities["fat"],
                food=fat_selection["food"],
                metric_key="fat_grams",
                gap=fat_gap,
                damping=0.86,
            )

        refreshed_summary = summarize_meal_fit(
            meal=meal,
            selected_foods=selected_foods,
            quantities=quantities,
            food_data_source=food_data_source,
        )
        calorie_gap = meal.target_calories - refreshed_summary["actual_calories"]

        if abs(calorie_gap) <= CALORIE_GAP_THRESHOLD:
            continue

        if calorie_gap > 0:
            if carb_selection and meal.target_carb_grams >= refreshed_summary["actual_carb_grams"]:
                quantities["carb"] = adjust_quantity_by_gap(
                    current_quantity=quantities["carb"],
                    food=carb_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.4,
                )
            elif protein_selection:
                quantities["protein"] = adjust_quantity_by_gap(
                    current_quantity=quantities["protein"],
                    food=protein_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.3,
                )
            elif fat_selection:
                quantities["fat"] = adjust_quantity_by_gap(
                    current_quantity=quantities["fat"],
                    food=fat_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.22,
                )
        else:
            if fat_selection:
                quantities["fat"] = adjust_quantity_by_gap(
                    current_quantity=quantities["fat"],
                    food=fat_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.28,
                )
            elif carb_selection:
                quantities["carb"] = adjust_quantity_by_gap(
                    current_quantity=quantities["carb"],
                    food=carb_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.32,
                )

    quantities = fine_tune_quantities_for_meal(
        meal=meal,
        selected_foods=selected_foods,
        quantities=quantities,
        food_data_source=food_data_source,
    )

    return summarize_meal_fit(
        meal=meal,
        selected_foods=selected_foods,
        quantities=quantities,
        food_data_source=food_data_source,
    )


def generate_food_based_meal(
    *,
    meal: DietMeal,
    meal_index: int,
    meals_count: int,
    training_focus: bool,
    food_lookup: dict[str, dict],
    food_data_source: str,
) -> dict:
    selected_foods = select_foods_for_meal(
        meal=meal,
        meal_index=meal_index,
        meals_count=meals_count,
        training_focus=training_focus,
        food_lookup=food_lookup,
    )
    meal_fit = estimate_food_quantities_for_meal(
        meal=meal,
        selected_foods=selected_foods,
        training_focus=training_focus,
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
                        "quantity": round_diet_value(food["quantity"]),
                        "unit": food["unit"],
                        "grams": round_diet_value(food["grams"]),
                        "calories": round_diet_value(food["calories"]),
                        "protein_grams": round_diet_value(food["protein_grams"]),
                        "fat_grams": round_diet_value(food["fat_grams"]),
                        "carb_grams": round_diet_value(food["carb_grams"]),
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
