"""Utility helpers to normalize food names across local and external sources."""
from __future__ import annotations

import re
import unicodedata

_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")

# Traducciones español → inglés para búsquedas en Spoonacular y otros catálogos externos.
# Las claves son nombres normalizados (sin tildes, minúsculas, sin caracteres especiales).
# Se añaden primero las expresiones compuestas para que el matching prioritice la forma más específica.
TRADUCCIONES_ALIMENTOS_ES_EN: dict[str, str] = {
    # ── Frutas ────────────────────────────────────────────────────────────────────
    "datiles": "dates",
    "datil": "date",
    "platano": "banana",
    "banano": "banana",
    "manzana": "apple",
    "manzanas": "apples",
    "naranja": "orange",
    "naranjas": "oranges",
    "pera": "pear",
    "peras": "pears",
    "melocoton": "peach",
    "melocotones": "peaches",
    "durazno": "peach",
    "duraznos": "peaches",
    "albaricoque": "apricot",
    "albaricoques": "apricots",
    "sandia": "watermelon",
    "melon": "melon",
    "pina": "pineapple",
    "ananas": "pineapple",
    "fresa": "strawberry",
    "fresas": "strawberries",
    "frambuesa": "raspberry",
    "frambuesas": "raspberries",
    "arandano": "blueberry",
    "arandanos": "blueberries",
    "uva": "grape",
    "uvas": "grapes",
    "mango": "mango",
    "papaya": "papaya",
    "kiwi": "kiwi",
    "cereza": "cherry",
    "cerezas": "cherries",
    "limon": "lemon",
    "limones": "lemons",
    "lima": "lime",
    "limas": "limes",
    "pomelo": "grapefruit",
    "mandarina": "tangerine",
    "mandarinas": "tangerines",
    "higo": "fig",
    "higos": "figs",
    "ciruela": "plum",
    "ciruelas": "plums",
    "nectarina": "nectarine",
    "granada": "pomegranate",
    # ── Proteínas animales ─────────────────────────────────────────────────────────
    "pechuga de pollo": "chicken breast",
    "pechuga de pavo": "turkey breast",
    "pechuga pollo": "chicken breast",
    "pechuga pavo": "turkey breast",
    "pollo": "chicken",
    "pavo": "turkey",
    "atun": "tuna",
    "salmon": "salmon",
    "merluza": "hake",
    "bacalao": "cod",
    "sardina": "sardine",
    "sardinas": "sardines",
    "ternera": "beef",
    "carne de ternera": "beef",
    "cerdo": "pork",
    "jamon": "ham",
    "jamon serrano": "serrano ham",
    "claras de huevo": "egg whites",
    "clara de huevo": "egg white",
    "claras": "egg whites",
    "huevo": "egg",
    "huevos": "eggs",
    "gamba": "shrimp",
    "gambas": "shrimp",
    "langostino": "prawn",
    "langostinos": "prawns",
    "calamar": "squid",
    "calamares": "squid",
    "sepia": "cuttlefish",
    "pulpo": "octopus",
    # ── Lácteos ───────────────────────────────────────────────────────────────────
    "yogur griego": "greek yogurt",
    "yogurt griego": "greek yogurt",
    "yogur": "yogurt",
    "yogurt": "yogurt",
    "leche desnatada": "skim milk",
    "leche semidesnatada": "semi skimmed milk",
    "leche entera": "whole milk",
    "leche": "milk",
    "queso cottage": "cottage cheese",
    "queso fresco": "fresh cheese",
    "requeson": "ricotta",
    "queso": "cheese",
    # ── Carbohidratos / cereales ───────────────────────────────────────────────────
    "copos de maiz": "cornflakes",
    "copos de avena": "oats",
    "copos de trigo": "wheat flakes",
    "pan integral": "whole wheat bread",
    "pan de centeno": "rye bread",
    "arroz integral": "brown rice",
    "arroz blanco": "white rice",
    "arroz": "rice",
    "pasta integral": "whole wheat pasta",
    "pasta": "pasta",
    "patatas": "potatoes",
    "patata": "potato",
    "boniato": "sweet potato",
    "batata": "sweet potato",
    "avena": "oats",
    "pan": "bread",
    "tortilla de maiz": "corn tortilla",
    "tortilla": "tortilla",
    "maiz": "corn",
    "quinoa": "quinoa",
    "quinua": "quinoa",
    "couscous": "couscous",
    "lentejas": "lentils",
    "lenteja": "lentil",
    "garbanzos": "chickpeas",
    "garbanzo": "chickpea",
    "judias blancas": "white beans",
    "judias negras": "black beans",
    "judias": "beans",
    "judia": "bean",
    "harina de avena": "oat flour",
    "harina integral": "whole wheat flour",
    "harina": "flour",
    "cereales": "cereals",
    "granola": "granola",
    "muesli": "muesli",
    # ── Grasas / frutos secos ──────────────────────────────────────────────────────
    "mantequilla de cacahuete": "peanut butter",
    "aceite de oliva virgen extra": "extra virgin olive oil",
    "aceite de oliva": "olive oil",
    "aceite": "oil",
    "aguacate": "avocado",
    "almendras": "almonds",
    "almendra": "almond",
    "nueces": "walnuts",
    "nuez": "walnut",
    "cacahuetes": "peanuts",
    "cacahuete": "peanut",
    "anacardos": "cashews",
    "anacardo": "cashew",
    "pistachos": "pistachios",
    "pistacho": "pistachio",
    "semillas de chia": "chia seeds",
    "semillas de lino": "flax seeds",
    "semillas de girasol": "sunflower seeds",
    "semillas de calabaza": "pumpkin seeds",
    "chia": "chia",
    "lino": "flax",
    "mantequilla": "butter",
    # ── Verduras y hortalizas ──────────────────────────────────────────────────────
    "espinacas": "spinach",
    "espinaca": "spinach",
    "brocoli": "broccoli",
    "zanahoria": "carrot",
    "zanahorias": "carrots",
    "tomate": "tomato",
    "tomates": "tomatoes",
    "lechuga": "lettuce",
    "pepino": "cucumber",
    "cebolla": "onion",
    "cebollas": "onions",
    "ajo": "garlic",
    "pimiento rojo": "red bell pepper",
    "pimiento verde": "green bell pepper",
    "pimiento": "bell pepper",
    "pimientos": "bell peppers",
    "calabacin": "zucchini",
    "berenjena": "eggplant",
    "coliflor": "cauliflower",
    "col": "cabbage",
    "apio": "celery",
    "champiñon": "mushroom",
    "champiñones": "mushrooms",
    "setas": "mushrooms",
    "judias verdes": "green beans",
    "guisantes": "peas",
    "maiz dulce": "sweet corn",
    "alcachofa": "artichoke",
    "esparragos": "asparagus",
    "esparrago": "asparagus",
    # ── Otros ─────────────────────────────────────────────────────────────────────
    "frutos secos": "mixed nuts",
    "fruto seco": "nuts",
}


def normalize_food_name(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    cleaned_value = _NON_ALPHANUMERIC_PATTERN.sub(" ", ascii_value)
    return _WHITESPACE_PATTERN.sub(" ", cleaned_value).strip()


def translate_food_query_for_search(query: str) -> str:
    """Normaliza y traduce un nombre de alimento español al inglés para búsqueda externa.

    Pasos: normalización Unicode → minúsculas → búsqueda en tabla de traducciones.
    Si no hay traducción conocida, devuelve el nombre normalizado (sin tildes).
    Las expresiones compuestas se comprueban antes que las simples.
    """
    normalized = normalize_food_name(query)
    if not normalized:
        return query

    # Buscar primero por expresión exacta normalizada
    if normalized in TRADUCCIONES_ALIMENTOS_ES_EN:
        return TRADUCCIONES_ALIMENTOS_ES_EN[normalized]

    # Buscar expresiones compuestas que contengan la consulta como subcadena
    for clave_es, valor_en in TRADUCCIONES_ALIMENTOS_ES_EN.items():
        if " " in clave_es and normalized in clave_es:
            return valor_en

    return normalized


def build_food_aliases(*values: str) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized_value = normalize_food_name(value)
        if not normalized_value or normalized_value in seen:
            continue

        aliases.append(normalized_value)
        seen.add(normalized_value)

    return aliases
