from __future__ import annotations

from app.schemas.diet import DietMeal
from app.services.diet.common import calculate_difference_summary
from app.services.diet.solver import build_exact_meal_solution, build_food_portion, calculate_meal_actuals_from_foods
from app.services.meal_coherence_service import apply_generation_coherence


def _food(
    code: str,
    category: str,
    *,
    protein: float,
    fat: float,
    carb: float,
    suitable_meals: list[str],
    name: str | None = None,
    reference_amount: float = 100.0,
    reference_unit: str = "g",
    grams_per_reference: float | None = None,
    default_qty: float = 100.0,
    min_qty: float = 10.0,
    max_qty: float = 400.0,
    step: float = 5.0,
    aliases: list[str] | None = None,
) -> dict:
    resolved_name = name or code.replace("_", " ").title()
    return {
        "code": code,
        "name": resolved_name,
        "display_name": resolved_name,
        "original_name": resolved_name,
        "normalized_name": resolved_name.lower(),
        "category": category,
        "source": "internal_catalog",
        "origin_source": "internal_catalog",
        "protein_grams": protein,
        "fat_grams": fat,
        "carb_grams": carb,
        "calories": protein * 4 + fat * 9 + carb * 4,
        "reference_amount": reference_amount,
        "reference_unit": reference_unit,
        "grams_per_reference": grams_per_reference or reference_amount,
        "default_quantity": default_qty,
        "max_quantity": max_qty,
        "min_quantity": min_qty,
        "step": step,
        "suitable_meals": suitable_meals,
        "aliases": aliases or [resolved_name.lower()],
        "dietary_tags": [],
        "allergen_tags": [],
        "compatibility_notes": [],
    }


LOOKUP = {
    "cornflakes": _food(
        "cornflakes",
        "cereales",
        protein=7.0,
        fat=1.0,
        carb=84.0,
        suitable_meals=["early", "snack"],
        name="Cornflakes",
        default_qty=55.0,
        min_qty=20.0,
        max_qty=140.0,
        aliases=["cornflakes", "cereales"],
    ),
    "eggs": _food(
        "eggs",
        "proteinas",
        protein=6.5,
        fat=5.3,
        carb=0.6,
        suitable_meals=["early", "main"],
        name="Huevos",
        reference_amount=1.0,
        reference_unit="unidad",
        grams_per_reference=60.0,
        default_qty=2.0,
        min_qty=1.0,
        max_qty=4.0,
        step=1.0,
        aliases=["huevo", "huevos", "egg", "eggs"],
    ),
    "greek_yogurt": _food(
        "greek_yogurt",
        "lacteos",
        protein=12.0,
        fat=0.5,
        carb=6.0,
        suitable_meals=["early", "snack"],
        name="Yogur griego",
        reference_amount=1.0,
        reference_unit="unidad",
        grams_per_reference=125.0,
        default_qty=1.0,
        min_qty=1.0,
        max_qty=3.0,
        step=1.0,
        aliases=["yogur", "yogur griego", "greek yogurt"],
    ),
    "semi_skimmed_milk": _food(
        "semi_skimmed_milk",
        "lacteos",
        protein=8.3,
        fat=3.8,
        carb=11.8,
        suitable_meals=["early", "snack"],
        name="Leche semidesnatada",
        reference_amount=250.0,
        reference_unit="ml",
        grams_per_reference=250.0,
        default_qty=250.0,
        min_qty=125.0,
        max_qty=500.0,
        step=125.0,
        aliases=["leche", "leche semidesnatada", "milk"],
    ),
    "oats": _food(
        "oats",
        "carbohidratos",
        protein=16.9,
        fat=6.9,
        carb=66.3,
        suitable_meals=["early", "snack"],
        name="Avena",
        default_qty=60.0,
        min_qty=25.0,
        max_qty=140.0,
        step=5.0,
        aliases=["avena", "oats"],
    ),
    "banana": _food(
        "banana",
        "frutas",
        protein=1.3,
        fat=0.4,
        carb=27.0,
        suitable_meals=["early", "snack"],
        name="Platano",
        reference_amount=1.0,
        reference_unit="unidad",
        grams_per_reference=120.0,
        default_qty=1.0,
        min_qty=0.5,
        max_qty=2.0,
        step=0.5,
        aliases=["platano", "banana", "fruta"],
    ),
    "avocado": _food(
        "avocado",
        "grasas",
        protein=2.0,
        fat=15.0,
        carb=9.0,
        suitable_meals=["early", "main", "snack"],
        name="Aguacate",
        default_qty=50.0,
        min_qty=20.0,
        max_qty=150.0,
        step=10.0,
        aliases=["aguacate", "avocado"],
    ),
}


def _build_meal_from_portions(
    *,
    meal_number: int,
    meal_slot: str,
    meal_role: str,
    meal_label: str,
    portions: list[tuple[str, float]],
) -> DietMeal:
    foods = [build_food_portion(LOOKUP[food_code], quantity) for food_code, quantity in portions]
    actuals = calculate_meal_actuals_from_foods(foods)
    differences = calculate_difference_summary(
        target_calories=actuals["actual_calories"],
        target_protein_grams=actuals["actual_protein_grams"],
        target_fat_grams=actuals["actual_fat_grams"],
        target_carb_grams=actuals["actual_carb_grams"],
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
    )
    return DietMeal(
        meal_number=meal_number,
        meal_slot=meal_slot,
        meal_role=meal_role,
        meal_label=meal_label,
        distribution_percentage=25.0,
        target_calories=actuals["actual_calories"],
        target_protein_grams=actuals["actual_protein_grams"],
        target_fat_grams=actuals["actual_fat_grams"],
        target_carb_grams=actuals["actual_carb_grams"],
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
        calorie_difference=differences["calorie_difference"],
        protein_difference=differences["protein_difference"],
        fat_difference=differences["fat_difference"],
        carb_difference=differences["carb_difference"],
        foods=[],
    )


def test_breakfast_cereal_generation_adds_a_preferred_dairy_pairing():
    meal = _build_meal_from_portions(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        portions=[("eggs", 2.0), ("cornflakes", 55.0), ("avocado", 30.0)],
    )
    original_plan = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": LOOKUP["eggs"],
            "carb": LOOKUP["cornflakes"],
            "fat": LOOKUP["avocado"],
        },
        support_food_specs=[],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=LOOKUP,
        training_focus=False,
        meal_slot="early",
    )

    assert original_plan is not None
    original_codes = {food["food_code"] for food in original_plan["foods"]}
    assert "semi_skimmed_milk" not in original_codes
    assert "greek_yogurt" not in original_codes

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        meal_plan=original_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert {"semi_skimmed_milk", "greek_yogurt"} & coherent_codes


def test_breakfast_templates_can_promote_oats_yogurt_banana_when_they_fit():
    meal = _build_meal_from_portions(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        portions=[("greek_yogurt", 2.0), ("oats", 45.0), ("avocado", 20.0)],
    )
    original_plan = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": LOOKUP["greek_yogurt"],
            "carb": LOOKUP["oats"],
            "fat": LOOKUP["avocado"],
        },
        support_food_specs=[],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=LOOKUP,
        training_focus=False,
        meal_slot="early",
    )

    assert original_plan is not None
    assert "banana" not in {food["food_code"] for food in original_plan["foods"]}

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        meal_plan=original_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert "banana" in coherent_codes
