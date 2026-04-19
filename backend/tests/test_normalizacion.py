"""Tests de normalización y traducción de nombres de alimentos."""

import pytest

from app.utils.normalization import normalize_food_name, translate_food_query_for_search


@pytest.mark.parametrize("entrada,esperado", [
    ("dátiles", "dates"),
    ("DÁTILES", "dates"),
    ("plátano", "banana"),
    ("Plátano", "banana"),
    ("atún", "tuna"),
    ("pechuga de pollo", "chicken breast"),
    ("copos de maíz", "cornflakes"),
    ("avena", "oats"),
    ("arroz", "rice"),
    ("yogur", "yogurt"),
])
def test_translate_food_query_espanol(entrada, esperado):
    assert translate_food_query_for_search(entrada) == esperado


def test_translate_food_query_ingles_sin_cambio():
    assert translate_food_query_for_search("chicken breast") == "chicken breast"


def test_translate_food_query_cadena_vacia():
    result = translate_food_query_for_search("")
    assert result == ""


def test_normalize_food_name_elimina_tildes():
    assert normalize_food_name("dátiles") == "datiles"


def test_normalize_food_name_minusculas():
    assert normalize_food_name("POLLO") == "pollo"


def test_normalize_food_name_cadena_vacia():
    assert normalize_food_name("") == ""
