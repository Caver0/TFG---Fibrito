from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from app.schemas.diet import DailyDiet, DietFood, DietMeal
from app.services import meal_regeneration_service as meal_regeneration
from app.services.diet.common import calculate_difference_summary
from app.services.diet.candidates import get_meal_structure_signature
from app.services.diet.solver import build_food_portion, calculate_meal_actuals_from_foods
from app.services.food_catalog_service import get_internal_food_lookup


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
        "aliases": [resolved_name.lower(), code.replace("_", " ")],
        "dietary_tags": [],
        "allergen_tags": [],
        "compatibility_notes": [],
    }


LOOKUP = {
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
        default_qty=2.0,
        min_qty=1.0,
        max_qty=3.0,
        step=1.0,
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
    ),
    "oats": _food(
        "oats",
        "cereales",
        protein=16.9,
        fat=6.9,
        carb=66.3,
        suitable_meals=["early", "snack"],
        name="Avena",
        default_qty=60.0,
        min_qty=25.0,
        max_qty=140.0,
        step=5.0,
    ),
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
    ),
}


def _build_breakfast_meal() -> DietMeal:
    foods_payload = [
        build_food_portion(LOOKUP["greek_yogurt"], 2.0),
        build_food_portion(LOOKUP["oats"], 55.0),
        build_food_portion(LOOKUP["avocado"], 30.0),
    ]
    actuals = calculate_meal_actuals_from_foods(foods_payload)
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
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
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
        foods=[DietFood.model_validate(food_payload) for food_payload in foods_payload],
    )


def _build_plan(
    *,
    protein_code: str,
    carb_code: str,
    fat_code: str,
) -> dict:
    foods = [
        build_food_portion(LOOKUP[protein_code], LOOKUP[protein_code]["default_quantity"]),
        build_food_portion(LOOKUP[carb_code], LOOKUP[carb_code]["default_quantity"]),
        build_food_portion(LOOKUP[fat_code], LOOKUP[fat_code]["default_quantity"]),
    ]
    return {
        "foods": foods,
        "selected_role_codes": {
            "protein": protein_code,
            "carb": carb_code,
            "fat": fat_code,
        },
        "support_food_specs": [],
        "score": 0.0,
    }


def _current_plan() -> dict:
    return {
        "selected_role_codes": {
            "protein": "greek_yogurt",
            "carb": "oats",
            "fat": "avocado",
        },
        "support_food_specs": [],
    }


def test_breakfast_regeneration_tries_full_exclusion_first(monkeypatch):
    meal = _build_breakfast_meal()
    current_food_codes = {"greek_yogurt", "oats", "avocado"}
    solver_calls: list[dict] = []
    coherence_calls: list[dict] = []

    monkeypatch.setattr(meal_regeneration, "infer_existing_meal_plan", lambda *args, **kwargs: _current_plan())

    def fake_solver(**kwargs):
        solver_calls.append(kwargs)
        return _build_plan(
            protein_code="eggs",
            carb_code="cornflakes",
            fat_code="mixed_nuts",
        )

    def fake_coherence(**kwargs):
        coherence_calls.append(kwargs)
        return kwargs["meal_plan"]

    monkeypatch.setattr(meal_regeneration, "find_exact_solution_for_meal", fake_solver)
    monkeypatch.setattr(meal_regeneration, "apply_generation_coherence", fake_coherence)

    regenerated_plan = meal_regeneration._solve_regenerated_meal_plan(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        full_food_lookup=LOOKUP,
        current_meal_food_lookup=LOOKUP,
        preference_profile=None,
        daily_food_usage={},
        current_food_codes=current_food_codes,
        variety_seed=17,
    )

    assert set(regenerated_plan["selected_role_codes"].values()) == {"eggs", "cornflakes", "mixed_nuts"}
    assert len(solver_calls) == 1
    assert solver_calls[0]["excluded_food_codes"] == current_food_codes
    assert solver_calls[0]["expand_candidate_pool"] is False
    assert solver_calls[0]["regeneration_context"]["original_food_codes"] == current_food_codes
    assert len(coherence_calls) == 1
    assert coherence_calls[0]["excluded_food_codes"] == current_food_codes
    assert coherence_calls[0]["strict_exclusions"] is True
    assert coherence_calls[0]["regeneration_context"]["prefer_visible_difference"] is True


def test_breakfast_regeneration_can_fallback_to_partially_different_meal(monkeypatch):
    meal = _build_breakfast_meal()
    current_food_codes = {"greek_yogurt", "oats", "avocado"}
    solver_calls: list[tuple[set[str] | None, bool]] = []
    coherence_calls: list[tuple[set[str] | None, bool]] = []

    monkeypatch.setattr(meal_regeneration, "infer_existing_meal_plan", lambda *args, **kwargs: _current_plan())

    def fake_solver(**kwargs):
        excluded_food_codes = kwargs["excluded_food_codes"]
        expand_candidate_pool = kwargs["expand_candidate_pool"]
        solver_calls.append((excluded_food_codes, expand_candidate_pool))
        if excluded_food_codes == current_food_codes:
            raise HTTPException(status_code=500, detail="no full breakfast alternative")
        if excluded_food_codes == {"greek_yogurt", "oats"} and expand_candidate_pool:
            return _build_plan(
                protein_code="eggs",
                carb_code="cornflakes",
                fat_code="avocado",
            )
        raise HTTPException(status_code=500, detail="keep trying")

    def fake_coherence(**kwargs):
        coherence_calls.append((kwargs["excluded_food_codes"], kwargs["strict_exclusions"]))
        return kwargs["meal_plan"]

    monkeypatch.setattr(meal_regeneration, "find_exact_solution_for_meal", fake_solver)
    monkeypatch.setattr(meal_regeneration, "apply_generation_coherence", fake_coherence)

    regenerated_plan = meal_regeneration._solve_regenerated_meal_plan(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        full_food_lookup=LOOKUP,
        current_meal_food_lookup=LOOKUP,
        preference_profile=None,
        daily_food_usage={},
        current_food_codes=current_food_codes,
        variety_seed=31,
    )

    assert solver_calls[:3] == [
        (current_food_codes, False),
        (current_food_codes, True),
        ({"greek_yogurt", "oats"}, True),
    ]
    assert set(regenerated_plan["selected_role_codes"].values()) == {"eggs", "cornflakes", "avocado"}
    assert coherence_calls[-1] == ({"greek_yogurt", "oats"}, True)


def test_regeneration_uses_last_resort_before_failing_when_reasonable_solution_exists(monkeypatch):
    meal = _build_breakfast_meal()
    current_food_codes = {"greek_yogurt", "oats", "avocado"}
    solver_calls: list[tuple[set[str] | None, bool]] = []
    coherence_calls: list[tuple[set[str] | None, bool]] = []

    monkeypatch.setattr(meal_regeneration, "infer_existing_meal_plan", lambda *args, **kwargs: _current_plan())

    def fake_solver(**kwargs):
        excluded_food_codes = kwargs["excluded_food_codes"]
        expand_candidate_pool = kwargs["expand_candidate_pool"]
        solver_calls.append((excluded_food_codes, expand_candidate_pool))
        if excluded_food_codes is None and expand_candidate_pool:
            return _build_plan(
                protein_code="eggs",
                carb_code="oats",
                fat_code="avocado",
            )
        raise HTTPException(status_code=500, detail="strict regeneration failed")

    def fake_coherence(**kwargs):
        coherence_calls.append((kwargs["excluded_food_codes"], kwargs["strict_exclusions"]))
        return kwargs["meal_plan"]

    monkeypatch.setattr(meal_regeneration, "find_exact_solution_for_meal", fake_solver)
    monkeypatch.setattr(meal_regeneration, "apply_generation_coherence", fake_coherence)

    regenerated_plan = meal_regeneration._solve_regenerated_meal_plan(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        full_food_lookup=LOOKUP,
        current_meal_food_lookup=LOOKUP,
        preference_profile=None,
        daily_food_usage={},
        current_food_codes=current_food_codes,
        variety_seed=44,
    )

    assert solver_calls[-1] == (None, True)
    assert set(regenerated_plan["selected_role_codes"].values()) == {"eggs", "oats", "avocado"}
    assert coherence_calls[-1] == (None, False)


def test_regeneration_skips_candidate_that_is_valid_but_not_visibly_different(monkeypatch):
    meal = _build_breakfast_meal()
    current_food_codes = {"greek_yogurt", "oats", "avocado"}
    solver_calls: list[tuple[set[str] | None, bool]] = []

    monkeypatch.setattr(meal_regeneration, "infer_existing_meal_plan", lambda *args, **kwargs: _current_plan())

    def fake_solver(**kwargs):
        excluded_food_codes = kwargs["excluded_food_codes"]
        expand_candidate_pool = kwargs["expand_candidate_pool"]
        solver_calls.append((excluded_food_codes, expand_candidate_pool))
        if excluded_food_codes == current_food_codes and not expand_candidate_pool:
            return _build_plan(
                protein_code="semi_skimmed_milk",
                carb_code="oats",
                fat_code="avocado",
            )
        if excluded_food_codes == current_food_codes and expand_candidate_pool:
            return _build_plan(
                protein_code="eggs",
                carb_code="cornflakes",
                fat_code="mixed_nuts",
            )
        raise HTTPException(status_code=500, detail="unexpected branch")

    monkeypatch.setattr(meal_regeneration, "find_exact_solution_for_meal", fake_solver)

    regenerated_plan = meal_regeneration._solve_regenerated_meal_plan(
        meal=meal,
        meal_index=0,
        meals_count=3,
        training_focus=False,
        full_food_lookup=LOOKUP,
        current_meal_food_lookup=LOOKUP,
        preference_profile=None,
        daily_food_usage={},
        current_food_codes=current_food_codes,
        variety_seed=52,
    )

    assert solver_calls[:2] == [
        (current_food_codes, False),
        (current_food_codes, True),
    ]
    assert set(regenerated_plan["selected_role_codes"].values()) == {"eggs", "cornflakes", "mixed_nuts"}


def test_regenerate_meal_desactiva_enriquecimiento_externo_final(monkeypatch):
    meal = _build_breakfast_meal()
    diet = DailyDiet(
        id="diet-1",
        created_at=datetime(2026, 1, 1),
        meals_count=3,
        target_calories=meal.target_calories,
        protein_grams=meal.target_protein_grams,
        fat_grams=meal.target_fat_grams,
        carb_grams=meal.target_carb_grams,
        actual_calories=meal.actual_calories,
        actual_protein_grams=meal.actual_protein_grams,
        actual_fat_grams=meal.actual_fat_grams,
        actual_carb_grams=meal.actual_carb_grams,
        distribution_percentages=[100.0],
        training_time_of_day=None,
        training_optimization_applied=False,
        food_data_source="internal",
        food_data_sources=["internal"],
        food_catalog_version="internal-v4",
        food_preferences_applied=False,
        applied_dietary_restrictions=[],
        applied_allergies=[],
        preferred_food_matches=0,
        diversity_strategy_applied=True,
        food_usage_summary={},
        food_filter_warnings=[],
        catalog_source_strategy="internal",
        spoonacular_attempted=False,
        spoonacular_attempts=0,
        spoonacular_hits=0,
        cache_hits=0,
        internal_fallbacks=0,
        resolved_foods_count=0,
        meals=[meal],
    )
    resolved_flags: list[bool] = []

    monkeypatch.setattr(meal_regeneration, "get_user_diet_by_id", lambda *args, **kwargs: diet)
    monkeypatch.setattr(meal_regeneration, "build_user_food_preferences_profile", lambda user: {})
    monkeypatch.setattr(meal_regeneration, "get_internal_food_lookup", lambda: LOOKUP)
    monkeypatch.setattr(meal_regeneration, "build_generation_food_lookup", lambda database, internal_food_lookup=None: LOOKUP)
    monkeypatch.setattr(meal_regeneration, "build_diet_context_food_lookup", lambda database, diet: LOOKUP)
    monkeypatch.setattr(
        meal_regeneration,
        "track_daily_food_usage_excluding_current_meal",
        lambda diet, meal_index_to_exclude, food_lookup: {},
    )
    monkeypatch.setattr(meal_regeneration, "get_training_focus_for_meal", lambda diet, meal_index: False)
    monkeypatch.setattr(meal_regeneration, "build_variety_seed", lambda *parts: 17)
    monkeypatch.setattr(
        meal_regeneration,
        "regenerate_meal_plan_v2",
        lambda **kwargs: _build_plan(protein_code="eggs", carb_code="cornflakes", fat_code="mixed_nuts"),
    )
    monkeypatch.setattr(meal_regeneration, "collect_selected_food_codes", lambda meals: ["eggs", "cornflakes", "mixed_nuts"])

    def fake_resolve_foods_by_codes(database, codes, allow_external_enrichment=True):
        resolved_flags.append(allow_external_enrichment)
        return ({}, {"food_catalog_version": "internal-v4", "catalog_source_strategy": "internal", "resolved_foods_count": len(codes)})

    monkeypatch.setattr(meal_regeneration, "resolve_foods_by_codes", fake_resolve_foods_by_codes)
    monkeypatch.setattr(
        meal_regeneration,
        "generate_food_based_meal",
        lambda **kwargs: {"meal_number": 1, "foods": []},
    )
    monkeypatch.setattr(
        meal_regeneration,
        "persist_updated_meal_in_diet",
        lambda database, user, diet, diet_id, meal_index, updated_meal, preference_profile, metadata_overrides=None: diet,
    )

    user = type("User", (), {"id": "user-1"})()
    meal_regeneration.regenerate_meal(
        object(),
        user=user,
        diet_id="diet-1",
        meal_number=1,
    )

    assert resolved_flags == [False]


def test_regeneration_varies_valid_breakfast_alternatives_across_seeds():
    lookup = get_internal_food_lookup()
    foods_payload = [
        build_food_portion(lookup["greek_yogurt"], 2.0),
        build_food_portion(lookup["oats"], 55.0),
        build_food_portion(lookup["avocado"], 30.0),
    ]
    actuals = calculate_meal_actuals_from_foods(foods_payload)
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
    meal = DietMeal(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
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
        foods=[DietFood.model_validate(food_payload) for food_payload in foods_payload],
    )

    regenerated_triplets = set()
    regenerated_structures = set()
    for seed in range(1, 16):
        regenerated_plan = meal_regeneration._solve_regenerated_meal_plan(
            meal=meal,
            meal_index=0,
            meals_count=4,
            training_focus=False,
            full_food_lookup=lookup,
            current_meal_food_lookup=lookup,
            preference_profile=None,
            daily_food_usage={},
            current_food_codes={"greek_yogurt", "oats", "avocado"},
            variety_seed=seed,
        )
        regenerated_triplets.add(
            tuple(
                regenerated_plan["selected_role_codes"].get(role)
                for role in ("protein", "carb", "fat")
            ),
        )
        regenerated_structures.add(
            get_meal_structure_signature(
                selected_role_codes=regenerated_plan["selected_role_codes"],
                support_food_specs=regenerated_plan["support_food_specs"],
            ),
        )

    assert len(regenerated_triplets) >= 2
    assert len(regenerated_structures) >= 2
