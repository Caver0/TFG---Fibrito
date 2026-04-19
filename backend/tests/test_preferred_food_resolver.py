"""Tests de la fase de enriquecimiento del lookup con alimentos preferidos.

Cubre los cinco casos del requisito:
  1. 'Cornflakes' no en catálogo local → Spoonacular lo resuelve → entra en lookup.
  2. 'Dátiles' no local → 'dates' se resuelve externamente → entra en lookup.
  3. Con preferred_foods=['Cornflakes'] el alimento queda disponible antes del solver.
  4. Con preferred_foods=['Dátiles', 'Cornflakes'] ambos participan en el flujo.
  5. Si un preferido no puede resolverse, queda en la lista no_resueltos sin romper nada.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.preferred_food_resolver import enrich_lookup_con_preferidos
from app.services.food_preferences_service import buscar_alimentos_por_nombre

# ── Parche ML global ──────────────────────────────────────────────────────────
_PATCH_ML = patch("app.services.diet.candidates.predict_meal_slot_scores", return_value={})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_spoonacular_food(code: str, name: str, category: str,
                           protein=5.0, fat=2.0, carb=70.0) -> dict:
    """Construye un fake food dict con el mismo formato que search_spoonacular_food devuelve."""
    from app.services.food_catalog_service import GENERIC_DEFAULT_QUANTITY, GENERIC_MAX_QUANTITY, GENERIC_MIN_QUANTITY, GENERIC_STEP
    return {
        "code": code,
        "internal_code": None,
        "name": name,
        "display_name": name,
        "normalized_name": name.lower().replace(" ", ""),
        "original_name": name,
        "category": category,
        "source": "spoonacular",
        "origin_source": "spoonacular",
        "spoonacular_id": 12345,
        "protein_grams": protein,
        "fat_grams": fat,
        "carb_grams": carb,
        "calories": protein * 4 + fat * 9 + carb * 4,
        "reference_amount": 100.0,
        "reference_unit": "g",
        "grams_per_reference": 100.0,
        "default_quantity": GENERIC_DEFAULT_QUANTITY,
        "min_quantity": GENERIC_MIN_QUANTITY,
        "max_quantity": GENERIC_MAX_QUANTITY,
        "step": GENERIC_STEP,
        "matched_query": name,
        "image": None,
        "aliases": [name.lower(), name.lower().replace(" ", "")],
        "preference_labels": [name.lower(), name.lower().replace(" ", "")],
        "dietary_flags": [],
        "allergy_flags": [],
        "tags": [],
        "suitable_meals": [],
    }


FAKE_CORNFLAKES = _fake_spoonacular_food(
    code="spoonacular_corn_flakes_12345",
    name="Corn Flakes",
    category="carbohidratos",
    protein=7.0, fat=1.0, carb=84.0,
)

FAKE_DATES = _fake_spoonacular_food(
    code="spoonacular_dates_99999",
    name="Dates",
    category="frutas",
    protein=2.5, fat=0.4, carb=75.0,
)


# ── Test 1: Cornflakes no está en catálogo local → Spoonacular lo inyecta ─────

def test_cornflakes_no_local_se_inyecta_desde_spoonacular():
    """Si 'Cornflakes' no está en el lookup inicial, search_spoonacular_food lo provee
    y enrich_lookup_con_preferidos lo inyecta en full_food_lookup."""
    lookup_inicial: dict = {}  # lookup vacío = cornflakes no existe localmente
    database = MagicMock()

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        return_value=FAKE_CORNFLAKES,
    ) as mock_spoon:
        no_resueltos = enrich_lookup_con_preferidos(
            database,
            preferred_foods=["Cornflakes"],
            full_food_lookup=lookup_inicial,
        )

    # El alimento debe haber sido inyectado
    assert FAKE_CORNFLAKES["code"] in lookup_inicial, (
        "El código de cornflakes debe estar en full_food_lookup tras el enriquecimiento"
    )
    # No debe quedar como no resuelto
    assert "Cornflakes" not in no_resueltos
    # Spoonacular debe haber sido llamado
    mock_spoon.assert_called()


# ── Test 2: Dátiles → dates resuelto externamente ────────────────────────────

def test_datiles_no_local_se_inyecta_como_dates():
    """Si 'Dátiles' no está en el lookup (ni 'dates' como código interno),
    la resolución externa devuelve el alimento y se inyecta en el lookup."""
    lookup_inicial: dict = {}
    database = MagicMock()

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        return_value=FAKE_DATES,
    ):
        no_resueltos = enrich_lookup_con_preferidos(
            database,
            preferred_foods=["Dátiles"],
            full_food_lookup=lookup_inicial,
        )

    assert FAKE_DATES["code"] in lookup_inicial, (
        "El food de dátiles/dates debe estar en full_food_lookup"
    )
    assert "Dátiles" not in no_resueltos


def test_lookup_contiene_dates_y_es_buscable_tras_inyeccion():
    """Tras inyectar el food de dates, buscar_alimentos_por_nombre('dátiles', lookup)
    debe encontrar el alimento."""
    lookup: dict = {}
    database = MagicMock()

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        return_value=FAKE_DATES,
    ):
        enrich_lookup_con_preferidos(database, preferred_foods=["Dátiles"], full_food_lookup=lookup)

    with _PATCH_ML:
        candidatos = buscar_alimentos_por_nombre("Dátiles", lookup)

    assert candidatos, (
        "Tras inyectar el food de dates, 'Dátiles' debe encontrarse en el lookup"
    )


# ── Test 3: preferred_foods=['Cornflakes'] → disponible antes del solver ──────

def test_cornflakes_disponible_en_lookup_antes_del_anclaje():
    """Con preferred_foods=['Cornflakes'], el alimento debe estar en full_food_lookup
    antes de que el resolver de anclas o el solver sean invocados."""
    lookup: dict = {}
    database = MagicMock()

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        return_value=FAKE_CORNFLAKES,
    ):
        enrich_lookup_con_preferidos(database, preferred_foods=["Cornflakes"], full_food_lookup=lookup)

    assert FAKE_CORNFLAKES["code"] in lookup
    # El alimento debe tener todos los campos necesarios para el solver
    food = lookup[FAKE_CORNFLAKES["code"]]
    for campo in ("protein_grams", "fat_grams", "carb_grams", "reference_amount",
                  "max_quantity", "min_quantity", "default_quantity", "reference_unit"):
        assert campo in food, f"Campo requerido '{campo}' no encontrado en el food inyectado"


# ── Test 4: preferred_foods=['Dátiles', 'Cornflakes'] → ambos participan ──────

def test_datiles_y_cornflakes_ambos_inyectados():
    """Con dos preferidos que no existen localmente, ambos deben inyectarse en el lookup."""
    lookup: dict = {}
    database = MagicMock()

    def _mock_spoonacular(db, termino):
        if "corn" in termino.lower() or termino.lower() == "cornflakes":
            return FAKE_CORNFLAKES
        if "date" in termino.lower() or "datil" in termino.lower():
            return FAKE_DATES
        return None

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        side_effect=_mock_spoonacular,
    ):
        no_resueltos = enrich_lookup_con_preferidos(
            database,
            preferred_foods=["Dátiles", "Cornflakes"],
            full_food_lookup=lookup,
        )

    assert FAKE_CORNFLAKES["code"] in lookup, "Cornflakes debe estar en el lookup"
    assert FAKE_DATES["code"] in lookup, "Dates debe estar en el lookup"
    assert len(no_resueltos) == 0, f"No deben quedar preferidos sin resolver: {no_resueltos}"


# ── Test 5: alimento no resuelto → no_resueltos sin romper la generación ──────

def test_alimento_no_encontrado_queda_en_no_resueltos():
    """Si un alimento preferido no puede resolverse en ninguna fuente,
    aparece en la lista devuelta pero no lanza excepción."""
    lookup: dict = {}
    database = MagicMock()

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        return_value=None,  # Spoonacular no encuentra nada
    ), patch(
        "app.services.preferred_food_resolver.search_internal_food",
        return_value=[],    # Catálogo interno tampoco
    ):
        no_resueltos = enrich_lookup_con_preferidos(
            database,
            preferred_foods=["xyzzy_alimento_inventado"],
            full_food_lookup=lookup,
        )

    assert "xyzzy_alimento_inventado" in no_resueltos
    assert len(lookup) == 0, "No debe añadirse nada al lookup si no hay resolución"


def test_preferido_parcialmente_resuelto_no_bloquea_generacion():
    """Si solo uno de dos preferidos se resuelve, el otro queda en no_resueltos
    pero la función completa sin excepción."""
    lookup: dict = {}
    database = MagicMock()

    def _mock_spoonacular(db, termino):
        if "corn" in termino.lower() or termino.lower() == "cornflakes":
            return FAKE_CORNFLAKES
        return None

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        side_effect=_mock_spoonacular,
    ), patch(
        "app.services.preferred_food_resolver.search_internal_food",
        return_value=[],
    ):
        no_resueltos = enrich_lookup_con_preferidos(
            database,
            preferred_foods=["Cornflakes", "xyzzy_inexistente"],
            full_food_lookup=lookup,
        )

    assert FAKE_CORNFLAKES["code"] in lookup, "Cornflakes sí debe inyectarse"
    assert "xyzzy_inexistente" in no_resueltos, "El no-resuelto debe estar en la lista"
    assert "Cornflakes" not in no_resueltos


# ── Test 6: alimento ya presente → no se llama a Spoonacular ─────────────────

def test_alimento_ya_en_lookup_no_llama_spoonacular():
    """Si el preferido ya existe en full_food_lookup, no se llama a Spoonacular."""
    from app.services.food_catalog_service import GENERIC_DEFAULT_QUANTITY, GENERIC_MAX_QUANTITY, GENERIC_MIN_QUANTITY, GENERIC_STEP
    oats_food = {
        "code": "oats",
        "name": "Oats",
        "category": "cereales",
        "protein_grams": 13.0, "fat_grams": 7.0, "carb_grams": 66.0,
        "reference_amount": 100.0, "grams_per_reference": 100.0,
        "reference_unit": "g",
        "default_quantity": GENERIC_DEFAULT_QUANTITY,
        "min_quantity": GENERIC_MIN_QUANTITY,
        "max_quantity": GENERIC_MAX_QUANTITY,
        "step": GENERIC_STEP,
        "suitable_meals": ["early"],
        "preference_labels": ["oats", "avena", "rolled oats"],
        "aliases": ["avena", "oats", "rolled oats"],
        "dietary_flags": [], "allergy_flags": [], "tags": [],
    }
    lookup = {"oats": oats_food}
    database = MagicMock()

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
    ) as mock_spoon:
        enrich_lookup_con_preferidos(
            database,
            preferred_foods=["avena"],  # 'avena' matchea 'oats' via alias
            full_food_lookup=lookup,
        )

    mock_spoon.assert_not_called()


# ── Test 7: Spoonacular lanza excepción → se captura sin propagar ─────────────

def test_spoonacular_error_no_propaga():
    """Si search_spoonacular_food lanza una excepción, enrich_lookup no la propaga."""
    lookup: dict = {}
    database = MagicMock()

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
        side_effect=RuntimeError("API no disponible"),
    ), patch(
        "app.services.preferred_food_resolver.search_internal_food",
        return_value=[],
    ):
        no_resueltos = enrich_lookup_con_preferidos(
            database,
            preferred_foods=["Cornflakes"],
            full_food_lookup=lookup,
        )

    # No debe propagarse la excepción; el alimento queda como no resuelto
    assert "Cornflakes" in no_resueltos
    assert len(lookup) == 0


# ── Test 8: database=None → skip Spoonacular, queda en no_resueltos ──────────

def test_sin_database_no_llama_spoonacular():
    """Si database es None (entorno de test sin MongoDB), no se intenta Spoonacular."""
    lookup: dict = {}

    with _PATCH_ML, patch(
        "app.services.preferred_food_resolver.search_spoonacular_food",
    ) as mock_spoon, patch(
        "app.services.preferred_food_resolver.search_internal_food",
        return_value=[],
    ):
        no_resueltos = enrich_lookup_con_preferidos(
            None,  # database=None
            preferred_foods=["Cornflakes"],
            full_food_lookup=lookup,
        )

    mock_spoon.assert_not_called()
    assert "Cornflakes" in no_resueltos
