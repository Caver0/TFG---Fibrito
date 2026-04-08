"""Business logic for generating and retrieving daily diets."""
from decimal import ROUND_HALF_UP, Decimal
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietListItem, DietMeal, TrainingTimeOfDay, serialize_daily_diet, serialize_diet_list_item
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


def round_diet_value(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(DIET_PRECISION, rounding=ROUND_HALF_UP))


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

    protein_weights = blend_weight_sets(uniform_weights, calorie_weights, calorie_ratio=0.3)
    fat_weights = blend_weight_sets(uniform_weights, calorie_weights, calorie_ratio=0.2)
    carb_weights = blend_weight_sets(uniform_weights, calorie_weights, calorie_ratio=0.8)

    primary_index, secondary_index = focus_indexes
    if training_optimization_applied and primary_index >= 0:
        fat_weights = adjust_focus_weights(
            fat_weights,
            primary_index,
            secondary_index,
            primary_multiplier=0.82,
            secondary_multiplier=0.92,
        )
        carb_weights = adjust_focus_weights(
            carb_weights,
            primary_index,
            secondary_index,
            primary_multiplier=1.22,
            secondary_multiplier=1.12,
        )

    protein_distribution = distribute_total_by_weights(protein_grams, protein_weights)
    fat_distribution = distribute_total_by_weights(fat_grams, fat_weights)
    carb_distribution = distribute_total_by_weights(carb_grams, carb_weights)

    meals: list[DietMeal] = []
    for meal_index, meal in enumerate(base_meals):
        meals.append(
            DietMeal(
                meal_number=meal["meal_number"],
                distribution_percentage=meal["distribution_percentage"],
                target_calories=meal["target_calories"],
                target_protein_grams=protein_distribution[meal_index],
                target_fat_grams=fat_distribution[meal_index],
                target_carb_grams=carb_distribution[meal_index],
            )
        )

    return meals


def generate_daily_diet(
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
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

    return {
        "meals_count": meals_count,
        "target_calories": nutrition.target_calories,
        "protein_grams": nutrition.protein_grams,
        "fat_grams": nutrition.fat_grams,
        "carb_grams": nutrition.carb_grams,
        "distribution_percentages": distribution_percentages,
        "training_time_of_day": training_time_of_day,
        "training_optimization_applied": training_optimization_applied,
        "meals": [meal.model_dump() for meal in meals],
    }


def save_diet(database, user_id: str, diet_payload: dict) -> DailyDiet:
    diet_document = {
        "user_id": ObjectId(user_id),
        "created_at": datetime.now(UTC),
        "meals_count": diet_payload["meals_count"],
        "target_calories": round_diet_value(diet_payload["target_calories"]),
        "protein_grams": round_diet_value(diet_payload["protein_grams"]),
        "fat_grams": round_diet_value(diet_payload["fat_grams"]),
        "carb_grams": round_diet_value(diet_payload["carb_grams"]),
        "distribution_percentages": [
            round_diet_value(value) for value in diet_payload["distribution_percentages"]
        ],
        "training_time_of_day": diet_payload["training_time_of_day"],
        "training_optimization_applied": diet_payload["training_optimization_applied"],
        "meals": [
            {
                "meal_number": meal["meal_number"],
                "distribution_percentage": round_diet_value(meal["distribution_percentage"]),
                "target_calories": round_diet_value(meal["target_calories"]),
                "target_protein_grams": round_diet_value(meal["target_protein_grams"]),
                "target_fat_grams": round_diet_value(meal["target_fat_grams"]),
                "target_carb_grams": round_diet_value(meal["target_carb_grams"]),
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
