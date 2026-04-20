"""Pobla MongoDB con alimentos de entrenamiento etiquetados para ExtraTrees.

Formato de cada fila: (Nombre, Proteína, Grasa, Carbohidratos, Categoría, Fibra, Azúcar)
- Categoría correcta para que el feature category_score sea útil al modelo.
- Fibra y azúcar para que fiber_ratio y sugar_ratio diferencien
  cereales de desayuno (alto azúcar) de almidones (bajo azúcar).
"""

import os
import sys

os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
os.environ.setdefault("MONGO_DB_NAME", "fibrito")
os.environ.setdefault("JWT_SECRET_KEY", "dev-script-secret")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import get_database
from app.services.food_catalog_service import cache_spoonacular_food, calculate_macro_calories
from app.services.food_preferences_service import annotate_food_compatibility
from app.utils.normalization import normalize_food_name

# Formato: (Nombre, Proteína g, Grasa g, Carbohidratos g, Categoría, Fibra g, Azúcar g)
# suitable_meals se asigna automáticamente según la lista en que aparece el alimento.

BREAKFAST_FOODS = [
    # Cereales de desayuno: alto azúcar, fibra moderada
    ("Avena en hojuelas",              16.9,  6.9, 66.3, "cereales",       10.6,  1.2),
    ("Muesli sin azúcar",               9.8,  6.7, 62.0, "cereales",        7.5,  9.0),
    ("Granola con miel",                9.5, 14.0, 60.0, "cereales",        5.0, 20.0),
    # Lácteos: poca fibra, azúcar moderada (lactosa)
    ("Leche entera",                    3.2,  3.6,  4.8, "lacteos",         0.0,  4.8),
    ("Leche semidesnatada",             3.4,  1.7,  5.0, "lacteos",         0.0,  5.0),
    ("Yogur natural sin azúcar",        3.5,  3.3,  4.7, "lacteos",         0.0,  4.7),
    ("Yogur griego natural",            9.0,  5.0,  4.0, "lacteos",         0.0,  4.0),
    ("Queso fresco batido 0%",         10.5,  0.2,  3.8, "lacteos",         0.0,  3.8),
    # Huevos: sin fibra, sin azúcar — válidos en desayuno Y comidas principales
    ("Huevo entero crudo",              12.6,  9.5,  0.7, "proteinas",      0.0,  0.7),
    ("Clara de huevo cruda",            10.9,  0.2,  0.7, "proteinas",      0.0,  0.7),
    # Frutas: fibra media, azúcar alta
    ("Plátano (Banana)",                1.1,  0.3, 22.8, "frutas",          2.6, 12.2),
    ("Fresas frescas",                  0.7,  0.3,  7.7, "frutas",          2.0,  4.9),
    ("Arándanos frescos",               0.7,  0.3, 14.5, "frutas",          2.4,  9.9),
    ("Manzana",                         0.3,  0.2, 13.8, "frutas",          2.4, 10.3),
    ("Naranja",                         0.9,  0.1, 11.8, "frutas",          2.4,  9.4),
    # Grasas de desayuno
    ("Mantequilla de cacahuete natural",25.0, 50.0, 20.0, "grasas",         6.0,  9.0),
    ("Almendras tostadas sin sal",      21.2, 49.9, 21.6, "grasas",        12.5,  4.4),
    ("Nueces peladas",                  15.2, 65.2, 13.7, "grasas",         6.7,  2.6),
    ("Semillas de chía secas",          16.5, 30.7, 42.1, "grasas",        34.4,  0.0),
    # Pan (sirve para desayuno Y comida)
    ("Pan integral (harina de trigo)",   9.7,  4.2, 43.1, "carbohidratos",  6.8,  4.0),
]

LUNCH_FOODS = [
    # Proteínas versátiles (también válidas en desayuno pero principales en comida/cena)
    ("Huevo entero crudo",              12.6,  9.5,  0.7, "proteinas",      0.0,  0.7),
    ("Clara de huevo cruda",            10.9,  0.2,  0.7, "proteinas",      0.0,  0.7),
    # Proteínas magras: nada de fibra, nada de azúcar
    ("Pechuga de pollo cruda",          23.1,  1.2,  0.0, "proteinas",      0.0,  0.0),
    ("Pechuga de pavo cruda",           22.0,  1.0,  0.0, "proteinas",      0.0,  0.0),
    ("Atún al natural escurrido",       23.7,  1.0,  0.0, "proteinas",      0.0,  0.0),
    ("Carne picada de ternera magra",   20.8,  4.7,  0.0, "proteinas",      0.0,  0.0),
    ("Tofu firme",                      15.8,  8.7,  2.8, "proteinas",      0.3,  0.9),
    # Legumbres: alta fibra, bajo azúcar
    ("Lentejas secas (legumbre)",       25.8,  1.1, 60.1, "carbohidratos", 30.5,  2.0),
    ("Garbanzos secos (legumbre)",      19.3,  6.0, 60.7, "carbohidratos", 12.2,  1.0),
    ("Judías blancas secas",            22.3,  1.5, 60.8, "carbohidratos", 15.2,  2.3),
    # Almidones: fibra baja, azúcar casi nula — la clave para NO confundirlos con cereales
    ("Arroz blanco crudo",               7.1,  0.7, 80.0, "carbohidratos",  0.4,  0.1),
    ("Arroz integral crudo",             7.9,  2.9, 77.2, "carbohidratos",  3.5,  0.7),
    ("Pasta de trigo duro cruda",       13.0,  1.5, 74.7, "carbohidratos",  2.5,  0.6),
    ("Patata cruda",                     2.0,  0.1, 17.5, "carbohidratos",  2.2,  0.8),
    # Grasas de comida
    ("Aceite de oliva virgen extra",     0.0,100.0,  0.0, "grasas",         0.0,  0.0),
    ("Aguacate",                         2.0, 14.7,  8.5, "grasas",         6.7,  0.7),
    # Verduras: algo de fibra, azúcar baja
    ("Tomate natural crudo",             0.9,  0.2,  3.9, "vegetales",      1.2,  2.6),
    ("Lechuga iceberg",                  0.9,  0.1,  3.0, "vegetales",      1.3,  2.0),
    ("Pimiento rojo puro crudo",         1.0,  0.3,  6.0, "vegetales",      2.1,  4.2),
]

DINNER_FOODS = [
    # Pescados y carnes: sin fibra, sin azúcar
    ("Salmón crudo",                    19.8, 13.4,  0.0, "proteinas",      0.0,  0.0),
    ("Lomo de cerdo crudo",             22.5,  5.8,  0.0, "proteinas",      0.0,  0.0),
    ("Merluza cruda (pescado blanco)",  16.0,  1.5,  0.0, "proteinas",      0.0,  0.0),
    ("Sepia cruda",                     16.2,  0.7,  0.8, "proteinas",      0.0,  0.0),
    ("Gambas peladas crudas",           20.1,  0.5,  0.0, "proteinas",      0.0,  0.0),
    # Verduras de cena: fibra moderada
    ("Brócoli fresco crudo",             2.8,  0.4,  6.6, "vegetales",      2.6,  1.7),
    ("Coliflor fresca cruda",            1.9,  0.3,  5.0, "vegetales",      2.0,  1.9),
    ("Espinacas frescas",                2.9,  0.4,  3.6, "vegetales",      2.2,  0.4),
    ("Champiñones crudos",               3.1,  0.3,  3.3, "vegetales",      1.0,  1.7),
    ("Berenjena cruda",                  1.0,  0.2,  5.9, "vegetales",      3.0,  3.5),
    ("Calabacín fresco crudo",           1.2,  0.3,  3.1, "vegetales",      1.1,  2.5),
    ("Cebolla blanca cruda",             1.1,  0.1,  9.3, "vegetales",      1.7,  4.2),
    # Carbohidratos de cena
    ("Boniato crudo / Batata",           1.6,  0.1, 20.1, "carbohidratos",  3.0,  4.2),
    ("Ajo pelado crudo",                 6.4,  0.5, 33.1, "carbohidratos",  2.1,  1.0),
    # Lácteo de cena
    ("Queso Mozzarella fresco",         22.2, 22.4,  2.2, "lacteos",        0.0,  1.1),
]

# Alimentos adicionales que no llegó a cubrir la cuota de Spoonacular
EXTRA_PROTEINS = [
    ("Pechuga de pollo cruda",          23.1,  1.2,  0.0, "proteinas",      0.0,  0.0),
    ("Pechuga de pavo cruda",           22.0,  1.0,  0.0, "proteinas",      0.0,  0.0),
    ("Atún al natural (lata escurrida)",25.5,  0.8,  0.0, "proteinas",      0.0,  0.0),
    ("Claras de huevo crudas",          10.9,  0.2,  0.7, "proteinas",      0.0,  0.7),
    ("Yogur griego 0% sin azúcar",      10.2,  0.4,  3.6, "lacteos",        0.0,  3.6),
    ("Queso cottage desnatado",         11.1,  0.3,  3.4, "lacteos",        0.0,  3.4),
    ("Leche desnatada",                  3.4,  0.1,  4.9, "lacteos",        0.0,  4.9),
    ("Tofu firme",                      8.1,   4.8,  1.9, "proteinas",      0.3,  0.6),
    ("Edamame",                         11.9,  5.2,  8.9, "proteinas",      5.2,  2.2),
    ("Ternera magra cruda",             21.4,  4.8,  0.0, "proteinas",      0.0,  0.0),
    ("Bacalao crudo",                   17.8,  0.7,  0.0, "proteinas",      0.0,  0.0),
    ("Gambas crudas",                   20.1,  0.5,  0.0, "proteinas",      0.0,  0.0),
]

EXTRA_CARBS = [
    ("Arroz blanco crudo",               7.1,  0.7, 80.0, "carbohidratos",  0.4,  0.1),
    ("Arroz integral crudo",             7.9,  2.9, 77.2, "carbohidratos",  3.5,  0.7),
    ("Pasta de trigo duro cruda",       13.0,  1.5, 74.7, "carbohidratos",  2.5,  0.6),
    ("Pasta integral cruda",            13.0,  2.5, 68.0, "carbohidratos",  7.0,  3.0),
    ("Quinoa cruda",                    14.1,  6.1, 64.2, "carbohidratos",  7.0,  4.0),
    ("Boniato crudo",                    1.6,  0.1, 20.1, "carbohidratos",  3.0,  4.2),
    ("Patata cruda",                     2.0,  0.1, 17.5, "carbohidratos",  2.2,  0.8),
    ("Lentejas secas",                  25.8,  1.1, 60.1, "carbohidratos", 30.5,  2.0),
    ("Garbanzos secos",                 19.3,  6.0, 60.7, "carbohidratos", 12.2,  1.0),
    ("Judías negras secas",             21.6,  1.4, 62.4, "carbohidratos", 15.5,  2.1),
    ("Copos de avena",                  16.9,  6.9, 66.3, "carbohidratos", 10.6,  1.2),
    ("Tortilla de maíz",                 5.7,  2.9, 44.6, "carbohidratos",  4.1,  0.4),
    ("Pan de centeno integral",         8.5,   2.0, 48.3, "carbohidratos",  6.2,  3.8),
]

EXTRA_VEGS = [
    ("Brócoli crudo",                    2.8,  0.4,  6.6, "vegetales",      2.6,  1.7),
    ("Espinacas crudas",                 2.9,  0.4,  3.6, "vegetales",      2.2,  0.4),
    ("Kale crudo",                       4.3,  0.9,  8.8, "vegetales",      3.6,  2.3),
    ("Judías verdes crudas",             1.8,  0.1,  7.0, "vegetales",      3.4,  3.3),
    ("Pimiento rojo crudo",              1.0,  0.3,  6.0, "vegetales",      2.1,  4.2),
    ("Zanahoria cruda",                  0.9,  0.2,  9.6, "vegetales",      2.8,  4.7),
    ("Tomate cherry",                    0.9,  0.2,  3.5, "vegetales",      1.2,  2.6),
    ("Pepino crudo",                     0.7,  0.1,  3.6, "vegetales",      0.5,  1.7),
    ("Setas crudas",                     3.1,  0.3,  3.3, "vegetales",      1.0,  1.7),
]

EXTRA_FATS = [
    ("Almendras crudas",                21.2, 49.9, 21.6, "grasas",        12.5,  4.4),
    ("Nueces peladas",                  15.2, 65.2, 13.7, "grasas",         6.7,  2.6),
    ("Aguacate",                         2.0, 14.7,  8.5, "grasas",         6.7,  0.7),
    ("Mantequilla de cacahuete natural",25.0, 50.0, 20.0, "grasas",         6.0,  9.0),
    ("Semillas de lino molidas",         18.3, 42.2, 28.9, "grasas",        27.3,  1.6),
]


def _has_any_token(name: str, tokens: tuple[str, ...]) -> bool:
    normalized_name = normalize_food_name(name)
    return any(token in normalized_name for token in tokens)


def get_suitable_meals(name: str) -> list[str]:
    labels: list[str] = []
    if any(row[0] == name for row in BREAKFAST_FOODS):
        labels.extend(["early", "snack"])
    if any(row[0] == name for row in LUNCH_FOODS):
        labels.append("main")
    if any(row[0] == name for row in DINNER_FOODS):
        labels.append("late")
    # Los extras usan reglas más finas para no contaminar el entrenamiento.
    if any(row[0] == name for row in EXTRA_PROTEINS):
        if _has_any_token(name, ("yogur", "yogurt", "cottage", "leche", "milk")):
            labels.extend(["early", "snack"])
        elif _has_any_token(name, ("huevo", "egg", "claras")):
            labels.extend(["early", "main"])
        else:
            labels.extend(["main", "late"])

    if any(row[0] == name for row in EXTRA_CARBS):
        if _has_any_token(name, ("avena", "oats", "pan", "bread", "muesli", "granola")):
            labels.extend(["early", "snack"])
            if _has_any_token(name, ("pan", "bread")):
                labels.append("main")
        else:
            labels.extend(["main", "late"])

    if any(row[0] == name for row in EXTRA_VEGS):
        labels.extend(["main", "late", "snack"])

    if any(row[0] == name for row in EXTRA_FATS):
        if _has_any_token(name, ("almendra", "nueces", "cacahuete", "chia", "lino")):
            labels.extend(["early", "snack"])
        elif _has_any_token(name, ("aguacate", "avocado")):
            labels.extend(["early", "main", "late", "snack"])
        else:
            labels.extend(["main", "late"])
    return list(dict.fromkeys(labels)) if labels else ["main"]


def populate() -> None:
    print("1. Conectando a MongoDB en localhost...")
    try:
        db = get_database()
        db.command("ping")
        print("   -> Conexión exitosa.")
    except Exception as exc:
        print(f"\n[ERROR] No se pudo conectar: {exc}")
        print("Asegúrate de que el contenedor de MongoDB está corriendo.")
        return

    all_raw_foods = (
        BREAKFAST_FOODS + LUNCH_FOODS + DINNER_FOODS
        + EXTRA_PROTEINS + EXTRA_CARBS + EXTRA_VEGS + EXTRA_FATS
    )
    print(f"\n2. Inyectando {len(all_raw_foods)} ingredientes con macros, fibra y azúcar reales.")
    print("-" * 70)

    for i, row in enumerate(all_raw_foods):
        name, protein, fat, carb, category, fiber, sugar = row
        cals = calculate_macro_calories(protein, fat, carb)
        norm_name = normalize_food_name(name)

        mock_food = {
            "code": f"mock_raw_{i}",
            "internal_code": None,
            "normalized_name": norm_name,
            "original_name": name,
            "name": name,
            "display_name": name,
            "category": category,          # Categoría real (no "otros")
            "source": "spoonacular",
            "origin_source": "spoonacular",
            "spoonacular_id": -9000 - i,
            "reference_amount": 100.0,
            "reference_unit": "g",
            "grams_per_reference": 100.0,
            "calories": cals,
            "protein_grams": protein,
            "fat_grams": fat,
            "carb_grams": carb,
            "fiber_grams": fiber,          # Nuevo: para fiber_ratio en features 6D
            "sugar_grams": sugar,          # Nuevo: para sugar_ratio en features 6D
            "default_quantity": 100.0,
            "min_quantity": 50.0,
            "max_quantity": 550.0 if category == "carbohidratos" else 300.0,
            "step": 10.0,
            "matched_query": name,
            "image": None,
            "aliases": [norm_name],
            "suitable_meals": get_suitable_meals(name),
        }

        mock_food = annotate_food_compatibility(mock_food)
        cache_spoonacular_food(db, mock_food)
        slot = get_suitable_meals(name)
        print(f"  [{slot}] {name} ({int(cals)} kcal | P:{protein} G:{fat} C:{carb} F:{fiber} Az:{sugar})")

    print("-" * 70)
    print(f"3. {len(all_raw_foods)} ingredientes inyectados correctamente.")
    print("   Ejecuta retro_tag.py para reentrenar el modelo con los nuevos datos.")


if __name__ == "__main__":
    populate()
