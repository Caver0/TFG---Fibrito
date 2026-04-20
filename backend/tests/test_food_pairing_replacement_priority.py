from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.schemas.diet import DietFood, FoodReplacementOption, ReplaceFoodRequest
from app.schemas.user import FoodPreferencesProfile, UserPublic
from app.services.food_substitution_service import list_food_replacement_options


def _food(
    code: str,
    category: str,
    *,
    protein: float,
    fat: float,
    carb: float,
    name: str,
    aliases: list[str],
) -> dict:
    return {
        "code": code,
        "name": name,
        "display_name": name,
        "original_name": name,
        "normalized_name": name.lower(),
        "category": category,
        "source": "internal_catalog",
        "origin_source": "internal_catalog",
        "protein_grams": protein,
        "fat_grams": fat,
        "carb_grams": carb,
        "calories": protein * 4 + fat * 9 + carb * 4,
        "reference_amount": 100.0,
        "reference_unit": "g",
        "grams_per_reference": 100.0,
        "default_quantity": 100.0,
        "max_quantity": 400.0,
        "min_quantity": 10.0,
        "step": 5.0,
        "suitable_meals": ["early", "snack", "main"],
        "aliases": aliases,
        "dietary_tags": [],
        "allergen_tags": [],
        "compatibility_notes": [],
    }


def _build_user() -> UserPublic:
    return UserPublic(
        id="user-1",
        name="Jorge",
        email="jorge@example.com",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        food_preferences=FoodPreferencesProfile(),
    )


def _build_option(candidate_food: dict, *, strategy: str = "strict") -> FoodReplacementOption:
    return FoodReplacementOption(
        food_code=str(candidate_food["code"]),
        name=str(candidate_food["name"]),
        category=str(candidate_food["category"]),
        functional_group="protein",
        source="internal_catalog",
        recommended_quantity=100.0,
        recommended_unit="g",
        recommended_grams=100.0,
        calories=float(candidate_food["calories"]),
        protein_grams=float(candidate_food["protein_grams"]),
        fat_grams=float(candidate_food["fat_grams"]),
        carb_grams=float(candidate_food["carb_grams"]),
        meal_calorie_difference=0.0,
        meal_protein_difference=0.0,
        meal_fat_difference=0.0,
        meal_carb_difference=0.0,
        strategy=strategy,
        note=None,
        macro_dominante="protein",
        equivalent_grams=100.0,
    )


def test_preferred_pairing_candidates_are_ranked_before_other_valid_replacements():
    cornflakes = _food("cornflakes", "cereales", protein=7.0, fat=1.0, carb=84.0, name="Cornflakes", aliases=["cornflakes", "cereales"])
    chicken = _food("chicken_breast", "proteinas", protein=23.0, fat=2.0, carb=0.0, name="Chicken Breast", aliases=["pollo", "chicken breast"])
    greek_yogurt = _food("greek_yogurt", "lacteos", protein=12.0, fat=0.5, carb=6.0, name="Greek Yogurt", aliases=["yogur", "yogur griego", "greek yogurt"])
    turkey = _food("turkey_breast", "proteinas", protein=24.0, fat=1.5, carb=0.0, name="Turkey Breast", aliases=["pavo", "turkey breast"])
    avocado = _food("avocado", "grasas", protein=2.0, fat=15.0, carb=9.0, name="Avocado", aliases=["aguacate", "avocado"])
    lookup = {
        food["code"]: food
        for food in (cornflakes, chicken, greek_yogurt, turkey, avocado)
    }

    context = {
        "current_food": DietFood.model_validate(
            {
                "food_code": "chicken_breast",
                "source": "internal_catalog",
                "origin_source": "internal_catalog",
                "name": "Chicken Breast",
                "category": "proteinas",
                "quantity": 120.0,
                "unit": "g",
                "grams": 120.0,
                "calories": chicken["calories"] * 1.2,
                "protein_grams": chicken["protein_grams"] * 1.2,
                "fat_grams": chicken["fat_grams"] * 1.2,
                "carb_grams": chicken["carb_grams"] * 1.2,
            }
        ),
        "current_food_entry": chicken,
        "context_food_lookup": lookup,
        "meal_food_lookup": lookup,
        "meal_slot": "early",
        "meal_role": "breakfast",
        "training_focus": False,
        "current_macro_dominante": "protein",
        "meal_food_codes": {"cornflakes", "chicken_breast", "avocado"},
        "inferred_plan": {
            "selected_role_codes": {
                "protein": "chicken_breast",
                "carb": "cornflakes",
                "fat": "avocado",
            },
            "support_food_specs": [],
        },
    }
    payload = ReplaceFoodRequest(current_food_name="Chicken Breast", current_food_code="chicken_breast")

    def _evaluate(candidate_food, *, context):
        del context
        if candidate_food["code"] == "turkey_breast":
            return 0.1, _build_option(candidate_food)
        return 1.4, _build_option(candidate_food)

    with patch(
        "app.services.food_substitution_service._build_food_replacement_context",
        return_value=context,
    ), patch(
        "app.services.food_substitution_service._find_replacement_candidates_with_fallback",
        return_value=[turkey, greek_yogurt],
    ), patch(
        "app.services.food_substitution_service._evaluate_candidate_for_context",
        side_effect=_evaluate,
    ):
        response = list_food_replacement_options(
            MagicMock(),
            user=_build_user(),
            diet_id="diet-1",
            meal_number=1,
            payload=payload,
        )

    assert [option.food_code for option in response.options[:2]] == ["greek_yogurt", "turkey_breast"]
