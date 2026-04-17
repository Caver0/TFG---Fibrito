"""
Enriquece el catálogo local de alimentos con datos reales de Spoonacular.
Busca ingredientes por nombre, obtiene macros a 100 g y los guarda en MongoDB.

Uso:
    python enrich_catalog.py
"""
import os
import sys
import time

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "fibrito")
os.environ.setdefault("JWT_SECRET_KEY", "dev-script-secret")
os.environ.setdefault("SPOONACULAR_API_KEY", "43d0574fa7424afd861f12bbcb9159b6")
os.environ.setdefault("SPOONACULAR_BASE_URL", "https://api.spoonacular.com")
os.environ.setdefault("SPOONACULAR_TIMEOUT_SECONDS", "15")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import get_database
from app.services.food_catalog_service import (
    cache_spoonacular_food,
    calculate_macro_calories,
    _extract_nutrient_amounts,
    _infer_food_category,
)
from app.services.food_preferences_service import annotate_food_compatibility
from app.services.spoonacular_service import (
    SpoonacularError,
    get_ingredient_information,
    search_ingredients,
)
from app.utils.normalization import build_food_aliases, normalize_food_name

# ──────────────────────────────────────────────────────────────────────────────
# Alimentos que queremos añadir al catálogo (término de búsqueda, categoría)
# Priorizamos fuentes de carbohidratos que faltaban, más variedad proteica
# y verduras de relleno para que el generador tenga más opciones.
# ──────────────────────────────────────────────────────────────────────────────
TARGETS = [
    # ── Carbohidratos ──────────────────────────────────────────────────────────
    ("white rice cooked",           "carbohidratos"),
    ("brown rice cooked",           "carbohidratos"),
    ("pasta cooked",                "carbohidratos"),
    ("whole wheat pasta cooked",    "carbohidratos"),
    ("quinoa cooked",               "carbohidratos"),
    ("oatmeal cooked",              "carbohidratos"),
    ("sweet potato cooked",         "carbohidratos"),
    ("corn tortilla",               "carbohidratos"),
    ("whole wheat bread",           "carbohidratos"),
    ("lentils cooked",              "carbohidratos"),
    ("chickpeas cooked",            "carbohidratos"),
    ("black beans cooked",          "carbohidratos"),
    ("kidney beans cooked",         "carbohidratos"),
    ("white potato boiled",         "carbohidratos"),
    ("couscous cooked",             "carbohidratos"),
    ("bulgur cooked",               "carbohidratos"),
    ("buckwheat cooked",            "carbohidratos"),
    ("millet cooked",               "carbohidratos"),
    ("cornmeal cooked",             "carbohidratos"),
    ("rice cakes",                  "carbohidratos"),
    # ── Frutas ────────────────────────────────────────────────────────────────
    ("banana",                      "frutas"),
    ("apple",                       "frutas"),
    ("orange",                      "frutas"),
    ("mango",                       "frutas"),
    ("strawberries",                "frutas"),
    ("blueberries",                 "frutas"),
    ("pear",                        "frutas"),
    ("kiwi",                        "frutas"),
    ("grapes",                      "frutas"),
    ("watermelon",                  "frutas"),
    ("pineapple",                   "frutas"),
    ("peach",                       "frutas"),
    ("raspberries",                 "frutas"),
    ("cherries",                    "frutas"),
    ("melon cantaloupe",            "frutas"),
    # ── Proteínas magras ──────────────────────────────────────────────────────
    ("chicken breast cooked",       "proteinas"),
    ("turkey breast cooked",        "proteinas"),
    ("tuna in water canned",        "proteinas"),
    ("salmon fillet baked",         "proteinas"),
    ("cod fillet baked",            "proteinas"),
    ("tilapia cooked",              "proteinas"),
    ("shrimp cooked",               "proteinas"),
    ("egg whole cooked",            "proteinas"),
    ("egg whites cooked",           "proteinas"),
    ("tofu firm",                   "proteinas"),
    ("edamame cooked",              "proteinas"),
    ("tempeh",                      "proteinas"),
    ("seitan",                      "proteinas"),
    ("lean beef ground cooked",     "proteinas"),
    ("pork tenderloin cooked",      "proteinas"),
    ("sardines in water",           "proteinas"),
    ("mackerel canned",             "proteinas"),
    ("canned chicken",              "proteinas"),
    # ── Lácteos ───────────────────────────────────────────────────────────────
    ("greek yogurt plain",          "lacteos"),
    ("cottage cheese",              "lacteos"),
    ("skimmed milk",                "lacteos"),
    ("low fat quark",               "lacteos"),
    ("skyr plain",                  "lacteos"),
    ("ricotta cheese",              "lacteos"),
    ("low fat mozzarella",          "lacteos"),
    # ── Grasas saludables ─────────────────────────────────────────────────────
    ("almonds",                     "grasas"),
    ("walnuts",                     "grasas"),
    ("cashews",                     "grasas"),
    ("pistachios",                  "grasas"),
    ("hazelnuts",                   "grasas"),
    ("pumpkin seeds",               "grasas"),
    ("sunflower seeds",             "grasas"),
    ("chia seeds",                  "grasas"),
    ("flaxseeds",                   "grasas"),
    ("avocado",                     "grasas"),
    ("olive oil",                   "grasas"),
    ("peanut butter natural",       "grasas"),
    ("almond butter",               "grasas"),
    ("coconut oil",                 "grasas"),
    ("tahini",                      "grasas"),
    # ── Verduras ──────────────────────────────────────────────────────────────
    ("broccoli cooked",             "vegetales"),
    ("spinach cooked",              "vegetales"),
    ("kale raw",                    "vegetales"),
    ("green beans cooked",          "vegetales"),
    ("zucchini cooked",             "vegetales"),
    ("bell pepper raw",             "vegetales"),
    ("cherry tomatoes",             "vegetales"),
    ("cucumber raw",                "vegetales"),
    ("carrot raw",                  "vegetales"),
    ("mushrooms cooked",            "vegetales"),
    ("cauliflower cooked",          "vegetales"),
    ("asparagus cooked",            "vegetales"),
    ("brussels sprouts cooked",     "vegetales"),
    ("eggplant cooked",             "vegetales"),
    ("celery raw",                  "vegetales"),
    ("lettuce romaine",             "vegetales"),
    ("arugula raw",                 "vegetales"),
    ("leek cooked",                 "vegetales"),
    ("onion raw",                   "vegetales"),
    ("artichoke cooked",            "vegetales"),
    ("peas cooked",                 "vegetales"),
    ("corn cooked",                 "vegetales"),
    ("beet cooked",                 "vegetales"),
    ("cabbage cooked",              "vegetales"),
    ("swiss chard cooked",          "vegetales"),
]

DELAY_BETWEEN_CALLS = 1.2  # segundos entre llamadas para no saturar la API


def _build_food_document(
    spoonacular_info: dict,
    query: str,
    forced_category: str,
) -> dict:
    """Construye el documento de alimento a partir de la respuesta de Spoonacular."""
    nutrients_raw = spoonacular_info.get("nutrition", {}).get("nutrients", [])
    nutrients = _extract_nutrient_amounts(nutrients_raw)

    name = str(
        spoonacular_info.get("name")
        or spoonacular_info.get("originalName")
        or query
    ).strip().capitalize()
    normalized = normalize_food_name(name)
    spoonacular_id = spoonacular_info.get("id")

    category = forced_category or _infer_food_category(
        name,
        nutrients["protein_grams"],
        nutrients["fat_grams"],
        nutrients["carb_grams"],
    )

    code = f"spoonacular_{normalized.replace(' ', '_')}_{spoonacular_id}"

    return annotate_food_compatibility({
        "code": code,
        "internal_code": None,
        "normalized_name": normalized,
        "original_name": spoonacular_info.get("originalName") or name,
        "name": name,
        "display_name": name,
        "category": category,
        "source": "spoonacular",
        "origin_source": "spoonacular",
        "spoonacular_id": spoonacular_id,
        "reference_amount": 100.0,
        "reference_unit": "g",
        "grams_per_reference": 100.0,
        "calories": nutrients["calories"],
        "protein_grams": nutrients["protein_grams"],
        "fat_grams": nutrients["fat_grams"],
        "carb_grams": nutrients["carb_grams"],
        "fiber_grams": next(
            (float(n["amount"]) for n in nutrients_raw if normalize_food_name(str(n.get("name", ""))) == "fiber"),
            0.0,
        ),
        "sugar_grams": next(
            (float(n["amount"]) for n in nutrients_raw if normalize_food_name(str(n.get("name", ""))) in ("sugar", "sugars")),
            0.0,
        ),
        "default_quantity": 100.0,
        "min_quantity": 50.0,
        "max_quantity": 350.0,
        "step": 5.0,
        "matched_query": query,
        "image": spoonacular_info.get("image"),
        "aliases": build_food_aliases(name, query, normalized),
    })


def enrich() -> None:
    print("Conectando a MongoDB...")
    db = get_database()
    db.command("ping")
    print("Conexion OK.\n")

    saved = 0
    skipped = 0
    errors = 0

    for query, category in TARGETS:
        print(f"  Buscando: '{query}'...", end=" ", flush=True)
        try:
            results = search_ingredients(query, number=3)
            if not results:
                print("sin resultados, omitido.")
                skipped += 1
                time.sleep(DELAY_BETWEEN_CALLS)
                continue

            # Tomar el primer resultado (mejor coincidencia)
            best = results[0]
            ingredient_id = best["id"]

            time.sleep(DELAY_BETWEEN_CALLS)
            info = get_ingredient_information(ingredient_id, amount=100, unit="g")

            food_doc = _build_food_document(info, query, category)
            cache_spoonacular_food(db, food_doc)

            cal = round(food_doc["calories"], 1)
            p   = round(food_doc["protein_grams"], 1)
            f   = round(food_doc["fat_grams"], 1)
            c   = round(food_doc["carb_grams"], 1)
            print(f"OK -> {food_doc['name']} | {cal} kcal | P:{p} G:{f} C:{c}")
            saved += 1

        except SpoonacularError as exc:
            print(f"ERROR Spoonacular: {exc}")
            errors += 1
        except Exception as exc:
            print(f"ERROR inesperado: {exc}")
            errors += 1

        time.sleep(DELAY_BETWEEN_CALLS)

    print(f"\nResumen: {saved} guardados | {skipped} omitidos | {errors} errores")
    print("Ejecuta retro_tag.py para reentrenar el modelo con los nuevos datos.")


if __name__ == "__main__":
    enrich()
