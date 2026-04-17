"""Helpers to derive stable meal semantics from distribution context."""
from typing import Literal

MealSlot = Literal["early", "main", "late"]
MealRole = Literal["meal", "breakfast", "pre_workout", "post_workout", "dinner", "training_focus"]

TRAINING_TIME_POSITIONS = {
    "manana": 0.18,
    "mediodia": 0.45,
    "tarde": 0.7,
    "noche": 0.9,
}

MEAL_ROLE_LABELS: dict[MealRole, str] = {
    "meal": "Comida",
    "breakfast": "Desayuno",
    "pre_workout": "Pre-entrenamiento",
    "post_workout": "Post-entrenamiento",
    "dinner": "Cena",
    "training_focus": "Comida de entreno",
}


def get_meal_slot(meal_index: int, meals_count: int) -> MealSlot:
    if meal_index == 0 or (meals_count >= 5 and meal_index == 1):
        return "early"
    if meal_index == meals_count - 1:
        return "late"
    return "main"


def get_meal_positions(meals_count: int) -> list[float]:
    return [
        (index + 1) / (meals_count + 1)
        for index in range(meals_count)
    ]


def get_training_focus_indexes(
    meals_count: int,
    training_time_of_day: str,
) -> tuple[int, int | None]:
    target_position = TRAINING_TIME_POSITIONS[training_time_of_day]
    meal_positions = get_meal_positions(meals_count)
    ordered_indexes = sorted(
        range(meals_count),
        key=lambda index: (abs(meal_positions[index] - target_position), index),
    )

    primary_index = ordered_indexes[0]
    secondary_index = ordered_indexes[1] if len(ordered_indexes) > 1 else None
    return primary_index, secondary_index


def get_training_neighbor_indexes(
    meals_count: int,
    training_time_of_day: str | None,
) -> tuple[int | None, int | None]:
    if not training_time_of_day or training_time_of_day not in TRAINING_TIME_POSITIONS:
        return None, None

    target_position = TRAINING_TIME_POSITIONS[training_time_of_day]
    meal_positions = get_meal_positions(meals_count)
    pre_workout_candidates = [
        index
        for index, position in enumerate(meal_positions)
        if position <= target_position
    ]
    post_workout_candidates = [
        index
        for index, position in enumerate(meal_positions)
        if position > target_position
    ]

    pre_workout_index = pre_workout_candidates[-1] if pre_workout_candidates else None
    post_workout_index = post_workout_candidates[0] if post_workout_candidates else None
    return pre_workout_index, post_workout_index


def resolve_meal_role(
    meal_index: int,
    meals_count: int,
    *,
    training_time_of_day: str | None = None,
    training_optimization_applied: bool = False,
) -> MealRole:
    if training_optimization_applied:
        pre_workout_index, post_workout_index = get_training_neighbor_indexes(
            meals_count,
            training_time_of_day,
        )
        focus_indexes = {
            index
            for index in get_training_focus_indexes(meals_count, training_time_of_day)
            if index is not None
        } if training_time_of_day in TRAINING_TIME_POSITIONS else set()

        if pre_workout_index is not None and meal_index == pre_workout_index:
            return "pre_workout"
        if post_workout_index is not None and meal_index == post_workout_index:
            return "post_workout"
        if meal_index in focus_indexes:
            return "training_focus"

    if meal_index == 0:
        return "breakfast"
    if meal_index == meals_count - 1:
        return "dinner"
    return "meal"


def format_meal_role_label(role: str | None) -> str:
    if not role:
        return MEAL_ROLE_LABELS["meal"]

    return MEAL_ROLE_LABELS.get(role, MEAL_ROLE_LABELS["meal"])
