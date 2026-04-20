"""Regression tests for breakfast candidate ranking and support foods."""

from app.services.diet.candidates import (
    get_allowed_meal_slots_for_food,
    get_food_role_fit_score,
    get_support_candidate_foods,
    get_support_food_fit_score,
    sort_codes_by_meal_fit,
)


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
) -> dict:
    return {
        "code": code,
        "internal_code": None,
        "normalized_name": (name or code).lower(),
        "original_name": name or code,
        "display_name": name or code,
        "name": name or code,
        "category": category,
        "source": source,
        "origin_source": source,
        "reference_amount": 100.0,
        "reference_unit": "g",
        "grams_per_reference": 100.0,
        "calories": (protein * 4.0) + (fat * 9.0) + (carb * 4.0),
        "protein_grams": protein,
        "fat_grams": fat,
        "carb_grams": carb,
        "default_quantity": 40.0,
        "min_quantity": 10.0,
        "max_quantity": 160.0,
        "step": 5.0,
        "aliases": [name or code],
        "suitable_meals": suitable_meals,
    }


def _build_breakfast_fruit_lookup() -> dict[str, dict]:
    return {
        "spoonacular_dates_9087": _food(
            "spoonacular_dates_9087",
            "frutas",
            protein=2.5,
            fat=0.4,
            carb=75.0,
            suitable_meals=["early", "snack"],
            name="dates",
            source="spoonacular",
        ),
        "banana": _food(
            "banana",
            "frutas",
            protein=1.1,
            fat=0.3,
            carb=22.8,
            suitable_meals=["early", "snack"],
            name="Banana",
        ),
        "apple": _food(
            "apple",
            "frutas",
            protein=0.3,
            fat=0.2,
            carb=14.0,
            suitable_meals=["early", "snack"],
            name="Apple",
        ),
    }


def _build_breakfast_cereal_lookup() -> dict[str, dict]:
    return {
        **_build_breakfast_fruit_lookup(),
        "spoonacular_corn_cereal_8020": _food(
            "spoonacular_corn_cereal_8020",
            "carbohidratos",
            protein=7.5,
            fat=0.4,
            carb=84.1,
            suitable_meals=["main", "late"],
            name="corn cereal",
            source="spoonacular",
        ),
    }


def test_breakfast_cereal_tokens_override_wrong_cached_slots_and_beat_dates_as_main_carb():
    food_lookup = _build_breakfast_cereal_lookup()
    corn_cereal = food_lookup["spoonacular_corn_cereal_8020"]

    assert "early" in get_allowed_meal_slots_for_food(corn_cereal)

    ranked_codes = sort_codes_by_meal_fit(
        ["spoonacular_dates_9087", "spoonacular_corn_cereal_8020"],
        role="carb",
        meal_slot="early",
        meal_role="breakfast",
        training_focus=False,
        food_lookup=food_lookup,
    )
    corn_score = get_food_role_fit_score(
        corn_cereal,
        role="carb",
        meal_slot="early",
        meal_role="breakfast",
        training_focus=False,
    )
    dates_score = get_food_role_fit_score(
        food_lookup["spoonacular_dates_9087"],
        role="carb",
        meal_slot="early",
        meal_role="breakfast",
        training_focus=False,
    )

    assert corn_score > dates_score
    assert ranked_codes[0] == "spoonacular_corn_cereal_8020"


def test_breakfast_support_prefers_fresh_fruit_over_dates_when_other_options_exist():
    food_lookup = _build_breakfast_fruit_lookup()

    date_score = get_support_food_fit_score(
        food_lookup["spoonacular_dates_9087"],
        support_role="fruit",
        meal_slot="early",
        meal_role="breakfast",
        training_focus=False,
    )
    banana_score = get_support_food_fit_score(
        food_lookup["banana"],
        support_role="fruit",
        meal_slot="early",
        meal_role="breakfast",
        training_focus=False,
    )
    ranked_candidates = get_support_candidate_foods(
        food_lookup,
        support_role="fruit",
        meal_slot="early",
        meal_role="breakfast",
        training_focus=False,
    )

    assert banana_score > date_score
    assert ranked_candidates[0]["code"] == "banana"
    assert "spoonacular_dates_9087" in [candidate["code"] for candidate in ranked_candidates]


def test_dates_remain_available_when_they_are_the_only_breakfast_fruit_option():
    food_lookup = {
        "spoonacular_dates_9087": _build_breakfast_fruit_lookup()["spoonacular_dates_9087"],
    }

    ranked_candidates = get_support_candidate_foods(
        food_lookup,
        support_role="fruit",
        meal_slot="early",
        meal_role="breakfast",
        training_focus=False,
    )

    assert [candidate["code"] for candidate in ranked_candidates] == ["spoonacular_dates_9087"]
