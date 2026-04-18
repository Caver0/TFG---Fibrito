"""Constantes compartidas por la logica de dietas."""

DEFAULT_FOOD_DATA_SOURCE = "internal"
CACHE_FOOD_DATA_SOURCE = "cache"
SPOONACULAR_FOOD_DATA_SOURCE = "spoonacular"
CATALOG_SOURCE_STRATEGY_DEFAULT = "internal_catalog_with_optional_spoonacular_enrichment"
DIET_SOURCE_MAP = {
    "internal_catalog": DEFAULT_FOOD_DATA_SOURCE,
    "local_cache": CACHE_FOOD_DATA_SOURCE,
    "spoonacular": SPOONACULAR_FOOD_DATA_SOURCE,
    DEFAULT_FOOD_DATA_SOURCE: DEFAULT_FOOD_DATA_SOURCE,
    CACHE_FOOD_DATA_SOURCE: CACHE_FOOD_DATA_SOURCE,
    SPOONACULAR_FOOD_DATA_SOURCE: SPOONACULAR_FOOD_DATA_SOURCE,
}
EXACT_SOLVER_TOLERANCE = 1e-6
FOOD_VALUE_PRECISION = 2
FOOD_OMIT_THRESHOLD = {
    "g": 0.5,
    "ml": 1.0,
    "unidad": 0.05,
}
SOFT_ROLE_MINIMUMS = {
    "protein": {"g": 55.0, "ml": 125.0, "unidad": 0.5},
    "carb": {"g": 15.0, "ml": 50.0, "unidad": 0.2},
    "fat": {"g": 3.0, "ml": 3.0, "unidad": 0.1},
}
ROLE_DISPLAY_ORDER = {
    "protein": 0,
    "carb": 1,
    "fruit": 2,
    "vegetable": 3,
    "dairy": 4,
    "fat": 5,
}
ROLE_LABELS = {
    "protein": "proteina",
    "carb": "carbohidrato",
    "fat": "grasa",
}
ROLE_FALLBACK_CODE_POOLS = {
    "protein": [
        "chicken_breast",
        "turkey_breast",
        "tuna",
        "egg_whites",
        "greek_yogurt",
        "eggs",
    ],
    "carb": [
        "rice",
        "potato",
        "pasta",
        "whole_wheat_bread",
        "banana",
        "oats",
    ],
    "fat": ["olive_oil", "avocado", "mixed_nuts"],
}
CORE_MACRO_KEYS = ("protein_grams", "fat_grams", "carb_grams")
MACRO_CALORIE_FACTORS = {
    "protein_grams": 4.0,
    "fat_grams": 9.0,
    "carb_grams": 4.0,
}
CANDIDATE_INDEX_WEIGHT = 0.08
# Este bonus debe ser mayor que CANDIDATE_INDEX_WEIGHT * profundidad tipica
# para que un alimento preferido gane frente a uno no preferido.
PREFERRED_FOOD_BONUS_BY_ROLE = {
    "protein": 1.20,
    "carb": 0.95,
    "fat": 0.45,
    "fruit": 0.55,
    "vegetable": 0.45,
    "dairy": 0.70,
}
REPEAT_PENALTY_BY_ROLE = {
    "protein": 0.85,
    "carb": 0.72,
    "fat": 0.28,
    "fruit": 0.18,
    "vegetable": 0.12,
    "dairy": 0.24,
}
REPEAT_ESCALATION_BY_ROLE = {
    "protein": 0.75,
    "carb": 0.55,
    "fat": 0.18,
    "fruit": 0.12,
    "vegetable": 0.08,
    "dairy": 0.18,
}
REPEATED_MAIN_PAIR_PENALTY = 0.5
WEEKLY_REPEAT_PENALTY_BY_ROLE = {
    "protein": 0.12,
    "carb": 0.08,
    "fat": 0.0,
    "fruit": 0.04,
    "vegetable": 0.02,
    "dairy": 0.06,
}
WEEKLY_DIVERSITY_WINDOW_DAYS = 6
DEFAULT_PROTEIN_ROLE_DAILY_MAX_USAGE = 1
PROTEIN_ROLE_DAILY_MAX_USAGE_BY_CODE = {
    "egg_whites": 1,
    "eggs": 1,
    "greek_yogurt": 2,
}
SWEET_BREAKFAST_CARB_TOKENS = (
    "avena",
    "oats",
    "muesli",
    "granola",
    "cereal",
    "cornflakes",
    "flakes",
    "porridge",
)
SAVORY_STARCH_TOKENS = (
    "arroz",
    "rice",
    "pasta",
    "patata",
    "potato",
    "quinoa",
    "couscous",
    "boniato",
    "batata",
    "lentil",
    "lenteja",
    "garbanzo",
    "chickpea",
    "judia",
    "bean",
    "tortilla",
)
SAVORY_PROTEIN_TOKENS = (
    "chicken",
    "pollo",
    "turkey",
    "pavo",
    "tuna",
    "atun",
    "beef",
    "ternera",
    "pork",
    "cerdo",
    "salmon",
    "merluza",
    "bacalao",
    "fish",
    "gamba",
    "shrimp",
    "prawn",
    "marisco",
    "sepia",
    "sausage",
    "salchicha",
)
BREAKFAST_PROTEIN_TOKENS = (
    "egg",
    "huevo",
    "claras",
    "yogur",
    "yogurt",
    "cottage",
    "skyr",
    "quark",
)
BREAKFAST_ONLY_DAIRY_TOKENS = (
    "yogur",
    "yogurt",
    "cottage",
    "skyr",
    "quark",
    "leche",
    "milk",
)
BREAKFAST_FAT_TOKENS = (
    "almendra",
    "almond",
    "nueces",
    "walnut",
    "peanut",
    "cacahuete",
    "chia",
    "lino",
    "flax",
    "seed",
)
COOKING_FAT_TOKENS = ("aceite", "olive oil", "oil")
BREAKFAST_BREAD_TOKENS = ("pan", "bread", "toast", "tostada")
VALID_MEAL_SLOTS = {"early", "main", "late"}
VALID_MEAL_ROLES = {"meal", "breakfast", "pre_workout", "post_workout", "dinner", "training_focus"}
LOW_FAT_MEAL_ROLES = {"pre_workout", "post_workout", "training_focus"}
MAX_ROLE_CANDIDATES_PER_MEAL = {
    "protein": 10,
    "carb": 10,
    "fat": 8,
}
MAX_SUPPORT_CANDIDATES_PER_ROLE = 3
LEAN_PROTEIN_CODES = {"chicken_breast", "turkey_breast", "tuna", "egg_whites", "greek_yogurt"}
FAST_DIGESTING_CARB_CODES = {"rice", "potato", "pasta", "oats", "banana", "whole_wheat_bread"}
EARLY_SWEET_FAT_CODES = {"mixed_nuts"}
SAVORY_FAT_CODES = {"olive_oil", "avocado"}
