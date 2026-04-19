"""Tests del perfil de preferencias alimentarias del usuario."""

import pytest

from app.services.food_preferences_service import build_user_food_preferences_profile


def _user_con_preferencias(**kwargs):
    return {"food_preferences": kwargs}


def test_sin_preferencias_flags_false():
    profile = build_user_food_preferences_profile(_user_con_preferencias())
    assert profile["has_preferences"] is False
    assert profile["has_positive_preferences"] is False
    assert profile["has_negative_preferences"] is False


def test_solo_alimentos_preferidos():
    profile = build_user_food_preferences_profile(
        _user_con_preferencias(preferred_foods=["pollo", "arroz"])
    )
    assert profile["has_positive_preferences"] is True
    assert profile["has_negative_preferences"] is False
    assert profile["has_preferences"] is True


def test_solo_alimentos_no_deseados():
    profile = build_user_food_preferences_profile(
        _user_con_preferencias(disliked_foods=["cerdo"])
    )
    assert profile["has_positive_preferences"] is False
    assert profile["has_negative_preferences"] is True
    assert profile["has_preferences"] is True


def test_solo_restricciones_dieteticas():
    profile = build_user_food_preferences_profile(
        _user_con_preferencias(dietary_restrictions=["vegetariano"])
    )
    assert profile["has_positive_preferences"] is False
    assert profile["has_negative_preferences"] is True


def test_solo_alergias():
    profile = build_user_food_preferences_profile(
        _user_con_preferencias(allergies=["gluten"])
    )
    assert profile["has_positive_preferences"] is False
    assert profile["has_negative_preferences"] is True


def test_preferencias_positivas_y_negativas():
    profile = build_user_food_preferences_profile(
        _user_con_preferencias(
            preferred_foods=["avena"],
            disliked_foods=["cerdo"],
        )
    )
    assert profile["has_positive_preferences"] is True
    assert profile["has_negative_preferences"] is True
    assert profile["has_preferences"] is True


def test_lista_vacia_no_activa_flags():
    profile = build_user_food_preferences_profile(
        _user_con_preferencias(preferred_foods=[], disliked_foods=[])
    )
    assert profile["has_positive_preferences"] is False
    assert profile["has_negative_preferences"] is False


def test_preferred_foods_normalizados():
    profile = build_user_food_preferences_profile(
        _user_con_preferencias(preferred_foods=["POLLO", "Arroz"])
    )
    assert "pollo" in profile["preferred_foods"]
    assert "arroz" in profile["preferred_foods"]
