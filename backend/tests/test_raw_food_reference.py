from app.schemas.diet import serialize_diet_food
from app.services.food_catalog_service import _serialize_cached_food, get_internal_food_lookup
from app.utils.normalization import normalize_food_to_raw_reference


def test_normalize_food_to_raw_reference_removes_cooking_variants():
    assert normalize_food_to_raw_reference("Pechuga de pollo cocida") == "Pechuga de pollo"
    assert normalize_food_to_raw_reference("Arroz blanco cocido") == "Arroz"
    assert normalize_food_to_raw_reference("Salmon al horno") == "Salmon"


def test_internal_catalog_core_carbs_use_raw_references():
    lookup = get_internal_food_lookup()

    assert lookup["rice"]["name"] == "Arroz"
    assert lookup["rice"]["calories"] == 365.0
    assert lookup["pasta"]["name"] == "Pasta"
    assert lookup["pasta"]["carb_grams"] == 74.7
    assert lookup["potato"]["name"] == "Patata"
    assert lookup["potato"]["carb_grams"] == 17.5


def test_cached_food_matching_internal_reference_is_reanchored_to_raw_catalog():
    lookup = get_internal_food_lookup()
    cached_document = {
        "code": "spoonacular_white_rice_cooked_1",
        "internal_code": "rice",
        "normalized_name": "arroz cocido",
        "original_name": "Arroz cocido",
        "display_name": "Arroz cocido",
        "name": "Arroz cocido",
        "category": "carbohidratos",
        "source": "spoonacular",
        "origin_source": "spoonacular",
        "spoonacular_id": 1,
        "reference_amount": 100.0,
        "reference_unit": "g",
        "grams_per_reference": 100.0,
        "calories": 130.0,
        "protein_grams": 2.7,
        "fat_grams": 0.3,
        "carb_grams": 28.0,
        "default_quantity": 150.0,
        "min_quantity": 60.0,
        "max_quantity": 900.0,
        "step": 10.0,
        "aliases": ["arroz cocido", "cooked rice"],
        "suitable_meals": ["main"],
    }

    serialized = _serialize_cached_food(cached_document)

    assert serialized["name"] == "Arroz"
    assert serialized["internal_code"] == "rice"
    assert serialized["calories"] == lookup["rice"]["calories"]
    assert serialized["carb_grams"] == lookup["rice"]["carb_grams"]


def test_serialize_diet_food_shows_raw_name_for_legacy_cooked_food():
    serialized_food = serialize_diet_food({
        "food_code": "white_rice_cooked",
        "source": "internal_catalog",
        "origin_source": "internal_catalog",
        "name": "Arroz blanco cocido",
        "category": "carbohidratos",
        "quantity": 250.0,
        "unit": "g",
        "grams": 250.0,
        "calories": 325.0,
        "protein_grams": 6.0,
        "fat_grams": 0.5,
        "carb_grams": 71.8,
    })

    assert serialized_food.name == "Arroz"
