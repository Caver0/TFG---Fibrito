"""Meal-level target distribution separated from food generation."""
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status

from app.schemas.diet import DietMeal, TrainingTimeOfDay
from app.schemas.user import UserPublic
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


def calculate_macro_calories(protein_grams: float, fat_grams: float, carb_grams: float) -> float:
    return (protein_grams * 4.0) + (fat_grams * 9.0) + (carb_grams * 4.0)


def round_distribution_value(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(DIET_PRECISION, rounding=ROUND_HALF_UP))


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


def get_default_distribution_template(meals_count: int) -> list[float]:
    template = DEFAULT_DISTRIBUTION_TEMPLATES.get(meals_count)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meals count must be between 3 and 6",
        )

    return template.copy()


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
        rounded_protein_target = round_distribution_value(float(protein_target))
        rounded_fat_target = round_distribution_value(float(fat_target))
        rounded_carb_target = round_distribution_value(float(carb_target))
        rounded_target_calories = round_distribution_value(
            calculate_macro_calories(
                rounded_protein_target,
                rounded_fat_target,
                rounded_carb_target,
            )
        )
        meals.append(
            DietMeal(
                meal_number=meal["meal_number"],
                distribution_percentage=meal["distribution_percentage"],
                target_calories=rounded_target_calories,
                target_protein_grams=rounded_protein_target,
                target_fat_grams=rounded_fat_target,
                target_carb_grams=rounded_carb_target,
                actual_calories=rounded_target_calories,
                actual_protein_grams=rounded_protein_target,
                actual_fat_grams=rounded_fat_target,
                actual_carb_grams=rounded_carb_target,
                calorie_difference=0.0,
                protein_difference=0.0,
                fat_difference=0.0,
                carb_difference=0.0,
                foods=[],
            )
        )

    return meals


def generate_meal_distribution_targets(
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
    target_calories = round_distribution_value(sum(meal.target_calories for meal in meals))
    target_protein_grams = round_distribution_value(sum(meal.target_protein_grams for meal in meals))
    target_fat_grams = round_distribution_value(sum(meal.target_fat_grams for meal in meals))
    target_carb_grams = round_distribution_value(sum(meal.target_carb_grams for meal in meals))

    return (
        {
            "meals_count": meals_count,
            "target_calories": target_calories,
            "protein_grams": target_protein_grams,
            "fat_grams": target_fat_grams,
            "carb_grams": target_carb_grams,
            "actual_calories": target_calories,
            "actual_protein_grams": target_protein_grams,
            "actual_fat_grams": target_fat_grams,
            "actual_carb_grams": target_carb_grams,
            "calorie_difference": 0.0,
            "protein_difference": 0.0,
            "fat_difference": 0.0,
            "carb_difference": 0.0,
            "distribution_percentages": distribution_percentages,
            "training_time_of_day": training_time_of_day,
            "training_optimization_applied": training_optimization_applied,
            "meals": [meal.model_dump() for meal in meals],
        },
        focus_indexes,
    )
