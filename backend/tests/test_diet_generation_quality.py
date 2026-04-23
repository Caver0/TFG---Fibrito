from __future__ import annotations

from unittest.mock import patch

from app.schemas.diet import DietMeal
from app.services.diet.candidates import (
    apply_meal_candidate_constraints,
    create_daily_food_usage_tracker,
    get_meal_structure_signature,
    track_food_usage_across_day,
)
from app.services.diet.solver import build_exact_meal_solution, find_exact_solution_for_meal
from app.services.food_catalog_service import get_internal_food_lookup
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
        "aliases": aliases or [resolved_name.lower(), code.replace("_", " ")],
        "dietary_tags": [],
        "allergen_tags": [],
        "compatibility_notes": [],
    }


def _meal(
    *,
    meal_number: int,
    meal_slot: str,
    meal_role: str,
    protein: float,
    fat: float,
    carb: float,
) -> DietMeal:
    calories = protein * 4 + fat * 9 + carb * 4
    return DietMeal(
        meal_number=meal_number,
        meal_slot=meal_slot,
        meal_role=meal_role,
        meal_label="Comida",
        distribution_percentage=30.0,
        target_calories=calories,
        target_protein_grams=protein,
        target_fat_grams=fat,
        target_carb_grams=carb,
        actual_calories=0.0,
        actual_protein_grams=0.0,
        actual_fat_grams=0.0,
        actual_carb_grams=0.0,
    )


def test_apply_meal_candidate_constraints_reduce_variant_families():
    lookup = {
        "greek_yogurt_zero": _food(
            "greek_yogurt_zero",
            "lacteos",
            protein=11.0,
            fat=0.1,
            carb=4.0,
            suitable_meals=["early"],
            name="Yogur griego 0%",
            aliases=["greek yogurt 0", "yogur griego 0"],
        ),
        "greek_yogurt_natural": _food(
            "greek_yogurt_natural",
            "lacteos",
            protein=10.0,
            fat=1.0,
            carb=4.0,
            suitable_meals=["early"],
            name="Yogur griego natural",
            aliases=["greek yogurt natural", "yogur griego natural"],
        ),
        "eggs": _food(
            "eggs",
            "proteinas",
            protein=6.5,
            fat=5.3,
            carb=0.6,
            suitable_meals=["early"],
            reference_amount=1.0,
            reference_unit="unidad",
            grams_per_reference=60.0,
        ),
    }
    constrained = apply_meal_candidate_constraints(
        {"protein": ["greek_yogurt_zero", "greek_yogurt_natural", "eggs"]},
        food_lookup=lookup,
    )

    assert constrained["protein"] == ["greek_yogurt_zero", "eggs"]


def test_build_exact_meal_solution_blocks_equivalent_yogurt_variants_in_same_meal():
    lookup = {
        "greek_yogurt_zero": _food(
            "greek_yogurt_zero",
            "lacteos",
            protein=11.0,
            fat=0.1,
            carb=4.0,
            suitable_meals=["early"],
            name="Yogur griego 0%",
            aliases=["greek yogurt 0", "yogur griego 0"],
            reference_amount=1.0,
            reference_unit="unidad",
            grams_per_reference=125.0,
        ),
        "greek_yogurt_natural": _food(
            "greek_yogurt_natural",
            "lacteos",
            protein=10.0,
            fat=1.0,
            carb=4.0,
            suitable_meals=["early"],
            name="Yogur griego natural",
            aliases=["greek yogurt natural", "yogur griego natural"],
            reference_amount=1.0,
            reference_unit="unidad",
            grams_per_reference=125.0,
        ),
        "oats": _food("oats", "cereales", protein=16.9, fat=6.9, carb=66.3, suitable_meals=["early"], name="Avena"),
        "mixed_nuts": _food("mixed_nuts", "grasas", protein=15.0, fat=50.0, carb=20.0, suitable_meals=["early"], name="Frutos secos"),
    }
    meal = _meal(meal_number=1, meal_slot="early", meal_role="breakfast", protein=30.0, fat=15.0, carb=45.0)

    solution = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": lookup["greek_yogurt_zero"],
            "carb": lookup["oats"],
            "fat": lookup["mixed_nuts"],
        },
        support_food_specs=[{
            "role": "dairy",
            "food_code": "greek_yogurt_natural",
            "quantity": 1.0,
        }],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=lookup,
        training_focus=False,
        meal_slot="early",
    )

    assert solution is None


def test_breakfast_solver_generates_multiple_visible_structures_across_seeds():
    lookup = get_internal_food_lookup()
    meal = _meal(meal_number=1, meal_slot="early", meal_role="breakfast", protein=30.0, fat=15.0, carb=50.0)

    structures = {
        get_meal_structure_signature(
            selected_role_codes=solution["selected_role_codes"],
            support_food_specs=solution["support_food_specs"],
        )
        for seed in range(1, 31)
        for solution in [
            find_exact_solution_for_meal(
                meal=meal,
                meal_index=0,
                meals_count=4,
                training_focus=False,
                food_lookup=lookup,
                variety_seed=seed,
            )
        ]
    }

    assert len(structures) >= 5


def test_breakfast_full_generation_retains_multiple_main_structures_across_seeds():
    lookup = get_internal_food_lookup()
    meal = _meal(meal_number=1, meal_slot="early", meal_role="breakfast", protein=30.0, fat=15.0, carb=50.0)

    coherent_structures = set()
    coherent_role_triplets = set()
    for seed in range(1, 31):
        solver_plan = find_exact_solution_for_meal(
            meal=meal,
            meal_index=0,
            meals_count=4,
            training_focus=False,
            food_lookup=lookup,
            variety_seed=seed,
        )
        coherent_plan = apply_generation_coherence(
            meal=meal,
            meal_index=0,
            meals_count=4,
            training_focus=False,
            meal_plan=solver_plan,
            food_lookup=lookup,
            preference_profile=None,
            daily_diversity_context=create_daily_food_usage_tracker(),
            variety_seed=seed,
        )
        coherent_structures.add(
            get_meal_structure_signature(
                selected_role_codes=coherent_plan["selected_role_codes"],
                support_food_specs=coherent_plan["support_food_specs"],
            ),
        )
        coherent_role_triplets.add(
            tuple(
                coherent_plan["selected_role_codes"].get(role)
                for role in ("protein", "carb", "fat")
            ),
        )

    assert len(coherent_structures) >= 5
    assert len(coherent_role_triplets) >= 3


def test_daily_diversity_context_avoids_repeating_same_structure_when_alternatives_exist():
    lookup = get_internal_food_lookup()
    meal = _meal(meal_number=2, meal_slot="main", meal_role="meal", protein=50.0, fat=20.0, carb=75.0)
    base_plan = build_exact_meal_solution(
        meal=meal,
        role_foods={
            "protein": lookup["tuna"],
            "carb": lookup["rice"],
            "fat": lookup["olive_oil"],
        },
        support_food_specs=[],
        candidate_indexes={"protein": 0, "carb": 0, "fat": 0},
        food_lookup=lookup,
        training_focus=False,
        meal_slot="main",
    )
    assert base_plan is not None

    daily_usage = create_daily_food_usage_tracker()
    track_food_usage_across_day(
        daily_usage,
        {
            "selected_role_codes": {
                "protein": "chicken_breast",
                "carb": "rice",
                "fat": "olive_oil",
            },
            "support_food_specs": [{
                "role": "vegetable",
                "food_code": "mixed_vegetables",
                "quantity": 120.0,
            }],
            "applied_template_id": "same_rice_chicken",
        },
    )

    with patch.object(
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
    ):
        coherent_plan = apply_generation_coherence(
            meal=meal,
            meal_index=1,
            meals_count=3,
            training_focus=False,
            meal_plan=base_plan,
            food_lookup=lookup,
            preference_profile=None,
            daily_diversity_context=daily_usage,
        )

    coherent_codes = {food["food_code"] for food in coherent_plan["foods"]}
    assert coherent_plan.get("applied_template_id") == "different_pasta_tuna"
    assert "pasta" in coherent_codes


def test_find_exact_solution_for_meal_avoids_repeating_chicken_rice_pair_when_day_already_has_it():
    lookup = get_internal_food_lookup()
    meal = _meal(meal_number=3, meal_slot="main", meal_role="meal", protein=50.0, fat=20.0, carb=75.0)
    daily_usage = create_daily_food_usage_tracker()
    track_food_usage_across_day(
        daily_usage,
        {
            "selected_role_codes": {
                "protein": "chicken_breast",
                "carb": "rice",
                "fat": "olive_oil",
            },
            "support_food_specs": [{
                "role": "vegetable",
                "food_code": "mixed_vegetables",
                "quantity": 120.0,
            }],
        },
    )

    solution = find_exact_solution_for_meal(
        meal=meal,
        meal_index=2,
        meals_count=3,
        training_focus=False,
        food_lookup=lookup,
        daily_food_usage=daily_usage,
        variety_seed=19,
    )

    assert solution["selected_role_codes"] != {
        "protein": "chicken_breast",
        "carb": "rice",
        "fat": "olive_oil",
    }
