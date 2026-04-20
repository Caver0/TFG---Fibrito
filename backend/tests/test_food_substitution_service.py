from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.diet import (
    BuscarAlimentoSustitutoRequest,
    DailyDiet,
    DietFood,
    DietMeal,
    ReplaceFoodRequest,
)
from app.schemas.user import FoodPreferencesProfile, UserPublic
from app.services.diet.common import calculate_difference_summary
from app.services.diet.solver import build_food_portion, calculate_meal_actuals_from_foods
from app.services.food_substitution_service import (
    determinar_macro_dominante,
    list_food_replacement_options,
    replace_food_in_meal,
    search_replacement_food,
)
from app.utils.normalization import normalize_food_name

_PATCH_ML = patch("app.services.diet.candidates.predict_meal_slot_scores", return_value={})


def _food(
    code: str,
    category: str,
    *,
    protein: float,
    fat: float,
    carb: float,
    suitable_meals: list[str],
    name: str | None = None,
    source: str = "internal_catalog",
    default_qty: float = 100.0,
    max_qty: float = 400.0,
    min_qty: float = 10.0,
    step: float = 5.0,
) -> dict:
    resolved_name = name or code.replace("_", " ").title()
    aliases = [
        normalize_food_name(resolved_name),
        normalize_food_name(code.replace("_", " ")),
    ]
    return {
        "code": code,
        "internal_code": None,
        "name": resolved_name,
        "display_name": resolved_name,
        "original_name": resolved_name,
        "normalized_name": normalize_food_name(resolved_name),
        "category": category,
        "source": source,
        "origin_source": source,
        "protein_grams": protein,
        "fat_grams": fat,
        "carb_grams": carb,
        "calories": protein * 4 + fat * 9 + carb * 4,
        "reference_amount": 100.0,
        "reference_unit": "g",
        "grams_per_reference": 100.0,
        "default_quantity": default_qty,
        "max_quantity": max_qty,
        "min_quantity": min_qty,
        "step": step,
        "suitable_meals": suitable_meals,
        "preference_labels": aliases,
        "aliases": aliases,
        "dietary_tags": ["vegetariano", "vegano", "sin_lactosa", "sin_gluten"],
        "allergen_tags": [],
        "compatibility_notes": [],
    }


BREAKFAST_LOOKUP = {
    "greek_yogurt": _food("greek_yogurt", "lacteos", protein=10.0, fat=0.4, carb=4.0, suitable_meals=["early"], default_qty=220.0, min_qty=80.0, max_qty=450.0),
    "oats": _food("oats", "cereales", protein=13.0, fat=7.0, carb=66.0, suitable_meals=["early"], default_qty=60.0, min_qty=20.0, max_qty=180.0, step=10.0),
    "cornflakes": _food("cornflakes", "cereales", protein=7.0, fat=1.0, carb=84.0, suitable_meals=["early"], default_qty=50.0, min_qty=20.0, max_qty=160.0, step=10.0),
    "avocado": _food("avocado", "grasas", protein=2.0, fat=15.0, carb=9.0, suitable_meals=["early", "main", "late"], default_qty=50.0, min_qty=15.0, max_qty=150.0, step=5.0),
    "dates": _food("dates", "frutas", protein=2.5, fat=0.4, carb=75.0, suitable_meals=["early"], default_qty=40.0, min_qty=10.0, max_qty=180.0, step=5.0, name="Dates"),
    "banana": _food("banana", "frutas", protein=1.1, fat=0.3, carb=23.0, suitable_meals=["early"], default_qty=120.0, min_qty=60.0, max_qty=260.0, step=10.0, name="Banana"),
    "apple": _food("apple", "frutas", protein=0.3, fat=0.2, carb=14.0, suitable_meals=["early"], default_qty=150.0, min_qty=80.0, max_qty=260.0, step=10.0, name="Apple"),
    "mixed_nuts": _food("mixed_nuts", "grasas", protein=15.0, fat=50.0, carb=20.0, suitable_meals=["early", "main", "late"], default_qty=25.0, min_qty=10.0, max_qty=70.0, step=5.0, name="Mixed Nuts"),
    "peanut_butter": _food("peanut_butter", "grasas", protein=25.0, fat=50.0, carb=20.0, suitable_meals=["early"], default_qty=15.0, min_qty=5.0, max_qty=45.0, step=5.0, name="Peanut Butter"),
}
BREAKFAST_LOOKUP["mixed_nuts"]["allergen_tags"] = ["frutos_secos"]
BREAKFAST_LOOKUP["peanut_butter"]["allergen_tags"] = ["frutos_secos"]

LUNCH_LOOKUP = {
    "chicken_breast": _food("chicken_breast", "proteinas", protein=23.0, fat=2.0, carb=0.0, suitable_meals=["main", "late"], default_qty=170.0, min_qty=80.0, max_qty=300.0, step=10.0, name="Chicken Breast"),
    "turkey_breast": _food("turkey_breast", "proteinas", protein=24.0, fat=1.5, carb=0.0, suitable_meals=["main", "late"], default_qty=170.0, min_qty=80.0, max_qty=300.0, step=10.0, name="Turkey Breast"),
    "rice": _food("rice", "carbohidratos", protein=7.0, fat=1.0, carb=78.0, suitable_meals=["main", "late"], default_qty=140.0, min_qty=40.0, max_qty=260.0, step=10.0, name="Rice"),
    "olive_oil": _food("olive_oil", "grasas", protein=0.0, fat=100.0, carb=0.0, suitable_meals=["main", "late"], default_qty=10.0, min_qty=3.0, max_qty=20.0, step=1.0, name="Olive Oil"),
    "mixed_vegetables": _food("mixed_vegetables", "vegetales", protein=2.0, fat=0.2, carb=8.0, suitable_meals=["main", "late"], default_qty=120.0, min_qty=60.0, max_qty=220.0, step=10.0, name="Mixed Vegetables"),
}


def _build_user(*, allergies: list[str] | None = None) -> UserPublic:
    return UserPublic(
        id="user-1",
        name="Jorge",
        email="jorge@example.com",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        food_preferences=FoodPreferencesProfile(allergies=allergies or []),
    )


def _meal_from_blueprint(
    *,
    meal_number: int,
    meal_slot: str,
    meal_role: str,
    meal_label: str,
    lookup: dict[str, dict],
    role_quantities: dict[str, tuple[str, float]],
    support_specs: list[dict[str, float]] | None = None,
) -> DietMeal:
    foods_payload = [
        build_food_portion(lookup[food_code], quantity)
        for food_code, quantity in role_quantities.values()
    ]
    for support_food in support_specs or []:
        foods_payload.append(
            build_food_portion(
                lookup[support_food["food_code"]],
                float(support_food["quantity"]),
            )
        )

    actuals = calculate_meal_actuals_from_foods(foods_payload)
    difference_summary = calculate_difference_summary(
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
        distribution_percentage=33.33,
        target_calories=actuals["actual_calories"],
        target_protein_grams=actuals["actual_protein_grams"],
        target_fat_grams=actuals["actual_fat_grams"],
        target_carb_grams=actuals["actual_carb_grams"],
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
        calorie_difference=difference_summary["calorie_difference"],
        protein_difference=difference_summary["protein_difference"],
        fat_difference=difference_summary["fat_difference"],
        carb_difference=difference_summary["carb_difference"],
        foods=[DietFood.model_validate(food_payload) for food_payload in foods_payload],
    )


def _build_diet(meal: DietMeal) -> DailyDiet:
    clone_2 = meal.model_copy(update={"meal_number": 2, "meal_label": "Comida 2"})
    clone_3 = meal.model_copy(update={"meal_number": 3, "meal_label": "Comida 3"})
    meals = [meal, clone_2, clone_3]
    total_calories = sum(float(current_meal.target_calories) for current_meal in meals)
    total_protein = sum(float(current_meal.target_protein_grams) for current_meal in meals)
    total_fat = sum(float(current_meal.target_fat_grams) for current_meal in meals)
    total_carb = sum(float(current_meal.target_carb_grams) for current_meal in meals)
    return DailyDiet(
        id="diet-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        meals_count=3,
        target_calories=total_calories,
        protein_grams=total_protein,
        fat_grams=total_fat,
        carb_grams=total_carb,
        actual_calories=total_calories,
        actual_protein_grams=total_protein,
        actual_fat_grams=total_fat,
        actual_carb_grams=total_carb,
        calorie_difference=0.0,
        protein_difference=0.0,
        fat_difference=0.0,
        carb_difference=0.0,
        distribution_percentages=[33.33, 33.33, 33.34],
        training_time_of_day=None,
        training_optimization_applied=False,
        food_data_source="internal",
        food_data_sources=["internal"],
        food_catalog_version="test",
        food_preferences_applied=False,
        applied_dietary_restrictions=[],
        applied_allergies=[],
        preferred_food_matches=0,
        diversity_strategy_applied=True,
        food_usage_summary={},
        food_filter_warnings=[],
        catalog_source_strategy="test",
        spoonacular_attempted=False,
        spoonacular_attempts=0,
        spoonacular_hits=0,
        cache_hits=0,
        internal_fallbacks=0,
        resolved_foods_count=0,
        meals=meals,
    )


def _context_from_meal(
    *,
    lookup: dict[str, dict],
    meal: DietMeal,
    current_food_code: str,
    slot: dict[str, str],
    user: UserPublic | None = None,
) -> dict:
    diet = _build_diet(meal)
    current_food = next(food for food in meal.foods if food.food_code == current_food_code)
    current_food_entry = lookup[current_food_code]
    active_user = user or _build_user()
    return {
        "diet": diet,
        "meal": meal,
        "meal_index": 0,
        "current_food": current_food,
        "current_food_entry": current_food_entry,
        "context_food_lookup": lookup,
        "meal_food_lookup": lookup,
        "preference_profile": {
            "preferred_foods": [],
            "disliked_foods": [],
            "dietary_restrictions": [],
            "allergies": list(active_user.food_preferences.allergies),
            "normalized_preferred_foods": set(),
            "normalized_disliked_foods": set(),
            "dietary_restriction_set": set(),
            "allergy_set": set(active_user.food_preferences.allergies),
            "allergy_tag_set": {"frutos_secos"} if "frutos secos" in active_user.food_preferences.allergies else set(),
            "has_positive_preferences": False,
            "has_negative_preferences": bool(active_user.food_preferences.allergies),
            "has_preferences": bool(active_user.food_preferences.allergies),
            "warnings": [],
        },
        "training_focus": False,
        "meal_slot": meal.meal_slot,
        "meal_role": meal.meal_role,
        "inferred_plan": {
            "selected_role_codes": {
                "protein": next(food.food_code for food in meal.foods if food.food_code in {"greek_yogurt", "chicken_breast", "peanut_butter"}),
            },
            "support_food_specs": [],
        },
        "slot": slot,
        "daily_food_usage": {
            "food_counts": {},
            "role_counts": {},
            "main_pair_counts": {},
        },
        "current_macro_dominante": "carb" if current_food_code == "dates" else "fat" if current_food_code == "peanut_butter" else "protein",
        "meal_food_codes": {food.food_code for food in meal.foods if food.food_code},
    }


def _persist_updated_meal(database, *, diet, meal_index, updated_meal, **kwargs):
    del database, kwargs
    updated_meals = [
        updated_meal if index == meal_index else current_meal.model_dump()
        for index, current_meal in enumerate(diet.meals)
    ]
    return DailyDiet.model_validate({
        **diet.model_dump(),
        "meals": updated_meals,
    })


def _resolver_desde_lookup(lookup: dict[str, dict]):
    def _resolver(database, *, food_code=None, food_name=None, include_external=True):
        del database, include_external
        if food_code and food_code in lookup:
            return lookup[food_code]

        normalized_name = normalize_food_name(food_name or "")
        for food in lookup.values():
            aliases = [normalize_food_name(alias) for alias in food.get("aliases", [])]
            if normalized_name == normalize_food_name(food["name"]) or normalized_name in aliases:
                return food
        return None

    return _resolver


def _build_context_dates_breakfast(user: UserPublic | None = None) -> tuple[dict, dict[str, dict]]:
    lookup = dict(BREAKFAST_LOOKUP)
    meal = _meal_from_blueprint(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        lookup=lookup,
        role_quantities={
            "protein": ("greek_yogurt", 240.0),
            "carb": ("oats", 35.0),
            "fat": ("avocado", 25.0),
        },
        support_specs=[{"role": "fruit", "food_code": "dates", "quantity": 20.0}],
    )
    return _context_from_meal(
        lookup=lookup,
        meal=meal,
        current_food_code="dates",
        slot={"kind": "support", "role": "fruit"},
        user=user,
    ), lookup


def _build_context_peanut_butter_breakfast(user: UserPublic | None = None) -> tuple[dict, dict[str, dict]]:
    lookup = dict(BREAKFAST_LOOKUP)
    meal = _meal_from_blueprint(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        lookup=lookup,
        role_quantities={
            "protein": ("greek_yogurt", 230.0),
            "carb": ("oats", 30.0),
            "fat": ("peanut_butter", 10.0),
        },
        support_specs=[{"role": "fruit", "food_code": "banana", "quantity": 90.0}],
    )
    return _context_from_meal(
        lookup=lookup,
        meal=meal,
        current_food_code="peanut_butter",
        slot={"kind": "role", "role": "fat"},
        user=user,
    ), lookup


def _build_context_chicken_lunch(user: UserPublic | None = None) -> tuple[dict, dict[str, dict]]:
    lookup = dict(LUNCH_LOOKUP)
    meal = _meal_from_blueprint(
        meal_number=1,
        meal_slot="main",
        meal_role="meal",
        meal_label="Comida",
        lookup=lookup,
        role_quantities={
            "protein": ("chicken_breast", 170.0),
            "carb": ("rice", 65.0),
            "fat": ("olive_oil", 10.0),
        },
        support_specs=[{"role": "vegetable", "food_code": "mixed_vegetables", "quantity": 120.0}],
    )
    return _context_from_meal(
        lookup=lookup,
        meal=meal,
        current_food_code="chicken_breast",
        slot={"kind": "role", "role": "protein"},
        user=user,
    ), lookup


def _patched_context(context: dict):
    return patch("app.services.food_substitution_service._build_food_replacement_context", return_value=context)


@pytest.mark.parametrize(
    ("food", "expected_macro"),
    [
        (BREAKFAST_LOOKUP["mixed_nuts"], "fat"),
        (BREAKFAST_LOOKUP["banana"], "carb"),
        (BREAKFAST_LOOKUP["greek_yogurt"], "protein"),
    ],
)
def test_alimentos_mixtos_y_de_soporte_tienen_macro_dominante_estable(food: dict, expected_macro: str):
    assert determinar_macro_dominante(food) == expected_macro


def test_un_carbohidrato_se_sustituye_por_otro_carbohidrato_equivalente():
    context, _lookup = _build_context_dates_breakfast()
    payload = ReplaceFoodRequest(current_food_name="Dates", current_food_code="dates")

    with _PATCH_ML, _patched_context(context):
        response = list_food_replacement_options(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    assert response.current_macro_dominante == "carb"
    assert response.options
    assert any(option.food_code in {"banana", "apple", "cornflakes"} for option in response.options)
    assert all(option.macro_dominante == "carb" for option in response.options)
    assert all((option.equivalent_grams or 0) > 0 for option in response.options)


def test_una_proteina_se_sustituye_por_otra_proteina_equivalente():
    context, _lookup = _build_context_chicken_lunch()
    payload = ReplaceFoodRequest(current_food_name="Chicken Breast", current_food_code="chicken_breast")

    with _PATCH_ML, _patched_context(context):
        response = list_food_replacement_options(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    assert any(option.food_code == "turkey_breast" for option in response.options)
    assert all(option.macro_dominante == "protein" for option in response.options)


def test_una_grasa_se_sustituye_por_otra_grasa_equivalente():
    context, _lookup = _build_context_peanut_butter_breakfast()
    payload = ReplaceFoodRequest(current_food_name="Peanut Butter", current_food_code="peanut_butter")

    with _PATCH_ML, _patched_context(context):
        response = list_food_replacement_options(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    assert any(option.food_code == "mixed_nuts" for option in response.options)
    assert all(option.macro_dominante == "fat" for option in response.options)


@pytest.mark.parametrize("source", ["local_cache", "spoonacular"])
def test_alimento_buscado_manualmente_se_acepta_si_cumple_macro_y_encaje(source: str):
    context, _lookup = _build_context_dates_breakfast()
    mango = _food(
        f"mango_{source}",
        "frutas",
        protein=0.8,
        fat=0.4,
        carb=15.0,
        suitable_meals=["early"],
        name="Mango",
        source=source,
        default_qty=120.0,
        min_qty=60.0,
        max_qty=240.0,
        step=10.0,
    )
    payload = BuscarAlimentoSustitutoRequest(
        current_food_name="Dates",
        current_food_code="dates",
        query="mango",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        return_value=mango,
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[mango],
    ):
        response = search_replacement_food(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    assert response.current_macro_dominante == "carb"
    assert response.candidates[0].valid is True
    assert response.candidates[0].macro_dominante == "carb"
    assert response.candidates[0].source == source


def test_alimento_buscado_manualmente_se_rechaza_si_no_cumple_el_mismo_macro():
    context, _lookup = _build_context_dates_breakfast()
    payload = BuscarAlimentoSustitutoRequest(
        current_food_name="Dates",
        current_food_code="dates",
        query="mixed nuts",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        return_value=BREAKFAST_LOOKUP["mixed_nuts"],
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[BREAKFAST_LOOKUP["mixed_nuts"]],
    ):
        response = search_replacement_food(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    assert response.candidates[0].valid is False
    assert response.candidates[0].validation_note.startswith("No compatible:")
    assert "grasa" in (response.candidates[0].validation_note or "").lower()


def test_la_busqueda_manual_no_depende_de_un_fit_final_para_devolver_candidatos():
    context, _lookup = _build_context_dates_breakfast()
    granola_imposible = _food(
        "granola_imposible",
        "cereales",
        protein=11.0,
        fat=18.0,
        carb=58.0,
        suitable_meals=["early"],
        name="Granola Imposible",
        default_qty=280.0,
        min_qty=280.0,
        max_qty=280.0,
        step=1.0,
    )
    search_payload = BuscarAlimentoSustitutoRequest(
        current_food_name="Dates",
        current_food_code="dates",
        query="granola imposible",
    )
    preview_payload = ReplaceFoodRequest(
        current_food_name="Dates",
        current_food_code="dates",
        replacement_food_name="Granola Imposible",
        replacement_food_code="granola_imposible",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        return_value=granola_imposible,
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[granola_imposible],
    ):
        search_response = search_replacement_food(
            MagicMock(),
            user=_build_user(),
            diet_id="diet-1",
            meal_number=1,
            payload=search_payload,
        )

        assert search_response.candidates[0].valid is True
        assert search_response.candidates[0].macro_dominante == "carb"

        with pytest.raises(HTTPException) as excinfo:
            list_food_replacement_options(
                MagicMock(),
                user=_build_user(),
                diet_id="diet-1",
                meal_number=1,
                payload=preview_payload,
            )

    assert excinfo.value.status_code == 422
    assert "unable to fit meal exactly" not in excinfo.value.detail.lower()
    assert "granola imposible" in excinfo.value.detail.lower()


def test_si_el_alimento_buscado_no_es_valido_la_previsualizacion_devuelve_un_motivo_claro():
    context, _lookup = _build_context_dates_breakfast()
    payload = ReplaceFoodRequest(
        current_food_name="Dates",
        current_food_code="dates",
        replacement_food_name="Mixed Nuts",
        replacement_food_code="mixed_nuts",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        return_value=BREAKFAST_LOOKUP["mixed_nuts"],
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[BREAKFAST_LOOKUP["mixed_nuts"]],
    ):
        with pytest.raises(HTTPException) as excinfo:
            list_food_replacement_options(
                MagicMock(),
                user=_build_user(),
                diet_id="diet-1",
                meal_number=1,
                payload=payload,
            )

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail.startswith("No compatible:")
    assert "pertenece a grasas" in excinfo.value.detail.lower()


def test_al_sustituir_un_alimento_los_demas_siguen_siendo_los_mismos_y_solo_cambian_cantidades():
    context, _lookup = _build_context_dates_breakfast()
    initial_quantities = {
        food.food_code: float(food.quantity)
        for food in context["meal"].foods
        if food.food_code != "dates"
    }
    payload = ReplaceFoodRequest(
        current_food_name="Dates",
        current_food_code="dates",
        replacement_food_name="Cornflakes",
        replacement_food_code="cornflakes",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        side_effect=_resolver_desde_lookup(_lookup),
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[],
    ), patch(
        "app.services.food_substitution_service.persist_updated_meal_in_diet",
        side_effect=_persist_updated_meal,
    ):
        response = replace_food_in_meal(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    updated_meal = response.diet.meals[0]
    updated_codes = [food.food_code for food in updated_meal.foods]
    assert "dates" not in updated_codes
    assert "cornflakes" in updated_codes
    assert {"greek_yogurt", "oats", "avocado"}.issubset(set(updated_codes))

    updated_quantities = {
        food.food_code: float(food.quantity)
        for food in updated_meal.foods
        if food.food_code in initial_quantities
    }
    assert any(updated_quantities[food_code] != initial_quantities[food_code] for food_code in initial_quantities)


def test_la_comida_resultante_mantiene_una_aproximacion_razonable_a_macros_y_calorias():
    context, _lookup = _build_context_dates_breakfast()
    payload = ReplaceFoodRequest(
        current_food_name="Dates",
        current_food_code="dates",
        replacement_food_name="Cornflakes",
        replacement_food_code="cornflakes",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        side_effect=_resolver_desde_lookup(_lookup),
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[],
    ), patch(
        "app.services.food_substitution_service.persist_updated_meal_in_diet",
        side_effect=_persist_updated_meal,
    ):
        response = replace_food_in_meal(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    updated_meal = response.diet.meals[0]
    assert abs(float(updated_meal.calorie_difference)) <= 240.0
    assert abs(float(updated_meal.protein_difference)) <= 16.0
    assert abs(float(updated_meal.fat_difference)) <= 12.0
    assert abs(float(updated_meal.carb_difference)) <= 26.0


def test_restricciones_duras_siguen_respetandose():
    user = _build_user(allergies=["frutos secos"])
    context, _lookup = _build_context_peanut_butter_breakfast(user=user)
    payload = ReplaceFoodRequest(
        current_food_name="Peanut Butter",
        current_food_code="peanut_butter",
        replacement_food_name="Mixed Nuts",
        replacement_food_code="mixed_nuts",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        side_effect=_resolver_desde_lookup(_lookup),
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[],
    ):
        with pytest.raises(HTTPException) as excinfo:
            replace_food_in_meal(MagicMock(), user=user, diet_id="diet-1", meal_number=1, payload=payload)

    assert excinfo.value.status_code == 422
    assert "restricciones" in excinfo.value.detail.lower() or "permitido" in excinfo.value.detail.lower()


def test_si_el_alimento_no_se_puede_resolver_ni_localmente_ni_con_spoonacular_devuelve_error_claro():
    context, _lookup = _build_context_dates_breakfast()
    payload = ReplaceFoodRequest(
        current_food_name="Dates",
        current_food_code="dates",
        replacement_food_name="alimento inventado",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        return_value=None,
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[],
    ):
        with pytest.raises(HTTPException) as excinfo:
            replace_food_in_meal(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    assert excinfo.value.status_code == 404
    assert "no se pudo localizar" in excinfo.value.detail.lower()


def test_si_no_cuadra_perfecto_devuelve_la_mejor_aproximacion_razonable():
    context, lookup = _build_context_dates_breakfast()
    breakfast_light = _food(
        "granola_fixed",
        "cereales",
        protein=12.0,
        fat=16.0,
        carb=55.0,
        suitable_meals=["early"],
        name="Granola",
        default_qty=60.0,
        min_qty=60.0,
        max_qty=60.0,
        step=1.0,
    )
    lookup["granola_fixed"] = breakfast_light
    context["context_food_lookup"] = lookup
    context["meal_food_lookup"] = lookup
    payload = ReplaceFoodRequest(
        current_food_name="Dates",
        current_food_code="dates",
        replacement_food_name="Granola",
        replacement_food_code="granola_fixed",
    )

    with _PATCH_ML, _patched_context(context), patch(
        "app.services.food_substitution_service.find_food_by_code_or_name",
        side_effect=_resolver_desde_lookup(lookup),
    ), patch(
        "app.services.food_substitution_service.merge_internal_and_external_food_sources",
        return_value=[],
    ), patch(
        "app.services.food_substitution_service.persist_updated_meal_in_diet",
        side_effect=_persist_updated_meal,
    ):
        response = replace_food_in_meal(MagicMock(), user=_build_user(), diet_id="diet-1", meal_number=1, payload=payload)

    assert any("mejor aproximacion razonable" in note.lower() for note in response.summary.strategy_notes)
    updated_meal = response.diet.meals[0]
    assert abs(float(updated_meal.calorie_difference)) > 0 or abs(float(updated_meal.carb_difference)) > 0
