"""Utility helpers to normalize food names across local and external sources."""
from __future__ import annotations

import re
import unicodedata

_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_RAW_REFERENCE_SUFFIX_PATTERN = re.compile(
    r"\b(?:"
    r"cocid[oa]s?|cocinad[oa]s?|hervid[oa]s?|asad[oa]s?|hornead[oa]s?|"
    r"saltead[oa]s?|frit[oa]s?|a la plancha|a la parrilla|a la brasa|al horno|"
    r"cooked|boiled|baked|roasted|grilled|fried|steamed|sauteed"
    r")\b",
    re.IGNORECASE,
)
_RAW_REFERENCE_EXTRA_PATTERN = re.compile(r"\b(?:sin piel)\b", re.IGNORECASE)

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

_RAW_REFERENCE_BY_CODE: dict[str, str] = {
    "oatmeal cooked": "Avena",
    "white rice cooked": "Arroz",
    "brown rice cooked": "Arroz integral",
    "rice cooked": "Arroz",
    "pasta cooked": "Pasta",
    "whole wheat pasta cooked": "Pasta integral",
    "sweet potato cooked": "Boniato",
    "potato cooked": "Patata",
    "broccoli cooked": "Brocoli",
    "spinach cooked": "Espinacas",
    "green beans cooked": "Judias verdes",
    "mushrooms cooked": "Setas",
    "chicken breast cooked": "Pechuga de pollo",
    "turkey breast cooked": "Pechuga de pavo",
    "egg whites cooked": "Claras de huevo",
    "egg whole cooked": "Huevo",
    "salmon fillet baked": "Salmon",
    "cod fillet baked": "Bacalao",
    "shrimp cooked": "Gambas",
}

_RAW_REFERENCE_BY_NAME: dict[str, str] = {
    "avena cocida": "Avena",
    "copos de avena cocidos": "Copos de avena",
    "oatmeal cooked": "Avena",
    "arroz cocido": "Arroz",
    "arroz blanco cocido": "Arroz",
    "white rice cooked": "Arroz",
    "arroz integral cocido": "Arroz integral",
    "brown rice cooked": "Arroz integral",
    "pasta cocida": "Pasta",
    "pasta integral cocida": "Pasta integral",
    "pasta cooked": "Pasta",
    "whole wheat pasta cooked": "Pasta integral",
    "quinoa cocida": "Quinoa",
    "quinoa cooked": "Quinoa",
    "boniato cocido": "Boniato",
    "sweet potato cooked": "Boniato",
    "patata cocida": "Patata",
    "patata cocida sin piel": "Patata",
    "white potato boiled": "Patata",
    "lentejas cocidas": "Lentejas",
    "lentils cooked": "Lentejas",
    "garbanzos cocidos": "Garbanzos",
    "chickpeas cooked": "Garbanzos",
    "judias negras cocidas": "Judias negras",
    "black beans cooked": "Judias negras",
    "judias rojas cocidas": "Judias rojas",
    "kidney beans cooked": "Judias rojas",
    "couscous cooked": "Couscous",
    "bulgur cooked": "Bulgur",
    "buckwheat cooked": "Trigo sarraceno",
    "millet cooked": "Mijo",
    "cornmeal cooked": "Harina de maiz",
    "pechuga de pollo cocida": "Pechuga de pollo",
    "chicken breast cooked": "Pechuga de pollo",
    "pechuga de pollo a la plancha": "Pechuga de pollo",
    "pechuga de pavo cocida": "Pechuga de pavo",
    "turkey breast cooked": "Pechuga de pavo",
    "claras de huevo cocidas": "Claras de huevo",
    "egg whites cooked": "Claras de huevo",
    "huevo cocido": "Huevo",
    "egg whole cooked": "Huevo",
    "salmon al horno": "Salmon",
    "salmon fillet baked": "Salmon",
    "bacalao al horno": "Bacalao",
    "cod fillet baked": "Bacalao",
    "tilapia cooked": "Tilapia",
    "gambas cocidas": "Gambas",
    "shrimp cooked": "Gambas",
    "edamame cocido": "Edamame",
    "edamame cooked": "Edamame",
    "ternera magra cocida": "Ternera magra",
    "lean beef ground cooked": "Carne picada magra",
    "pork tenderloin cooked": "Lomo de cerdo",
    "brocoli cocido": "Brocoli",
    "broccoli cooked": "Brocoli",
    "espinacas cocidas": "Espinacas",
    "spinach cooked": "Espinacas",
    "judias verdes cocidas": "Judias verdes",
    "green beans cooked": "Judias verdes",
    "pimiento rojo cocido": "Pimiento rojo",
    "zucchini cooked": "Calabacin",
    "setas cocidas": "Setas",
    "mushrooms cooked": "Setas",
    "cauliflower cooked": "Coliflor",
    "asparagus cooked": "Esparragos",
    "brussels sprouts cooked": "Coles de bruselas",
    "eggplant cooked": "Berenjena",
    "leek cooked": "Puerro",
    "artichoke cooked": "Alcachofa",
    "peas cooked": "Guisantes",
    "corn cooked": "Maiz",
    "beet cooked": "Remolacha",
    "cabbage cooked": "Col",
    "swiss chard cooked": "Acelga",
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


def normalize_food_to_raw_reference(value: str, *, food_code: str | None = None) -> str:
    cleaned_value = str(value or "").strip()
    if not cleaned_value:
        return ""

    normalized_code = normalize_food_name(str(food_code or "").replace("_", " "))
    if normalized_code in _RAW_REFERENCE_BY_CODE:
        return _RAW_REFERENCE_BY_CODE[normalized_code]

    normalized_value = normalize_food_name(cleaned_value)
    if normalized_value in _RAW_REFERENCE_BY_NAME:
        return _RAW_REFERENCE_BY_NAME[normalized_value]

    stripped_value = _RAW_REFERENCE_SUFFIX_PATTERN.sub(" ", cleaned_value)
    stripped_value = _RAW_REFERENCE_EXTRA_PATTERN.sub(" ", stripped_value)
    stripped_value = re.sub(r"\s+", " ", stripped_value).strip(" ,-/")
    if not stripped_value:
        return cleaned_value

    normalized_stripped_value = normalize_food_name(stripped_value)
    if normalized_stripped_value in _RAW_REFERENCE_BY_NAME:
        return _RAW_REFERENCE_BY_NAME[normalized_stripped_value]

    return stripped_value


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

    normalized_raw_reference = normalize_food_name(normalize_food_to_raw_reference(query))
    if normalized_raw_reference in TRADUCCIONES_ALIMENTOS_ES_EN:
        return TRADUCCIONES_ALIMENTOS_ES_EN[normalized_raw_reference]

    # Buscar expresiones compuestas que contengan la consulta como subcadena
    for clave_es, valor_en in TRADUCCIONES_ALIMENTOS_ES_EN.items():
        if " " in clave_es and (normalized in clave_es or normalized_raw_reference in clave_es):
            return valor_en

    return normalized_raw_reference or normalized


def build_food_aliases(*values: str) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    for value in values:
        for candidate_value in (str(value or ""), normalize_food_to_raw_reference(str(value or ""))):
            normalized_value = normalize_food_name(candidate_value)
            if not normalized_value or normalized_value in seen:
                continue

            aliases.append(normalized_value)
            seen.add(normalized_value)

    return aliases
