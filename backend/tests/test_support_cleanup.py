"""Tests de limpieza para soportes y cantidades residuales."""

from unittest.mock import patch

from app.services.diet.candidates import get_support_option_specs
from app.services.diet.solver import find_exact_solution_for_meal
from tests.test_solver_preferencias import BREAKFAST_LOOKUP, _breakfast_meal, _pref_profile

_PATCH_ML = patch("app.services.diet.candidates.predict_meal_slot_scores", return_value={})


def test_soporte_fruta_en_gramos_no_usa_cantidad_residual():
    """Una fruta medida en gramos no debe generar soportes de 0.5 g o 1 g."""
    meal = _breakfast_meal()
    lookup = {
        "banana_g": {
            **BREAKFAST_LOOKUP["banana"],
            "code": "banana_g",
            "reference_unit": "g",
            "default_quantity": 120.0,
        },
        "greek_yogurt": BREAKFAST_LOOKUP["greek_yogurt"],
    }

    with _PATCH_ML:
        support_options = get_support_option_specs(
            meal=meal,
            meal_index=0,
            meals_count=3,
            training_focus=False,
            food_lookup=lookup,
        )

    fruit_options = [
        option[0]
        for option in support_options
        if option and option[0]["role"] == "fruit"
    ]
    assert fruit_options, "Debe existir al menos una opcion de fruta en el desayuno"
    assert fruit_options[0]["quantity"] >= 10.0, fruit_options[0]


def test_desayuno_basico_no_anade_soporte_residual_por_defecto():
    """Sin preferencias, un desayuno resoluble no debe meter fruta residual como soporte."""
    meal = _breakfast_meal()
    with _PATCH_ML:
        result = find_exact_solution_for_meal(
            meal=meal,
            meal_index=0,
            meals_count=3,
            training_focus=False,
            food_lookup=BREAKFAST_LOOKUP,
        )

    assert result["support_food_specs"] == []
    assert all(
        not (food["food_code"] == "banana" and float(food["quantity"]) <= 1.0)
        for food in result["foods"]
    ), result["foods"]


def test_cornflakes_y_dates_pueden_convivir_como_ancla_y_soporte():
    """Cornflakes y dates deben seguir pudiendo entrar juntos cuando son preferidos."""
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

    food_codes = [food.get("food_code") or food.get("code") for food in result["foods"]]
    assert "cornflakes" in food_codes, food_codes
    assert "dates" in food_codes, food_codes
    assert result["support_food_specs"][0]["food_code"] == "dates"
    assert result["support_food_specs"][0]["role"] == "fruit"
    assert result["support_food_specs"][0]["quantity"] >= 10.0
