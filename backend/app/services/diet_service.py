"""Business logic for generating and retrieving food-based daily diets."""
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietListItem, DietMeal, TrainingTimeOfDay, serialize_daily_diet, serialize_diet_list_item
from app.schemas.user import UserPublic
from app.services.food_catalog_service import get_food_catalog_version, get_food_lookup
from app.services.nutrition_service import build_nutrition_summary

DIET_PRECISION = Decimal("0.1")
PERCENTAGE_TOTAL = Decimal("100.0")
PERCENTAGE_TOLERANCE = Decimal("0.5")
MIN_PERCENTAGE_AFTER_OPTIMIZATION = Decimal("1.0")
DEFAULT_DISTRIBUTION_TEMPLATES = {
    3: [30.0, 40.0, 30.0],
    4: [25.0, 15.0, 35.0, 25.0],
    5: [20.0, 10.0, 30.0, 15.0, 25.0],
    6: [20.0, 10.0, 25.0, 10.0, 15.0, 20.0],
}
TRAINING_TIME_POSITIONS = {
    "manana": 0.18,
    "mediodia": 0.45,
    "tarde": 0.7,
    "noche": 0.9,
}
LOW_CARB_THRESHOLD = 15.0
SIGNIFICANT_CARB_THRESHOLD = 20.0
SIGNIFICANT_FAT_THRESHOLD = 8.0
TRAINING_FAT_THRESHOLD = 14.0
PROTEIN_GAP_THRESHOLD = 4.0
CARB_GAP_THRESHOLD = 6.0
FAT_GAP_THRESHOLD = 2.5
CALORIE_GAP_THRESHOLD = 60.0


def round_diet_value(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(DIET_PRECISION, rounding=ROUND_HALF_UP))


def round_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value

    step_decimal = Decimal(str(step))
    units = (Decimal(str(value)) / step_decimal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(units * step_decimal)


def get_default_distribution_template(meals_count: int) -> list[float]:
    template = DEFAULT_DISTRIBUTION_TEMPLATES.get(meals_count)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meals count must be between 3 and 6",
        )

    return template.copy()


def normalize_weights(weights: list[float | Decimal]) -> list[float]:
    total = sum(Decimal(str(weight)) for weight in weights)
    if total <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Distribution weights must be greater than zero",
        )

    return [float(Decimal(str(weight)) / total) for weight in weights]


def distribute_total_by_weights(total: float, weights: list[float | Decimal]) -> list[float]:
    normalized_weights = normalize_weights(weights)
    remaining_total = Decimal(str(total))
    remaining_weights = [Decimal(str(weight)) for weight in normalized_weights]
    distribution: list[float] = []

    for index, weight in enumerate(remaining_weights):
        remaining_slots = len(remaining_weights) - index
        if remaining_slots == 1:
            portion = remaining_total
        else:
            remaining_weight_sum = sum(remaining_weights[index:])
            portion = (
                remaining_total * (weight / remaining_weight_sum)
            ).quantize(DIET_PRECISION, rounding=ROUND_HALF_UP)

        distribution.append(float(portion))
        remaining_total -= portion

    return distribution


def normalize_percentages(percentages: list[float]) -> list[float]:
    return distribute_total_by_weights(float(PERCENTAGE_TOTAL), percentages)


def validate_distribution_percentages(percentages: list[float], meals_count: int) -> list[float]:
    if len(percentages) != meals_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Custom percentages must match the selected meals count",
        )

    if any(Decimal(str(value)) <= 0 for value in percentages):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Each meal percentage must be greater than zero",
        )

    total = sum(Decimal(str(value)) for value in percentages)
    if abs(total - PERCENTAGE_TOTAL) > PERCENTAGE_TOLERANCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Custom percentages must add up to 100",
        )

    return normalize_percentages(percentages)


def get_training_focus_indexes(
    meals_count: int,
    training_time_of_day: TrainingTimeOfDay,
) -> tuple[int, int | None]:
    target_position = TRAINING_TIME_POSITIONS[training_time_of_day]
    meal_positions = [
        (index + 1) / (meals_count + 1)
        for index in range(meals_count)
    ]
    ordered_indexes = sorted(
        range(meals_count),
        key=lambda index: (abs(meal_positions[index] - target_position), index),
    )

    primary_index = ordered_indexes[0]
    secondary_index = ordered_indexes[1] if len(ordered_indexes) > 1 else None
    return primary_index, secondary_index


def optimize_distribution_for_training(
    percentages: list[float],
    training_time_of_day: TrainingTimeOfDay | None,
) -> tuple[list[float], bool, tuple[int, int | None]]:
    if not training_time_of_day:
        return percentages, False, (-1, None)

    primary_index, secondary_index = get_training_focus_indexes(
        len(percentages),
        training_time_of_day,
    )
    distribution = [Decimal(str(value)) for value in percentages]
    requested_boosts = [(primary_index, Decimal("4.0"))]
    if secondary_index is not None:
        requested_boosts.append((secondary_index, Decimal("2.0")))

    reduction_indexes = [
        index
        for index in range(len(distribution))
        if index not in {boost_index for boost_index, _ in requested_boosts}
    ]
    reduction_capacities = [
        max(distribution[index] - MIN_PERCENTAGE_AFTER_OPTIMIZATION, Decimal("0.0"))
        for index in reduction_indexes
    ]
    available_shift = sum(reduction_capacities)
    requested_shift = sum(boost for _, boost in requested_boosts)
    applied_shift = min(available_shift, requested_shift)

    if applied_shift <= 0:
        return percentages, False, (primary_index, secondary_index)

    boost_amounts = distribute_total_by_weights(
        float(applied_shift),
        [float(boost) for _, boost in requested_boosts],
    )
    reduction_amounts = distribute_total_by_weights(
        float(applied_shift),
        [float(capacity) for capacity in reduction_capacities],
    )

    for (boost_index, _), amount in zip(requested_boosts, boost_amounts):
        distribution[boost_index] += Decimal(str(amount))

    for reduction_index, amount in zip(reduction_indexes, reduction_amounts):
        distribution[reduction_index] -= Decimal(str(amount))

    normalized_distribution = normalize_percentages([float(value) for value in distribution])
    return normalized_distribution, True, (primary_index, secondary_index)


def build_base_meal_distribution(
    *,
    meals_count: int,
    target_calories: float,
    distribution_percentages: list[float],
) -> list[dict]:
    calorie_weights = [percentage / 100 for percentage in distribution_percentages]
    meal_calories = distribute_total_by_weights(target_calories, calorie_weights)

    return [
        {
            "meal_number": meal_index + 1,
            "distribution_percentage": distribution_percentages[meal_index],
            "target_calories": meal_calories[meal_index],
        }
        for meal_index in range(meals_count)
    ]


def blend_weight_sets(
    uniform_weights: list[float],
    calorie_weights: list[float],
    calorie_ratio: float,
) -> list[float]:
    return normalize_weights(
        [
            (uniform_weight * (1 - calorie_ratio)) + (calorie_weight * calorie_ratio)
            for uniform_weight, calorie_weight in zip(uniform_weights, calorie_weights, strict=True)
        ]
    )


def adjust_focus_weights(
    weights: list[float],
    primary_index: int,
    secondary_index: int | None,
    primary_multiplier: float,
    secondary_multiplier: float,
) -> list[float]:
    adjusted_weights = weights.copy()
    if primary_index >= 0:
        adjusted_weights[primary_index] *= primary_multiplier
    if secondary_index is not None:
        adjusted_weights[secondary_index] *= secondary_multiplier

    return normalize_weights(adjusted_weights)


def distribute_macros_across_meals(
    *,
    base_meals: list[dict],
    protein_grams: float,
    fat_grams: float,
    carb_grams: float,
    distribution_percentages: list[float],
    training_optimization_applied: bool,
    focus_indexes: tuple[int, int | None],
) -> list[DietMeal]:
    meals_count = len(base_meals)
    calorie_weights = normalize_weights(distribution_percentages)
    uniform_weights = [1 / meals_count] * meals_count

    protein_weights = blend_weight_sets(uniform_weights, calorie_weights, calorie_ratio=0.18)
    fat_weights = blend_weight_sets(uniform_weights, calorie_weights, calorie_ratio=0.35)

    primary_index, secondary_index = focus_indexes
    if training_optimization_applied and primary_index >= 0:
        fat_weights = adjust_focus_weights(
            fat_weights,
            primary_index,
            secondary_index,
            primary_multiplier=0.7,
            secondary_multiplier=0.88,
        )

    protein_distribution = distribute_total_by_weights(protein_grams, protein_weights)
    fat_distribution = distribute_total_by_weights(fat_grams, fat_weights)
    remaining_carb_grams = Decimal(str(carb_grams))
    meals: list[DietMeal] = []
    for meal_index, meal in enumerate(base_meals):
        protein_target = Decimal(str(protein_distribution[meal_index]))
        fat_target = Decimal(str(fat_distribution[meal_index]))
        remaining_slots = meals_count - meal_index
        if remaining_slots == 1:
            carb_target = max(remaining_carb_grams, Decimal("0.0"))
        else:
            carb_target = (
                (Decimal(str(meal["target_calories"])) - (protein_target * Decimal("4")) - (fat_target * Decimal("9")))
                / Decimal("4")
            ).quantize(DIET_PRECISION, rounding=ROUND_HALF_UP)
            carb_target = max(carb_target, Decimal("0.0"))

        remaining_carb_grams -= carb_target
        meals.append(
            DietMeal(
                meal_number=meal["meal_number"],
                distribution_percentage=meal["distribution_percentage"],
                target_calories=meal["target_calories"],
                target_protein_grams=float(protein_target),
                target_fat_grams=float(fat_target),
                target_carb_grams=float(carb_target),
                actual_calories=meal["target_calories"],
                actual_protein_grams=float(protein_target),
                actual_fat_grams=float(fat_target),
                actual_carb_grams=float(carb_target),
                foods=[],
            )
        )

    return meals


def build_structural_daily_diet(
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> tuple[dict, tuple[int, int | None]]:
    nutrition = build_nutrition_summary(
        user,
        target_calories_override=user.target_calories,
    )

    base_percentages = (
        validate_distribution_percentages(custom_percentages, meals_count)
        if custom_percentages is not None
        else get_default_distribution_template(meals_count)
    )
    distribution_percentages, training_optimization_applied, focus_indexes = (
        optimize_distribution_for_training(base_percentages, training_time_of_day)
    )
    base_meals = build_base_meal_distribution(
        meals_count=meals_count,
        target_calories=nutrition.target_calories,
        distribution_percentages=distribution_percentages,
    )
    meals = distribute_macros_across_meals(
        base_meals=base_meals,
        protein_grams=nutrition.protein_grams,
        fat_grams=nutrition.fat_grams,
        carb_grams=nutrition.carb_grams,
        distribution_percentages=distribution_percentages,
        training_optimization_applied=training_optimization_applied,
        focus_indexes=focus_indexes,
    )

    return (
        {
            "meals_count": meals_count,
            "target_calories": nutrition.target_calories,
            "protein_grams": nutrition.protein_grams,
            "fat_grams": nutrition.fat_grams,
            "carb_grams": nutrition.carb_grams,
            "distribution_percentages": distribution_percentages,
            "training_time_of_day": training_time_of_day,
            "training_optimization_applied": training_optimization_applied,
            "meals": [meal.model_dump() for meal in meals],
        },
        focus_indexes,
    )


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
    needs_carb_source = meal.target_carb_grams >= SIGNIFICANT_CARB_THRESHOLD
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
        carb_codes = (
            ["oats", "potato", "whole_wheat_bread"]
            if meal.target_carb_grams >= 55
            else ["whole_wheat_bread", "oats", "potato"]
        )
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
        carb_codes = (
            ["rice", "potato", "whole_wheat_bread"]
            if meal.target_carb_grams >= 65
            else ["potato", "rice", "whole_wheat_bread"]
        )
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
        if meal.target_carb_grams >= 80:
            carb_codes = ["rice", "pasta", "potato"]
        elif meal.target_carb_grams >= 45:
            carb_codes = ["rice", "potato", "pasta", "whole_wheat_bread"]
        else:
            carb_codes = ["whole_wheat_bread", "potato", "rice", "pasta"]
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

    should_add_fruit = meal.target_carb_grams >= 28 and (meal_slot == "early" or training_focus)
    if should_add_fruit:
        selected_foods.append({"role": "fruit", "food": food_lookup["banana"]})

    should_add_vegetables = meal_slot != "early" and meal.target_calories >= 300
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


def clamp_food_quantity(food: dict, quantity: float) -> float:
    bounded_quantity = min(
        max(quantity, float(food["min_quantity"])),
        float(food["max_quantity"]),
    )
    return round_to_step(bounded_quantity, float(food["step"]))


def build_food_portion(food: dict, quantity: float, source: str) -> dict:
    scale = Decimal(str(quantity)) / Decimal(str(food["reference_amount"]))
    grams = Decimal(str(food["grams_per_reference"])) * scale

    return {
        "food_code": food["code"],
        "source": source,
        "name": food["name"],
        "category": food["category"],
        "quantity": round_diet_value(quantity),
        "unit": food["reference_unit"],
        "grams": round_diet_value(float(grams)),
        "calories": round_diet_value(float(Decimal(str(food["calories"])) * scale)),
        "protein_grams": round_diet_value(float(Decimal(str(food["protein_grams"])) * scale)),
        "fat_grams": round_diet_value(float(Decimal(str(food["fat_grams"])) * scale)),
        "carb_grams": round_diet_value(float(Decimal(str(food["carb_grams"])) * scale)),
    }


def calculate_meal_totals_from_foods(foods: list[dict]) -> dict[str, float]:
    return {
        "actual_calories": round_diet_value(sum(food["calories"] for food in foods)),
        "actual_protein_grams": round_diet_value(sum(food["protein_grams"] for food in foods)),
        "actual_fat_grams": round_diet_value(sum(food["fat_grams"] for food in foods)),
        "actual_carb_grams": round_diet_value(sum(food["carb_grams"] for food in foods)),
    }


def get_support_quantity(role: str, meal: DietMeal, training_focus: bool) -> float:
    if role == "vegetable":
        return 150.0 if meal.target_calories >= 420 else 120.0
    if role == "fruit":
        if meal.target_carb_grams >= 140:
            return 2.0
        if meal.target_carb_grams >= 75:
            return 1.5
        if meal.target_carb_grams >= 35 or training_focus:
            return 1.0
        return 0.5
    if role == "dairy":
        return 250.0 if meal.target_calories >= 220 else 125.0

    raise ValueError(f"Unsupported support role: {role}")


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
        role = selection["role"]
        food = selection["food"]
        quantity = quantities.get(role)
        if quantity is None:
            continue

        foods.append(build_food_portion(food, quantity, source))

    return foods


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


def estimate_food_quantities_for_meal(
    *,
    meal: DietMeal,
    selected_foods: list[dict],
    training_focus: bool,
    food_data_source: str,
) -> list[dict]:
    quantities: dict[str, float] = {}

    for role in ("vegetable", "fruit", "dairy"):
        selection = find_selection_by_role(selected_foods, role)
        if selection:
            quantities[role] = clamp_food_quantity(
                selection["food"],
                get_support_quantity(role, meal, training_focus),
            )

    support_foods = build_foods_from_quantities(
        selected_foods=selected_foods,
        quantities=quantities,
        source=food_data_source,
    )
    support_totals = calculate_meal_totals_from_foods(support_foods)

    protein_selection = find_selection_by_role(selected_foods, "protein")
    if protein_selection:
        quantities["protein"] = estimate_quantity_for_macro(
            food=protein_selection["food"],
            target_value=meal.target_protein_grams,
            current_value=support_totals["actual_protein_grams"],
            metric_key="protein_grams",
            minimum_ratio=0.78,
        )

    foods_after_protein = build_foods_from_quantities(
        selected_foods=selected_foods,
        quantities=quantities,
        source=food_data_source,
    )
    totals_after_protein = calculate_meal_totals_from_foods(foods_after_protein)

    carb_selection = find_selection_by_role(selected_foods, "carb")
    if carb_selection:
        minimum_ratio = 0.58 if find_selection_by_role(selected_foods, "fruit") else 0.82
        quantities["carb"] = estimate_quantity_for_macro(
            food=carb_selection["food"],
            target_value=meal.target_carb_grams,
            current_value=totals_after_protein["actual_carb_grams"],
            metric_key="carb_grams",
            minimum_ratio=minimum_ratio,
        )

    foods_after_carb = build_foods_from_quantities(
        selected_foods=selected_foods,
        quantities=quantities,
        source=food_data_source,
    )
    totals_after_carb = calculate_meal_totals_from_foods(foods_after_carb)

    fat_selection = find_selection_by_role(selected_foods, "fat")
    if fat_selection:
        quantities["fat"] = estimate_quantity_for_macro(
            food=fat_selection["food"],
            target_value=meal.target_fat_grams,
            current_value=totals_after_carb["actual_fat_grams"],
            metric_key="fat_grams",
            minimum_ratio=0.72,
        )

    for _ in range(2):
        current_foods = build_foods_from_quantities(
            selected_foods=selected_foods,
            quantities=quantities,
            source=food_data_source,
        )
        totals = calculate_meal_totals_from_foods(current_foods)

        protein_gap = meal.target_protein_grams - totals["actual_protein_grams"]
        carb_gap = meal.target_carb_grams - totals["actual_carb_grams"]
        fat_gap = meal.target_fat_grams - totals["actual_fat_grams"]

        if abs(protein_gap) > PROTEIN_GAP_THRESHOLD and protein_selection:
            quantities["protein"] = adjust_quantity_by_gap(
                current_quantity=quantities["protein"],
                food=protein_selection["food"],
                metric_key="protein_grams",
                gap=protein_gap,
                damping=0.75,
            )

        if abs(carb_gap) > CARB_GAP_THRESHOLD and carb_selection:
            quantities["carb"] = adjust_quantity_by_gap(
                current_quantity=quantities["carb"],
                food=carb_selection["food"],
                metric_key="carb_grams",
                gap=carb_gap,
                damping=0.8,
            )

        if abs(fat_gap) > FAT_GAP_THRESHOLD and fat_selection:
            quantities["fat"] = adjust_quantity_by_gap(
                current_quantity=quantities["fat"],
                food=fat_selection["food"],
                metric_key="fat_grams",
                gap=fat_gap,
                damping=0.9,
            )

        current_foods = build_foods_from_quantities(
            selected_foods=selected_foods,
            quantities=quantities,
            source=food_data_source,
        )
        totals = calculate_meal_totals_from_foods(current_foods)
        calorie_gap = meal.target_calories - totals["actual_calories"]

        if abs(calorie_gap) <= CALORIE_GAP_THRESHOLD:
            continue

        if calorie_gap > 0:
            if carb_selection and meal.target_carb_grams >= totals["actual_carb_grams"]:
                quantities["carb"] = adjust_quantity_by_gap(
                    current_quantity=quantities["carb"],
                    food=carb_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.45,
                )
            elif protein_selection:
                quantities["protein"] = adjust_quantity_by_gap(
                    current_quantity=quantities["protein"],
                    food=protein_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.35,
                )
            elif fat_selection:
                quantities["fat"] = adjust_quantity_by_gap(
                    current_quantity=quantities["fat"],
                    food=fat_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.25,
                )
        else:
            if fat_selection:
                quantities["fat"] = adjust_quantity_by_gap(
                    current_quantity=quantities["fat"],
                    food=fat_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.3,
                )
            elif carb_selection:
                quantities["carb"] = adjust_quantity_by_gap(
                    current_quantity=quantities["carb"],
                    food=carb_selection["food"],
                    metric_key="calories",
                    gap=calorie_gap,
                    damping=0.35,
                )

    return build_foods_from_quantities(
        selected_foods=selected_foods,
        quantities=quantities,
        source=food_data_source,
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
    foods = estimate_food_quantities_for_meal(
        meal=meal,
        selected_foods=selected_foods,
        training_focus=training_focus,
        food_data_source=food_data_source,
    )
    meal_totals = calculate_meal_totals_from_foods(foods)

    return {
        "meal_number": meal.meal_number,
        "distribution_percentage": round_diet_value(meal.distribution_percentage or 0),
        "target_calories": round_diet_value(meal.target_calories),
        "target_protein_grams": round_diet_value(meal.target_protein_grams),
        "target_fat_grams": round_diet_value(meal.target_fat_grams),
        "target_carb_grams": round_diet_value(meal.target_carb_grams),
        "actual_calories": meal_totals["actual_calories"],
        "actual_protein_grams": meal_totals["actual_protein_grams"],
        "actual_fat_grams": meal_totals["actual_fat_grams"],
        "actual_carb_grams": meal_totals["actual_carb_grams"],
        "foods": foods,
    }


def calculate_daily_totals_from_meals(meals: list[dict]) -> dict[str, float]:
    return {
        "actual_calories": round_diet_value(sum(meal["actual_calories"] for meal in meals)),
        "actual_protein_grams": round_diet_value(sum(meal["actual_protein_grams"] for meal in meals)),
        "actual_fat_grams": round_diet_value(sum(meal["actual_fat_grams"] for meal in meals)),
        "actual_carb_grams": round_diet_value(sum(meal["actual_carb_grams"] for meal in meals)),
    }


def generate_food_based_diet(
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    structural_diet, focus_indexes = build_structural_daily_diet(
        user=user,
        meals_count=meals_count,
        custom_percentages=custom_percentages,
        training_time_of_day=training_time_of_day,
    )
    food_lookup = get_food_lookup()
    food_data_source = "internal_catalog"
    generated_meals = [
        generate_food_based_meal(
            meal=DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=structural_diet["training_optimization_applied"] and meal_index in focus_indexes,
            food_lookup=food_lookup,
            food_data_source=food_data_source,
        )
        for meal_index, meal in enumerate(structural_diet["meals"])
    ]
    diet_totals = calculate_daily_totals_from_meals(generated_meals)

    return {
        "meals_count": structural_diet["meals_count"],
        "target_calories": structural_diet["target_calories"],
        "protein_grams": structural_diet["protein_grams"],
        "fat_grams": structural_diet["fat_grams"],
        "carb_grams": structural_diet["carb_grams"],
        "actual_calories": diet_totals["actual_calories"],
        "actual_protein_grams": diet_totals["actual_protein_grams"],
        "actual_fat_grams": diet_totals["actual_fat_grams"],
        "actual_carb_grams": diet_totals["actual_carb_grams"],
        "distribution_percentages": structural_diet["distribution_percentages"],
        "training_time_of_day": structural_diet["training_time_of_day"],
        "training_optimization_applied": structural_diet["training_optimization_applied"],
        "food_data_source": food_data_source,
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
        "distribution_percentages": [
            round_diet_value(value) for value in diet_payload["distribution_percentages"]
        ],
        "training_time_of_day": diet_payload["training_time_of_day"],
        "training_optimization_applied": diet_payload["training_optimization_applied"],
        "food_data_source": diet_payload.get("food_data_source", "internal_catalog"),
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
                "foods": [
                    {
                        "food_code": food.get("food_code"),
                        "source": food.get("source", "internal_catalog"),
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
