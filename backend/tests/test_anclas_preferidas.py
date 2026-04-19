"""Tests de regresión para el sistema de anclaje de alimentos preferidos."""

from unittest.mock import patch

import pytest

from app.services.diet.preference_anchors import resolver_anclas_preferidas

# ── Helpers para construir alimentos de prueba ────────────────────────────────

def _food(code, category, protein=0.0, carb=0.0, fat=0.0, suitable_meals=None, name=None):
    return {
        "code": code,
        "name": name or code,
        "category": category,
        "protein_grams": protein,
        "carb_grams": carb,
        "fat_grams": fat,
        "reference_amount": 100.0,
        "grams_per_reference": 100.0,
        "reference_unit": "g",
        "default_quantity": 100.0,
        "suitable_meals": suitable_meals or [],
        "preference_labels": [],
        "dietary_flags": [],
        "allergy_flags": [],
        "tags": [],
    }


LOOKUP_BASE: dict[str, dict] = {
    "cornflakes": _food(
        "cornflakes", "cereales",
        protein=7.0, carb=84.0, fat=1.0,
        suitable_meals=["early"],
        name="Cornflakes",
    ),
    "dates": _food(
        "dates", "frutas",
        protein=2.5, carb=75.0, fat=0.4,
        suitable_meals=["early"],
        name="Dates",
    ),
    "oats": _food(
        "oats", "cereales",
        protein=13.0, carb=66.0, fat=7.0,
        suitable_meals=["early"],
        name="Oats",
    ),
    "greek_yogurt": _food(
        "greek_yogurt", "lacteos",
        protein=10.0, carb=4.0, fat=0.4,
        suitable_meals=["early"],
        name="Greek Yogurt",
    ),
    "banana": _food(
        "banana", "frutas",
        protein=1.1, carb=23.0, fat=0.3,
        suitable_meals=["early"],
        name="Banana",
    ),
    "chicken_breast": _food(
        "chicken_breast", "proteinas",
        protein=31.0, carb=0.0, fat=3.6,
        suitable_meals=["main", "late"],
        name="Chicken Breast",
    ),
    "rice": _food(
        "rice", "carbohidratos",
        protein=2.7, carb=28.0, fat=0.3,
        suitable_meals=["main", "late"],
        name="Rice",
    ),
}

# Parche global para evitar la dependencia del clasificador ML
_PATCH_ML = patch(
    "app.services.diet.candidates.predict_meal_slot_scores",
    return_value={},
)


# ── Caso 1: traducción al vuelo (dátiles → dates) ────────────────────────────

def test_datiles_se_traduce_y_encuentra():
    """buscar_alimentos_por_nombre debe encontrar 'dates' usando el texto 'dátiles'."""
    with _PATCH_ML:
        resultado = resolver_anclas_preferidas(
            preferred_foods=["dátiles"],
            food_lookup=LOOKUP_BASE,
            meal_slots=["early"],
            meal_roles=["breakfast"],
            training_focus_flags=[False],
        )
    diagnosticos = resultado["diagnosticos"]
    assert len(diagnosticos) == 1
    diag = diagnosticos[0]
    assert diag["estado"] != "no_encontrado", (
        f"'dátiles' no fue encontrado en el catálogo. Diagnóstico: {diag}"
    )


# ── Caso 2: ancla + soporte (cornflakes + dátiles) ───────────────────────────

def test_cornflakes_ancla_datiles_soporte():
    """cornflakes debe anclar como carb y dátiles caer como soporte fruit."""
    with _PATCH_ML:
        resultado = resolver_anclas_preferidas(
            preferred_foods=["cornflakes", "dátiles"],
            food_lookup=LOOKUP_BASE,
            meal_slots=["early"],
            meal_roles=["breakfast"],
            training_focus_flags=[False],
        )

    anclas = resultado["anclas"]
    soporte = resultado["soporte"]
    diagnosticos = resultado["diagnosticos"]

    estados = {d["preferido"]: d["estado"] for d in diagnosticos}

    assert estados.get("cornflakes") == "anclado", f"cornflakes: {estados.get('cornflakes')}"
    assert "carb" in anclas.get(0, {}), f"anclas[0]: {anclas.get(0)}"
    assert anclas[0]["carb"] == "cornflakes"

    estado_datiles = estados.get("dátiles")
    assert estado_datiles in ("anclado", "usado_como_soporte"), (
        f"dátiles debe quedar anclado o como soporte, pero fue: {estado_datiles}"
    )


# ── Caso 3: desayuno coherente yogur + avena + banana ───────────────────────

def test_yogur_avena_banana_desayuno():
    """greek_yogurt → protein, oats → carb, banana → soporte fruit."""
    with _PATCH_ML:
        resultado = resolver_anclas_preferidas(
            preferred_foods=["yogur", "avena", "banana"],
            food_lookup=LOOKUP_BASE,
            meal_slots=["early"],
            meal_roles=["breakfast"],
            training_focus_flags=[False],
        )

    anclas = resultado["anclas"].get(0, {})
    soporte = resultado["soporte"].get(0, [])
    diagnosticos = resultado["diagnosticos"]
    estados = {d["preferido"]: d["estado"] for d in diagnosticos}

    assert estados.get("yogur") in ("anclado", "usado_como_soporte"), (
        f"yogur: {estados.get('yogur')}"
    )
    assert estados.get("avena") in ("anclado", "usado_como_soporte"), (
        f"avena: {estados.get('avena')}"
    )
    assert estados.get("banana") in ("anclado", "usado_como_soporte"), (
        f"banana: {estados.get('banana')}"
    )


# ── Caso 4: comida principal clásica (pollo + arroz) ─────────────────────────

def test_pollo_arroz_comida_principal():
    """chicken_breast → protein, rice → carb en slot main."""
    with _PATCH_ML:
        resultado = resolver_anclas_preferidas(
            preferred_foods=["pollo", "arroz"],
            food_lookup=LOOKUP_BASE,
            meal_slots=["main"],
            meal_roles=["meal"],
            training_focus_flags=[False],
        )

    anclas = resultado["anclas"].get(0, {})
    diagnosticos = resultado["diagnosticos"]
    estados = {d["preferido"]: d["estado"] for d in diagnosticos}

    assert estados.get("pollo") == "anclado", f"pollo: {estados.get('pollo')}"
    assert estados.get("arroz") == "anclado", f"arroz: {estados.get('arroz')}"
    assert anclas.get("protein") == "chicken_breast"
    assert anclas.get("carb") == "rice"


# ── Caso 5: solo preferencias negativas no generan anclas ────────────────────

def test_sin_preferencias_positivas_no_genera_anclas():
    """Con preferred_foods vacío, el resultado debe tener anclas y soporte vacíos."""
    with _PATCH_ML:
        resultado = resolver_anclas_preferidas(
            preferred_foods=[],
            food_lookup=LOOKUP_BASE,
            meal_slots=["early", "main"],
            meal_roles=["breakfast", "meal"],
            training_focus_flags=[False, False],
        )

    assert resultado["anclas"] == {}
    assert resultado["soporte"] == {}
    assert resultado["diagnosticos"] == []


# ── Caso 6: alimento no encontrado ───────────────────────────────────────────

def test_alimento_no_encontrado():
    """Un alimento sin coincidencia en el catálogo debe reportarse como no_encontrado."""
    with _PATCH_ML:
        resultado = resolver_anclas_preferidas(
            preferred_foods=["xyzzy_alimento_inexistente"],
            food_lookup=LOOKUP_BASE,
            meal_slots=["early"],
            meal_roles=["breakfast"],
            training_focus_flags=[False],
        )

    diagnosticos = resultado["diagnosticos"]
    assert len(diagnosticos) == 1
    assert diagnosticos[0]["estado"] == "no_encontrado"
    assert resultado["anclas"] == {}
    assert resultado["soporte"] == {}
