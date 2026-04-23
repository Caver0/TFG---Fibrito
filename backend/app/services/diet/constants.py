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
NEAR_BEST_SELECTION_WINDOW_BY_SLOT = {
    "early": 1.55,
    "main": 0.9,
    "late": 0.9,
}
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
FAMILY_REPEAT_PENALTY_BY_ROLE = {
    "protein": 0.45,
    "carb": 0.35,
    "fat": 0.14,
    "fruit": 0.12,
    "vegetable": 0.08,
    "dairy": 0.16,
}
REPEATED_MAIN_PAIR_PENALTY = 0.5
REPEATED_MAIN_FAMILY_PAIR_PENALTY = 0.85
REPEATED_MEAL_STRUCTURE_PENALTY = 1.15
REPEATED_TEMPLATE_PENALTY = 1.75
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
    "carb": 12,
    "fat": 8,
}
MAX_SUPPORT_CANDIDATES_PER_ROLE = 3
LEAN_PROTEIN_CODES = {"chicken_breast", "turkey_breast", "tuna", "egg_whites", "greek_yogurt"}
FAST_DIGESTING_CARB_CODES = {"rice", "potato", "pasta", "oats", "banana", "whole_wheat_bread"}
EARLY_SWEET_FAT_CODES = {"mixed_nuts"}
SAVORY_FAT_CODES = {"olive_oil", "avocado"}

# Límites de cantidad dinámicos: la cantidad máxima permitida para un alimento es
# N veces el objetivo macro que ese rol debe cubrir en la comida. Así el límite escala
# con el peso corporal del usuario (vía sus objetivos nutricionales) en lugar de ser fijo.
ROLE_QUANTITY_TARGET_MULTIPLIER = 2.0
# Multiplicador más conservador para frutas como carbohidrato: su densidad en hidratos
# es baja y no es razonable que suplan toda la cuota de carbohidratos de la comida.
FRUIT_CARB_TARGET_MULTIPLIER = 1.5

# Techo de seguridad absoluto como última red: se activa solo si la densidad del alimento
# es tan baja que el límite dinámico resultaría en una cantidad físicamente imposible.
ROLE_QUANTITY_SAFETY_CEILING_G = {
    "protein": 450.0,
    "carb": 350.0,
    "fat": 150.0,
}

# Límite absoluto para frutas como carbohidrato principal: incluso para usuarios grandes,
# una fruta no debe suplir más de ~200 g en una comida; el solver elegirá almidones si
# los objetivos de carbohidratos son altos.
CARB_FRUIT_MAX_QUANTITY_UNIDAD = 3.0
CARB_FRUIT_MAX_QUANTITY_G = 200.0
# Tope fijo para aceites y grasas de cocina: su uso es culinario, no proporcional al peso.
FAT_OIL_MAX_QUANTITY_G = 25.0

BONUS_CORRELACION_ALIMENTARIA = 0.18

# Pares de alimentos que combinan bien culinariamente. La clave es el código de uno de los
# alimentos; el valor es la lista de códigos con los que armoniza bien.
# Se aplica como bonus negativo en build_solution_score (menor score = mejor candidato).
CORRELACIONES_ALIMENTOS_COMPATIBLES: dict[str, list[str]] = {
    "cornflakes": ["greek_yogurt", "milk", "oats"],
    "oats": ["greek_yogurt", "milk", "banana", "mixed_nuts"],
    "muesli": ["greek_yogurt", "milk", "banana"],
    "granola": ["greek_yogurt", "milk"],
    "rice": ["chicken_breast", "turkey_breast", "tuna", "eggs"],
    "pasta": ["chicken_breast", "turkey_breast", "tuna"],
    "potato": ["chicken_breast", "salmon", "eggs"],
    "whole_wheat_bread": ["eggs", "turkey_breast", "avocado"],
    "banana": ["oats", "greek_yogurt"],
    "chicken_breast": ["rice", "potato", "pasta"],
    "turkey_breast": ["rice", "pasta", "whole_wheat_bread"],
    "tuna": ["rice", "pasta", "potato"],
    "salmon": ["potato", "rice"],
    "eggs": ["whole_wheat_bread", "potato", "rice"],
    "greek_yogurt": ["oats", "cornflakes", "banana", "muesli", "granola"],
}

# Equivalencias semánticas conocidas entre alimentos con distintos nombres o idiomas.
# Evita seleccionar el mismo alimento dos veces en la misma comida con códigos distintos.
FOOD_SEMANTIC_EQUIVALENCES: dict[str, set[str]] = {
    "banana": {"platano", "banano"},
    "platano": {"banana", "banano"},
    "banano": {"banana", "platano"},
    "potato": {"patata"},
    "patata": {"potato"},
    "tuna": {"atun"},
    "atun": {"tuna"},
}
