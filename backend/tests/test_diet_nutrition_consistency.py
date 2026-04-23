from app.services.diet.payloads import calculate_daily_totals_from_meals
from app.services.diet.solver import calculate_meal_actuals_from_foods
from app.services.nutrition_service import build_nutrition_summary


def test_build_nutrition_summary_aligns_target_calories_with_rounded_macros() -> None:
    summary = build_nutrition_summary(
        {
            "age": 28,
            "sex": "Masculino",
            "height": 178.0,
            "current_weight": 78.0,
            "training_days_per_week": 4,
            "goal": "ganar_masa",
        }
    )

    expected_calories = round(
        (summary.protein_grams * 4.0)
        + (summary.fat_grams * 9.0)
        + (summary.carb_grams * 4.0),
        1,
    )

    assert summary.target_calories == expected_calories


def test_calculate_meal_actuals_from_foods_uses_final_macro_energy() -> None:
    actuals = calculate_meal_actuals_from_foods(
        [
            {
                "calories": 100.11,
                "protein_grams": 10.04,
                "fat_grams": 3.04,
                "carb_grams": 10.04,
            },
            {
                "calories": 100.11,
                "protein_grams": 10.04,
                "fat_grams": 3.04,
                "carb_grams": 10.04,
            },
        ]
    )

    assert actuals == {
        "actual_calories": 215.7,
        "actual_protein_grams": 20.1,
        "actual_fat_grams": 6.1,
        "actual_carb_grams": 20.1,
    }


def test_calculate_daily_totals_from_meals_uses_daily_macro_energy() -> None:
    totals = calculate_daily_totals_from_meals(
        target_calories=3051.2,
        target_protein_grams=156.0,
        target_fat_grams=62.4,
        target_carb_grams=466.4,
        meals=[
            {
                "actual_calories": 1525.5,
                "actual_protein_grams": 78.0,
                "actual_fat_grams": 31.2,
                "actual_carb_grams": 233.2,
            },
            {
                "actual_calories": 1525.5,
                "actual_protein_grams": 78.1,
                "actual_fat_grams": 31.2,
                "actual_carb_grams": 233.2,
            },
        ],
    )

    assert totals["actual_calories"] == 3051.6
    assert totals["actual_protein_grams"] == 156.1
    assert totals["actual_fat_grams"] == 62.4
    assert totals["actual_carb_grams"] == 466.4
    assert totals["calorie_difference"] == 0.4
