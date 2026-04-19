"""Resolución e inyección de alimentos preferidos en el lookup de trabajo.

Este módulo resuelve el problema de que los alimentos preferidos del usuario
(ej. 'Cornflakes', 'Dátiles') pueden no existir en el catálogo interno ni en
la base de datos local, haciendo que el sistema de anclas y el solver no puedan
considerarlos como candidatos reales.

Flujo de resolución para cada alimento preferido:
  1. Si ya existe en full_food_lookup (búsqueda por nombre/alias) → nada que hacer.
  2. Si no, buscar en catálogo interno con el texto original y la traducción ES→EN.
  3. Si no, buscar en Spoonacular/caché local (la traducción ES→EN se aplica
     internamente vía autocomplete_ingredients/search_ingredients).
  4. Si se obtiene coincidencia, inyectarla en full_food_lookup antes del anclaje.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.food_catalog_service import search_internal_food, search_spoonacular_food
from app.services.food_preferences_service import buscar_alimentos_por_nombre
from app.utils.normalization import translate_food_query_for_search

logger = logging.getLogger(__name__)

# Número máximo de resultados internos a considerar por término de búsqueda
_MAX_INTERNAL_MATCHES = 3


def enrich_lookup_con_preferidos(
    database: Any,
    preferred_foods: list[str],
    full_food_lookup: dict[str, dict],
) -> list[str]:
    """Garantiza que cada alimento preferido existe en full_food_lookup antes del solver.

    Args:
        database: Conexión a la base de datos MongoDB (puede ser None en tests).
        preferred_foods: Lista de textos de alimentos preferidos del usuario.
        full_food_lookup: Diccionario mutable {code: food_dict} que se enriquece in-place.

    Returns:
        Lista de textos preferidos que no pudieron resolverse en ninguna fuente
        (se usarán para diagnóstico 'no_encontrado' en el resolver de anclas).
    """
    no_resueltos: list[str] = []

    for texto_preferido in preferred_foods:
        # ── Paso 1: ¿ya hay candidatos en el lookup para este texto? ──────────────
        if buscar_alimentos_por_nombre(texto_preferido, full_food_lookup):
            logger.debug("[preferred_resolver] '%s' ya existe en lookup, omitiendo.", texto_preferido)
            continue

        traduccion_en = translate_food_query_for_search(texto_preferido)
        # Construir lista de términos a probar (sin duplicados, orden preferencial)
        terminos = list(dict.fromkeys([texto_preferido, traduccion_en]))

        # ── Paso 2: búsqueda en catálogo interno ──────────────────────────────────
        inyectado = False
        for termino in terminos:
            coincidencias_internas = search_internal_food(termino, limit=_MAX_INTERNAL_MATCHES)
            for food in coincidencias_internas:
                code = food["code"]
                if code not in full_food_lookup:
                    full_food_lookup[code] = food
                    logger.debug(
                        "[preferred_resolver] '%s' → código '%s' inyectado desde catálogo interno.",
                        texto_preferido, code,
                    )
            if coincidencias_internas:
                inyectado = True
                break

        # Verificar si la inyección interna ya resuelve la búsqueda
        if inyectado and buscar_alimentos_por_nombre(texto_preferido, full_food_lookup):
            continue

        # ── Paso 3: resolución externa (Spoonacular o caché local) ────────────────
        if database is None:
            logger.debug("[preferred_resolver] Sin base de datos, omitiendo resolución externa para '%s'.", texto_preferido)
            no_resueltos.append(texto_preferido)
            continue

        food_externo: dict | None = None
        for termino in terminos:
            try:
                food_externo = search_spoonacular_food(database, termino)
                if food_externo:
                    break
            except Exception as exc:
                logger.debug("[preferred_resolver] Error buscando '%s' externamente: %s", termino, exc)

        if food_externo:
            code = food_externo["code"]
            if code not in full_food_lookup:
                full_food_lookup[code] = food_externo
                logger.debug(
                    "[preferred_resolver] '%s' → código '%s' inyectado desde fuente externa.",
                    texto_preferido, code,
                )
        else:
            logger.debug("[preferred_resolver] '%s' no pudo resolverse en ninguna fuente.", texto_preferido)
            no_resueltos.append(texto_preferido)

    return no_resueltos
