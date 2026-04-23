from __future__ import annotations

from app.schemas.diet import DietMeal
from app.services.diet.common import calculate_difference_summary
from app.services.diet.solver import build_exact_meal_solution, build_food_portion, calculate_meal_actuals_from_foods
from app.services import meal_coherence_service
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
    "mixed_nuts": _food(
        "mixed_nuts",
        "grasas",
        protein=15.0,
        fat=50.0,
        carb=20.0,
        suitable_meals=["early", "snack"],
        name="Frutos secos",
        default_qty=20.0,
        min_qty=10.0,
        max_qty=80.0,
        step=5.0,
        aliases=["frutos secos", "nuts"],
    ),
    "whole_wheat_bread": _food(
        "whole_wheat_bread",
        "carbohidratos",
        protein=13.0,
        fat=4.2,
        carb=41.2,
        suitable_meals=["early", "main", "snack"],
        name="Pan integral",
        default_qty=70.0,
        min_qty=40.0,
        max_qty=220.0,
        step=10.0,
        aliases=["pan integral", "pan tostado", "toast", "bread"],
    ),
    "turkey_breast": _food(
        "turkey_breast",
        "proteinas",
        protein=23.0,
        fat=1.5,
        carb=0.0,
        suitable_meals=["main", "late", "snack"],
        name="Pechuga de pavo",
        default_qty=150.0,
        min_qty=60.0,
        max_qty=300.0,
        step=5.0,
        aliases=["pavo", "pechuga de pavo", "turkey"],
    ),
    "chicken_breast": _food(
        "chicken_breast",
        "proteinas",
        protein=23.0,
        fat=2.0,
        carb=0.0,
        suitable_meals=["main", "late"],
        name="Pechuga de pollo",
        default_qty=150.0,
        min_qty=60.0,
        max_qty=300.0,
        step=5.0,
        aliases=["pollo", "chicken"],
    ),
    "tuna": _food(
        "tuna",
        "proteinas",
        protein=26.0,
        fat=1.0,
        carb=0.0,
        suitable_meals=["main", "late"],
        name="Atun",
        default_qty=120.0,
        min_qty=60.0,
        max_qty=220.0,
        step=10.0,
        aliases=["atun", "tuna"],
    ),
    "rice": _food(
        "rice",
        "carbohidratos",
        protein=7.1,
        fat=0.7,
        carb=80.0,
        suitable_meals=["main", "late"],
        name="Arroz",
        default_qty=80.0,
        min_qty=30.0,
        max_qty=250.0,
        step=5.0,
        aliases=["arroz", "rice"],
    ),
    "pasta": _food(
        "pasta",
        "carbohidratos",
        protein=13.0,
        fat=1.5,
        carb=74.7,
        suitable_meals=["main", "late"],
        name="Pasta",
        default_qty=90.0,
        min_qty=40.0,
        max_qty=250.0,
        step=5.0,
        aliases=["pasta", "macarrones"],
    ),
    "potato": _food(
        "potato",
        "carbohidratos",
        protein=2.0,
        fat=0.1,
        carb=17.5,
        suitable_meals=["main", "late"],
        name="Patata",
        default_qty=250.0,
        min_qty=100.0,
        max_qty=500.0,
        step=10.0,
        aliases=["patata", "potato"],
    ),
    "olive_oil": _food(
        "olive_oil",
        "grasas",
        protein=0.0,
        fat=100.0,
        carb=0.0,
        suitable_meals=["main", "late"],
        name="Aceite de oliva",
        default_qty=10.0,
        min_qty=5.0,
        max_qty=25.0,
        step=1.0,
        aliases=["aceite de oliva", "olive oil"],
    ),
    "mixed_vegetables": _food(
        "mixed_vegetables",
        "vegetales",
        protein=2.0,
        fat=0.3,
        carb=6.0,
        suitable_meals=["main", "late", "snack"],
        name="Verduras variadas",
        default_qty=120.0,
        min_qty=80.0,
        max_qty=250.0,
        step=10.0,
        aliases=["verduras", "verduras variadas", "vegetables"],
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


def test_regeneration_mode_prevents_pairing_rules_from_reintroducing_excluded_foods():
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

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        meal_plan=original_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
        excluded_food_codes={"semi_skimmed_milk", "greek_yogurt"},
        strict_exclusions=True,
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert "semi_skimmed_milk" not in coherent_codes
    assert "greek_yogurt" not in coherent_codes


def test_regeneration_mode_prevents_templates_from_reintroducing_excluded_foods():
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

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        meal_plan=original_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
        excluded_food_codes={"banana"},
        strict_exclusions=True,
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert "banana" not in coherent_codes


def test_regeneration_allows_two_food_templates_that_are_fully_new(monkeypatch):
    meal = _build_meal_from_portions(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        portions=[("eggs", 2.0), ("banana", 1.0), ("mixed_nuts", 20.0)],
    )
    base_plan = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": LOOKUP["eggs"],
            "carb": LOOKUP["banana"],
            "fat": LOOKUP["mixed_nuts"],
        },
        support_food_specs=[],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=LOOKUP,
        training_focus=False,
        meal_slot="early",
    )

    assert base_plan is not None

    monkeypatch.setattr(
        meal_coherence_service,
        "load_meal_templates",
        lambda: [
            {
                "id": "cereal_milk_test",
                "name": "Cereal con leche",
                "meal_types": ["breakfast"],
                "priority": 100,
                "foods": [
                    {"name": "cornflakes", "role": "carb", "ratio": 0.55},
                    {"name": "leche semidesnatada", "role": "liquid", "ratio": 0.45},
                ],
            }
        ],
    )

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        meal_plan=base_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
        regeneration_context={
            "original_food_codes": {"greek_yogurt", "oats", "avocado"},
            "original_selected_role_codes": {
                "protein": "greek_yogurt",
                "carb": "oats",
                "fat": "avocado",
            },
            "prefer_visible_difference": True,
            "min_visual_difference": 2,
            "avoid_same_template": True,
        },
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert "cornflakes" in coherent_codes
    assert "semi_skimmed_milk" in coherent_codes
    assert coherent_plan.get("applied_template_id") == "cereal_milk_test"


def test_normal_generation_keeps_template_gate_for_fully_new_two_food_candidates(monkeypatch):
    meal = _build_meal_from_portions(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        portions=[("eggs", 2.0), ("banana", 1.0), ("mixed_nuts", 20.0)],
    )
    base_plan = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": LOOKUP["eggs"],
            "carb": LOOKUP["banana"],
            "fat": LOOKUP["mixed_nuts"],
        },
        support_food_specs=[],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=LOOKUP,
        training_focus=False,
        meal_slot="early",
    )

    assert base_plan is not None

    monkeypatch.setattr(
        meal_coherence_service,
        "load_meal_templates",
        lambda: [
            {
                "id": "cereal_milk_test",
                "name": "Cereal con leche",
                "meal_types": ["breakfast"],
                "priority": 100,
                "foods": [
                    {"name": "cornflakes", "role": "carb", "ratio": 0.55},
                    {"name": "leche semidesnatada", "role": "liquid", "ratio": 0.45},
                ],
            }
        ],
    )

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        meal_plan=base_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert "cornflakes" not in coherent_codes
    assert coherent_plan.get("applied_template_id") is None


def test_regeneration_prefers_breakfast_structure_visibly_different_from_original():
    meal = _build_meal_from_portions(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        portions=[("eggs", 2.0), ("whole_wheat_bread", 70.0), ("avocado", 35.0)],
    )
    base_plan = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": LOOKUP["eggs"],
            "carb": LOOKUP["whole_wheat_bread"],
            "fat": LOOKUP["avocado"],
        },
        support_food_specs=[],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=LOOKUP,
        training_focus=False,
        meal_slot="early",
    )

    assert base_plan is not None

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        meal_plan=base_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
        regeneration_context={
            "original_food_codes": {"greek_yogurt", "oats", "avocado"},
            "original_selected_role_codes": {
                "protein": "greek_yogurt",
                "carb": "oats",
                "fat": "avocado",
            },
            "prefer_visible_difference": True,
            "min_visual_difference": 2,
            "avoid_same_template": True,
        },
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert "greek_yogurt" not in coherent_codes
    assert "oats" not in coherent_codes
    assert "whole_wheat_bread" in coherent_codes


def test_regeneration_avoids_collapsing_lunch_back_to_same_visible_structure(monkeypatch):
    meal = _build_meal_from_portions(
        meal_number=2,
        meal_slot="main",
        meal_role="meal",
        meal_label="Comida",
        portions=[("rice", 80.0), ("tuna", 120.0), ("olive_oil", 10.0)],
    )
    base_plan = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": LOOKUP["tuna"],
            "carb": LOOKUP["rice"],
            "fat": LOOKUP["olive_oil"],
        },
        support_food_specs=[],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=LOOKUP,
        training_focus=False,
        meal_slot="main",
    )

    assert base_plan is not None

    monkeypatch.setattr(
        meal_coherence_service,
        "load_meal_templates",
        lambda: [
            {
                "id": "same_rice_chicken",
                "name": "Arroz con pollo",
                "meal_types": ["lunch"],
                "priority": 100,
                "foods": [
                    {"name": "arroz", "role": "carb", "ratio": 0.5},
                    {"name": "pollo", "role": "protein", "ratio": 0.35},
                    {"name": "verduras", "role": "vegetable", "ratio": 0.15},
                ],
            },
            {
                "id": "different_pasta_tuna",
                "name": "Pasta con atun",
                "meal_types": ["lunch"],
                "priority": 90,
                "foods": [
                    {"name": "pasta", "role": "carb", "ratio": 0.5},
                    {"name": "atun", "role": "protein", "ratio": 0.3},
                    {"name": "verduras", "role": "vegetable", "ratio": 0.2},
                ],
            },
        ],
    )

    coherent_plan = apply_generation_coherence(
        meal=meal,
        meal_index=1,
        meals_count=3,
        training_focus=False,
        meal_plan=base_plan,
        food_lookup=LOOKUP,
        preference_profile=None,
        regeneration_context={
            "original_food_codes": {"rice", "chicken_breast", "mixed_vegetables"},
            "original_selected_role_codes": {
                "protein": "chicken_breast",
                "carb": "rice",
                "fat": "olive_oil",
            },
            "original_support_food_specs": [
                {"role": "vegetable", "food_code": "mixed_vegetables", "quantity": 120.0},
            ],
            "prefer_visible_difference": True,
            "min_visual_difference": 2,
            "avoid_same_template": True,
        },
    )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert "pasta" in coherent_codes
    assert "chicken_breast" not in coherent_codes
    assert coherent_plan.get("applied_template_id") == "different_pasta_tuna"
