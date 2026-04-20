"""Regression tests for carb distribution across meals."""

from app.services.meal_distribution_service import distribute_macros_across_meals


def _base_meals(*, meals_count: int, target_calories: float = 400.0) -> list[dict]:
    return [
        {
            "meal_number": meal_index + 1,
            "distribution_percentage": round(100 / meals_count, 2),
            "target_calories": target_calories,
        }
        for meal_index in range(meals_count)
    ]


def test_carb_distribution_without_training_stays_balanced():
    meals = distribute_macros_across_meals(
        base_meals=_base_meals(meals_count=4),
        protein_grams=0.0,
        fat_grams=0.0,
        carb_grams=100.0,
        distribution_percentages=[25.0, 25.0, 25.0, 25.0],
        training_optimization_applied=False,
        focus_indexes=(-1, None),
        training_time_of_day=None,
    )

    assert [meal.target_carb_grams for meal in meals] == [25.0, 25.0, 25.0, 25.0]


def test_carb_distribution_preserves_a_minimum_in_every_meal_before_prioritizing_pre_workout():
    meals = distribute_macros_across_meals(
        base_meals=_base_meals(meals_count=4),
        protein_grams=0.0,
        fat_grams=0.0,
        carb_grams=100.0,
        distribution_percentages=[25.0, 25.0, 25.0, 25.0],
        training_optimization_applied=True,
        focus_indexes=(2, 3),
        training_time_of_day="tarde",
    )

    carb_targets = [meal.target_carb_grams for meal in meals]

    assert min(carb_targets) >= 10.0
    assert carb_targets[2] == max(carb_targets)
    assert round(sum(carb_targets), 1) == 100.0


def test_shared_carb_minimum_scales_down_when_total_carbs_are_low():
    meals = distribute_macros_across_meals(
        base_meals=_base_meals(meals_count=4),
        protein_grams=0.0,
        fat_grams=0.0,
        carb_grams=20.0,
        distribution_percentages=[25.0, 25.0, 25.0, 25.0],
        training_optimization_applied=False,
        focus_indexes=(-1, None),
        training_time_of_day=None,
    )

    assert [meal.target_carb_grams for meal in meals] == [5.0, 5.0, 5.0, 5.0]
