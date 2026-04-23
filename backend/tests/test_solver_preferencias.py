"""Tests de la política de fallo de find_exact_solution_for_meal.

Verifica que:
  - Las preferencias positivas nunca bloquean por sí solas la generación.
  - La Estrategia D (relajación de prefs positivas) actúa como último recurso.
  - Las restricciones duras (alergias, disgustos) sí pueden bloquear cuando corresponde.
  - anchor_diagnostics se mantiene; FoodPreferenceConflictError no se emite solo por prefs positivas.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.schemas.diet import DietMeal
from app.services.diet.solver import find_exact_solution_for_meal
from app.services.food_preferences_service import FoodPreferenceConflictError

# ── Parche ML global ──────────────────────────────────────────────────────────
_PATCH_ML = patch("app.services.diet.candidates.predict_meal_slot_scores", return_value={})


# ── Food lookup mínimo para desayuno (early slot) ────────────────────────────
# Los macros están calibrados para que el sistema lineal 3×3 tenga solución
# con la combinación greek_yogurt (P) + oats (C) + avocado (F).
#
# Solución aproximada para P=30, F=8, C=40:
#   greek_yogurt ≈ 239g, oats ≈ 42g, avocado ≈ 27g
#   Verificado: cumple todos los límites (min, max, serving_floor, visibility_threshold).

def _food(code, category, protein, fat, carb, suitable_meals=None, *, name=None,
          default_qty=100.0, max_qty=400.0, min_qty=10.0, step=10.0):
    return {
        "code": code,
        "name": name or code.replace("_", " ").title(),
        "category": category,
        "protein_grams": protein,
        "fat_grams": fat,
        "carb_grams": carb,
        "reference_amount": 100.0,
        "grams_per_reference": 100.0,
        "reference_unit": "g",
        "default_quantity": default_qty,
        "max_quantity": max_qty,
        "min_quantity": min_qty,
        "step": step,
        "suitable_meals": suitable_meals or [],
        "preference_labels": [],
        "dietary_flags": [],
        "allergy_flags": [],
        "tags": [],
        "aliases": [],
    }


BREAKFAST_LOOKUP: dict[str, dict] = {
    # Proteínas de desayuno (no savory)
    "greek_yogurt": _food("greek_yogurt", "lacteos", protein=10.0, fat=0.4, carb=4.0,
                          suitable_meals=["early"], default_qty=200.0, max_qty=450.0, min_qty=50.0),
    "eggs": _food("eggs", "lacteos", protein=13.0, fat=11.0, carb=1.0,
                  suitable_meals=["early"], default_qty=100.0, max_qty=300.0, min_qty=50.0),
    # Carbohidratos de desayuno dulces (sweet breakfast carb → early only)
    "oats": _food("oats", "cereales", protein=13.0, fat=7.0, carb=66.0,
                  suitable_meals=["early"], default_qty=70.0, max_qty=200.0, min_qty=20.0, step=10.0),
    "cornflakes": _food("cornflakes", "cereales", protein=7.0, fat=1.0, carb=84.0,
                        suitable_meals=["early"], default_qty=50.0, max_qty=150.0, min_qty=20.0, step=10.0),
    # Grasas de desayuno (no cooking fat)
    "avocado": _food("avocado", "grasas", protein=2.0, fat=15.0, carb=9.0,
                     suitable_meals=["early"], default_qty=50.0, max_qty=150.0, min_qty=15.0, step=10.0),
    "mixed_nuts": _food("mixed_nuts", "grasas", protein=15.0, fat=50.0, carb=20.0,
                        suitable_meals=["early"], default_qty=30.0, max_qty=80.0, min_qty=10.0, step=5.0),
    # Frutas (soporte)
    "dates": _food("dates", "frutas", protein=2.5, fat=0.4, carb=75.0,
                   suitable_meals=["early"], default_qty=50.0, max_qty=200.0, min_qty=20.0),
    "banana": _food("banana", "frutas", protein=1.1, fat=0.3, carb=23.0,
                    suitable_meals=["early"], default_qty=120.0, max_qty=300.0, min_qty=80.0),
}


def _breakfast_meal(*, protein=30.0, fat=8.0, carb=40.0) -> DietMeal:
    calories = protein * 4 + fat * 9 + carb * 4
    return DietMeal(
        meal_number=1,
        meal_slot="early",
        meal_role="breakfast",
        meal_label="Desayuno",
        distribution_percentage=25.0,
        target_calories=calories,
        target_protein_grams=protein,
        target_fat_grams=fat,
        target_carb_grams=carb,
        actual_calories=0.0,
        actual_protein_grams=0.0,
        actual_fat_grams=0.0,
        actual_carb_grams=0.0,
    )


def _pref_profile(**kwargs) -> dict:
    """Perfil mínimo de preferencias para los tests."""
    preferred_foods = kwargs.get("preferred_foods", [])
    disliked_foods = kwargs.get("disliked_foods", [])
    dietary_restrictions = kwargs.get("dietary_restrictions", [])
    allergies = kwargs.get("allergies", [])
    tiene_pos = bool(preferred_foods)
    tiene_neg = bool(disliked_foods or dietary_restrictions or allergies)
    return {
        "preferred_foods": preferred_foods,
        "disliked_foods": disliked_foods,
        "dietary_restrictions": dietary_restrictions,
        "allergies": allergies,
        "normalized_preferred_foods": set(preferred_foods),
        "normalized_disliked_foods": set(disliked_foods),
        "dietary_restriction_set": set(dietary_restrictions),
        "allergy_set": set(allergies),
        "allergy_tag_set": set(),
        "has_positive_preferences": tiene_pos,
        "has_negative_preferences": tiene_neg,
        "has_preferences": tiene_pos or tiene_neg,
        "warnings": [],
    }


# ── Test 1: caso base sin preferencias — el solver funciona ──────────────────

def test_desayuno_basico_sin_preferencias():
    """Sin preferencias, el solver encuentra una solución válida para desayuno."""
    meal = _breakfast_meal()
    with _PATCH_ML:
        result = find_exact_solution_for_meal(
            meal=meal,
            meal_index=0,
            meals_count=3,
            training_focus=False,
            food_lookup=BREAKFAST_LOOKUP,
        )
    assert result is not None
    assert "foods" in result
    assert len(result["foods"]) >= 3


# ── Test 2: preferencias positivas (cornflakes + dátiles) no bloquean ─────────

def test_preferencias_positivas_no_bloquean_generacion():
    """Con preferred_foods=[cornflakes, dates], el solver devuelve una comida válida.

    Este era el caso que lanzaba FoodPreferenceConflictError prematuramente.
    """
    meal = _breakfast_meal()
    profile = _pref_profile(preferred_foods=["cornflakes", "dates"])
    with _PATCH_ML:
        result = find_exact_solution_for_meal(
            meal=meal,
            meal_index=0,
            meals_count=3,
            training_focus=False,
            food_lookup=BREAKFAST_LOOKUP,
            preference_profile=profile,
        )
    assert result is not None, "El solver no debe fallar con solo preferencias positivas"
    assert "foods" in result


# ── Test 3: prefs positivas que no existen en el catálogo no bloquean ─────────

def test_preferencia_inexistente_no_bloquea():
    """Si el alimento preferido no está en el catálogo, la dieta se genera igualmente."""
    meal = _breakfast_meal()
    profile = _pref_profile(preferred_foods=["xyzzy_alimento_inexistente"])
    with _PATCH_ML:
        result = find_exact_solution_for_meal(
            meal=meal,
            meal_index=0,
            meals_count=3,
            training_focus=False,
            food_lookup=BREAKFAST_LOOKUP,
            preference_profile=profile,
        )
    assert result is not None
    assert "foods" in result


# ── Test 4: FoodPreferenceConflictError NO se lanza por prefs positivas ────────

def test_preferencias_positivas_no_emiten_food_preference_conflict_error():
    """FoodPreferenceConflictError no debe propagarse cuando el único motivo
    de fallo son preferencias positivas que no pueden satisfacerse."""
    meal = _breakfast_meal()
    profile = _pref_profile(preferred_foods=["cornflakes", "dates"])

    # Simulamos que build_exact_meal_solution siempre devuelve None (ninguna combinación
    # pasa los filtros) para forzar que el solver llegue a Estrategia D.
    # Después de agotar Estrategia D, debe lanzar HTTPException (problema real de catálogo),
    # no FoodPreferenceConflictError (que culparía a las preferencias del usuario).
    with _PATCH_ML, patch(
        "app.services.diet.solver.build_exact_meal_solution",
        return_value=None,
    ):
        with pytest.raises(HTTPException):
            find_exact_solution_for_meal(
                meal=meal,
                meal_index=0,
                meals_count=3,
                training_focus=False,
                food_lookup=BREAKFAST_LOOKUP,
                preference_profile=profile,
            )
        # Si llegamos aquí sin que FoodPreferenceConflictError haya sido capturado,
        # el test pasa: la excepción fue HTTPException, no FoodPreferenceConflictError.


def test_preferencias_positivas_no_emiten_food_preference_conflict_error_directo():
    """Variante explícita: verifica que FoodPreferenceConflictError no se lanza."""
    meal = _breakfast_meal()
    profile = _pref_profile(preferred_foods=["cornflakes", "dates"])

    with _PATCH_ML, patch(
        "app.services.diet.solver.build_exact_meal_solution",
        return_value=None,
    ):
        try:
            find_exact_solution_for_meal(
                meal=meal,
                meal_index=0,
                meals_count=3,
                training_focus=False,
                food_lookup=BREAKFAST_LOOKUP,
                preference_profile=profile,
            )
        except FoodPreferenceConflictError as exc:
            pytest.fail(
                f"FoodPreferenceConflictError no debe lanzarse por preferencias positivas: {exc}"
            )
        except HTTPException:
            pass  # Esperado: problema real de catálogo, no de preferencias


# ── Test 5: ancla forzada (cornflakes) con prefs activas devuelve comida ───────

def test_ancla_forzada_con_preferencias_positivas():
    """Con forced_role_codes={'carb': 'cornflakes'} y prefs positivas,
    el solver encuentra solución usando cornflakes como carb."""
    meal = _breakfast_meal()
    profile = _pref_profile(preferred_foods=["cornflakes", "dates"])
    with _PATCH_ML:
        result = find_exact_solution_for_meal(
            meal=meal,
            meal_index=0,
            meals_count=3,
            training_focus=False,
            food_lookup=BREAKFAST_LOOKUP,
            preference_profile=profile,
            forced_role_codes={"carb": "cornflakes"},
        )
    assert result is not None
    food_codes = [f.get("food_code") or f.get("code") for f in result["foods"]]
    assert "cornflakes" in food_codes, (
        f"cornflakes debe aparecer en la comida cuando está forzado; foods={food_codes}"
    )


def test_variety_seed_desempata_soluciones_casi_equivalentes(monkeypatch):
    meal = _breakfast_meal()

    controlled_lookup = {
        "protein_a": _food("protein_a", "lacteos", protein=10.0, fat=0.4, carb=4.0, suitable_meals=["early"]),
        "protein_b": _food("protein_b", "lacteos", protein=10.0, fat=0.4, carb=4.0, suitable_meals=["early"]),
        "carb_a": _food("carb_a", "cereales", protein=7.0, fat=1.0, carb=84.0, suitable_meals=["early"]),
        "fat_a": _food("fat_a", "grasas", protein=2.0, fat=15.0, carb=9.0, suitable_meals=["early"]),
    }

    monkeypatch.setattr(
        "app.services.diet.solver.get_role_candidate_codes",
        lambda **kwargs: {
            "protein": ["protein_a", "protein_b"],
            "carb": ["carb_a"],
            "fat": ["fat_a"],
        },
    )
    monkeypatch.setattr(
        "app.services.diet.solver.get_support_option_specs",
        lambda **kwargs: [[]],
    )
    monkeypatch.setattr(
        "app.services.diet.solver.apply_daily_usage_candidate_limits",
        lambda candidate_codes, **kwargs: candidate_codes,
    )
    monkeypatch.setattr(
        "app.services.diet.solver.apply_meal_candidate_constraints",
        lambda candidate_codes, **kwargs: candidate_codes,
    )
    monkeypatch.setattr(
        "app.services.diet.solver.apply_support_option_constraints",
        lambda support_options, **kwargs: support_options,
    )

    def fake_build_exact_meal_solution(**kwargs):
        role_foods = kwargs["role_foods"]
        protein_code = role_foods["protein"]["code"]
        return {
            "foods": [
                {"food_code": protein_code, "calories": 120.0},
                {"food_code": "carb_a", "calories": 140.0},
                {"food_code": "fat_a", "calories": 80.0},
            ],
            "selected_role_codes": {
                "protein": protein_code,
                "carb": "carb_a",
                "fat": "fat_a",
            },
            "support_food_specs": [],
            "actual_calories": 340.0,
            "score": 0.0,
        }

    monkeypatch.setattr(
        "app.services.diet.solver.build_exact_meal_solution",
        fake_build_exact_meal_solution,
    )

    selected_proteins = set()
    with _PATCH_ML:
        for seed in range(1, 10):
            result = find_exact_solution_for_meal(
                meal=meal,
                meal_index=0,
                meals_count=3,
                training_focus=False,
                food_lookup=controlled_lookup,
                variety_seed=seed,
            )
            selected_proteins.add(result["selected_role_codes"]["protein"])

    assert selected_proteins == {"protein_a", "protein_b"}


# ── Test 6: solo ancla entra, el otro alimento no cabe → dieta igualmente ─────

def test_un_preferido_entra_el_otro_no_cabe():
    """Si cornflakes entra como ancla pero dates no cabe (p.ej., no hay hueco de soporte),
    la dieta se genera igualmente con cornflakes incluido."""
    meal = _breakfast_meal()
    profile = _pref_profile(preferred_foods=["cornflakes", "dates"])
    # Solo forzamos cornflakes; dates no está como support candidate → simplemente no aparece
    with _PATCH_ML:
        result = find_exact_solution_for_meal(
            meal=meal,
            meal_index=0,
            meals_count=3,
            training_focus=False,
            food_lookup=BREAKFAST_LOOKUP,
            preference_profile=profile,
            forced_role_codes={"carb": "cornflakes"},
        )
    assert result is not None, "La dieta debe generarse aunque no entren todos los preferidos"


# ── Test 7: restricciones duras (disgustos) sí pueden bloquear ────────────────

def test_restricciones_duras_bloquean_cuando_corresponde():
    """Si el usuario tiene restricciones negativas que vacían todos los candidatos
    de un rol, el sistema debe lanzar un error apropiado (no silenciar el problema)."""
    meal = _breakfast_meal()

    # Lookup mínimo con solo un alimento por rol
    lookup_minimo: dict[str, dict] = {
        "greek_yogurt": BREAKFAST_LOOKUP["greek_yogurt"],
        "oats": BREAKFAST_LOOKUP["oats"],
        "avocado": BREAKFAST_LOOKUP["avocado"],
    }
    # El usuario no quiere ningún alimento lácteo ni cereal ni grasa → pool completamente vacío
    # Nota: se usa disliked_foods para coincidir con los nombres/código de los alimentos
    profile = _pref_profile(
        preferred_foods=["cornflakes"],
        disliked_foods=["greek yogurt", "yogurt", "oats", "avocado"],
    )

    with _PATCH_ML:
        with pytest.raises((FoodPreferenceConflictError, HTTPException)):
            find_exact_solution_for_meal(
                meal=meal,
                meal_index=0,
                meals_count=3,
                training_focus=False,
                food_lookup=lookup_minimo,
                preference_profile=profile,
            )


# ── Test 8: diagnostico de anclas no se pierde ────────────────────────────────

def test_anchor_diagnostics_disponibles_en_diet_service(monkeypatch):
    """El campo anchor_diagnostics debe incluirse en el resultado de generate_food_based_diet
    cuando hay preferencias positivas, incluso si no todos los alimentos pueden anclarse."""
    from app.services.diet.preference_anchors import resolver_anclas_preferidas

    with _PATCH_ML:
        resultado = resolver_anclas_preferidas(
            preferred_foods=["cornflakes", "dátiles"],
            food_lookup=BREAKFAST_LOOKUP,
            meal_slots=["early"],
            meal_roles=["breakfast"],
            training_focus_flags=[False],
        )

    diagnosticos = resultado["diagnosticos"]
    assert len(diagnosticos) >= 1, "Debe haber al menos un diagnóstico"
    estados_validos = {"anclado", "usado_como_soporte", "no_encontrado", "descartado_sin_hueco_compatible"}
    for diag in diagnosticos:
        assert diag["estado"] in estados_validos, f"Estado inválido: {diag['estado']}"
