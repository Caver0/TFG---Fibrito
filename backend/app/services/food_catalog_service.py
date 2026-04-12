"""Catalog resolution layer: internal foods, persistent cache, and Spoonacular."""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.data.food_catalog import CATALOG_VERSION, FOOD_CATALOG
from app.schemas.food import serialize_food_catalog_item
from app.services.food_preferences_service import annotate_food_compatibility
from app.services.spoonacular_service import (
    SpoonacularError,
    SpoonacularUnavailableError,
    autocomplete_ingredients,
    get_ingredient_information,
    get_spoonacular_status,
    search_ingredients,
)
from app.utils.normalization import build_food_aliases, normalize_food_name

INTERNAL_FOOD_SOURCE = "internal_catalog"
LOCAL_CACHE_FOOD_SOURCE = "local_cache"
SPOONACULAR_FOOD_SOURCE = "spoonacular"
DEFAULT_EXTERNAL_REFERENCE_AMOUNT = 100.0
DEFAULT_EXTERNAL_REFERENCE_UNIT = "g"
GENERIC_DEFAULT_QUANTITY = 100.0
GENERIC_MIN_QUANTITY = 50.0
GENERIC_MAX_QUANTITY = 350.0
GENERIC_STEP = 5.0
MACRO_CALORIE_FACTORS = {
    "protein_grams": 4.0,
    "fat_grams": 9.0,
    "carb_grams": 4.0,
}
NUTRIENT_NAME_MAP = {
    "calories": "Calories",
    "protein_grams": "Protein",
    "fat_grams": "Fat",
    "carb_grams": "Carbohydrates",
}


def _build_resolution_summary(
    *,
    settings,
    resolution_details: list[dict[str, Any]],
) -> dict[str, Any]:
    spoonacular_attempts = sum(len(detail.get("attempted_queries", [])) for detail in resolution_details)
    spoonacular_hits = sum(int(detail["final_source"] == SPOONACULAR_FOOD_SOURCE) for detail in resolution_details)
    cache_hits = sum(int(detail["final_source"] == LOCAL_CACHE_FOOD_SOURCE) for detail in resolution_details)
    internal_fallbacks = sum(int(detail["final_source"] == INTERNAL_FOOD_SOURCE) for detail in resolution_details)

    return {
        "catalog_source_strategy": settings.food_resolution_strategy,
        "spoonacular_attempted": spoonacular_attempts > 0,
        "spoonacular_attempts": spoonacular_attempts,
        "spoonacular_hits": spoonacular_hits,
        "cache_hits": cache_hits,
        "internal_fallbacks": internal_fallbacks,
        "resolved_foods_count": len(resolution_details),
    }


def calculate_macro_calories(protein_grams: float, fat_grams: float, carb_grams: float) -> float:
    return (
        (protein_grams * MACRO_CALORIE_FACTORS["protein_grams"])
        + (fat_grams * MACRO_CALORIE_FACTORS["fat_grams"])
        + (carb_grams * MACRO_CALORIE_FACTORS["carb_grams"])
    )


def _infer_food_category(name: str, protein_grams: float, fat_grams: float, carb_grams: float) -> str:
    normalized_name = normalize_food_name(name)
    if any(token in normalized_name for token in ("oil", "aceite", "nuts", "aguacate", "avocado")):
        return "grasas"
    if protein_grams >= max(fat_grams, carb_grams) and protein_grams >= 8:
        return "proteinas"
    if carb_grams >= max(protein_grams, fat_grams):
        if any(token in normalized_name for token in ("banana", "apple", "orange", "fruit", "platano", "fruta")):
            return "frutas"
        return "carbohidratos"
    if any(token in normalized_name for token in ("milk", "yogurt", "cheese", "leche", "yogur", "queso")):
        return "lacteos"
    return "otros"


def _build_external_food_code(name: str, spoonacular_id: int | None = None) -> str:
    base_code = normalize_food_name(name).replace(" ", "_") or "food"
    if spoonacular_id is not None:
        return f"spoonacular_{base_code}_{spoonacular_id}"

    return f"spoonacular_{base_code}"


def _extract_nutrient_amounts(nutrients: list[dict[str, Any]]) -> dict[str, float]:
    extracted_values = {field_name: 0.0 for field_name in NUTRIENT_NAME_MAP}

    for field_name, nutrient_name in NUTRIENT_NAME_MAP.items():
        matched_nutrient = next(
            (
                nutrient
                for nutrient in nutrients
                if normalize_food_name(str(nutrient.get("name", ""))) == normalize_food_name(nutrient_name)
            ),
            None,
        )
        if matched_nutrient:
            extracted_values[field_name] = float(matched_nutrient.get("amount", 0.0))

    extracted_values["calories"] = calculate_macro_calories(
        extracted_values["protein_grams"],
        extracted_values["fat_grams"],
        extracted_values["carb_grams"],
    )
    return extracted_values


def _build_internal_food_entry(food: dict[str, Any]) -> dict[str, Any]:
    normalized_name = normalize_food_name(food["name"])
    aliases = build_food_aliases(
        food["name"],
        food["code"].replace("_", " "),
        *(food.get("aliases") or []),
    )

    return annotate_food_compatibility({
        **deepcopy(food),
        "internal_code": food["code"],
        "normalized_name": normalized_name,
        "original_name": food["name"],
        "source": INTERNAL_FOOD_SOURCE,
        "origin_source": INTERNAL_FOOD_SOURCE,
        "spoonacular_id": None,
        "image": None,
        "matched_query": None,
        "aliases": aliases,
    })


def _serialize_cached_food(document: dict[str, Any]) -> dict[str, Any]:
    serialized_food = serialize_food_catalog_item(document).model_dump()
    serialized_food["name"] = serialized_food["display_name"]
    serialized_food["source"] = LOCAL_CACHE_FOOD_SOURCE
    serialized_food["aliases"] = document.get("aliases", [])
    serialized_food["external_search_enabled"] = False
    return annotate_food_compatibility(serialized_food)


def _build_spoonacular_request_reference(food: dict[str, Any] | None) -> tuple[float, str | None]:
    if not food:
        return DEFAULT_EXTERNAL_REFERENCE_AMOUNT, DEFAULT_EXTERNAL_REFERENCE_UNIT

    if food["reference_unit"] in {"g", "ml"}:
        return float(food["reference_amount"]), str(food["reference_unit"])

    return DEFAULT_EXTERNAL_REFERENCE_AMOUNT, DEFAULT_EXTERNAL_REFERENCE_UNIT


def _score_external_candidate(candidate: dict[str, Any], aliases: list[str]) -> tuple[int, int]:
    normalized_candidate_name = normalize_food_name(str(candidate.get("name", "")))
    if normalized_candidate_name in aliases:
        return (3, -len(normalized_candidate_name))
    if any(alias in normalized_candidate_name or normalized_candidate_name in alias for alias in aliases):
        return (2, -len(normalized_candidate_name))

    return (1, -len(normalized_candidate_name))


def _select_best_spoonacular_candidate(
    candidates: list[dict[str, Any]],
    aliases: list[str],
) -> dict[str, Any] | None:
    if not candidates:
        return None

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: _score_external_candidate(candidate, aliases),
        reverse=True,
    )
    return ranked_candidates[0]


def _merge_spoonacular_candidates(*candidate_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_candidates: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for candidate_group in candidate_groups:
        for candidate in candidate_group:
            candidate_id = candidate.get("id")
            if candidate_id is None:
                continue

            normalized_candidate_id = int(candidate_id)
            if normalized_candidate_id in seen_ids:
                continue

            seen_ids.add(normalized_candidate_id)
            merged_candidates.append(candidate)

    return merged_candidates


def _build_spoonacular_search_queries(internal_food: dict[str, Any]) -> list[str]:
    return build_food_aliases(
        *(internal_food.get("spoonacular_queries") or []),
        internal_food["name"],
        *internal_food.get("aliases", []),
    )


def _normalize_spoonacular_food(
    ingredient_information: dict[str, Any],
    *,
    matched_query: str,
    internal_food: dict[str, Any] | None = None,
) -> dict[str, Any]:
    amount, unit = _build_spoonacular_request_reference(internal_food)
    internal_aliases = internal_food.get("aliases", []) if internal_food else []
    nutrients = _extract_nutrient_amounts(
        ingredient_information.get("nutrition", {}).get("nutrients", [])
    )
    normalized_name = normalize_food_name(
        ingredient_information.get("name")
        or ingredient_information.get("originalName")
        or matched_query
    )
    grams_per_reference = ingredient_information.get("nutrition", {}).get("weightPerServing", {}).get("amount")
    if not grams_per_reference:
        if unit == "g":
            grams_per_reference = amount
        elif internal_food:
            grams_per_reference = internal_food.get("grams_per_reference", amount)
        else:
            grams_per_reference = amount

    grams_per_reference = float(grams_per_reference)
    display_name = internal_food["name"] if internal_food else str(
        ingredient_information.get("name")
        or ingredient_information.get("originalName")
        or matched_query
    )
    category = internal_food["category"] if internal_food else _infer_food_category(
        display_name,
        nutrients["protein_grams"],
        nutrients["fat_grams"],
        nutrients["carb_grams"],
    )
    code = internal_food["code"] if internal_food else _build_external_food_code(
        display_name,
        ingredient_information.get("id"),
    )

    return annotate_food_compatibility({
        "code": code,
        "internal_code": internal_food["code"] if internal_food else None,
        "normalized_name": normalized_name,
        "original_name": str(
            ingredient_information.get("originalName")
            or ingredient_information.get("name")
            or matched_query
        ),
        "name": display_name,
        "display_name": display_name,
        "category": category,
        "source": SPOONACULAR_FOOD_SOURCE,
        "origin_source": SPOONACULAR_FOOD_SOURCE,
        "spoonacular_id": ingredient_information.get("id"),
        "reference_amount": float(internal_food["reference_amount"]) if internal_food else amount,
        "reference_unit": str(internal_food["reference_unit"]) if internal_food else (unit or DEFAULT_EXTERNAL_REFERENCE_UNIT),
        "grams_per_reference": float(grams_per_reference or (internal_food["grams_per_reference"] if internal_food else amount)),
        "calories": nutrients["calories"],
        "protein_grams": nutrients["protein_grams"],
        "fat_grams": nutrients["fat_grams"],
        "carb_grams": nutrients["carb_grams"],
        "default_quantity": float(internal_food["default_quantity"]) if internal_food else GENERIC_DEFAULT_QUANTITY,
        "min_quantity": float(internal_food["min_quantity"]) if internal_food else GENERIC_MIN_QUANTITY,
        "max_quantity": float(internal_food["max_quantity"]) if internal_food else GENERIC_MAX_QUANTITY,
        "step": float(internal_food["step"]) if internal_food else GENERIC_STEP,
        "matched_query": matched_query,
        "image": ingredient_information.get("image"),
        "aliases": build_food_aliases(
            display_name,
            matched_query,
            ingredient_information.get("name", ""),
            ingredient_information.get("originalName", ""),
            *internal_aliases,
        ),
    })


def get_food_catalog() -> list[dict[str, Any]]:
    return [_build_internal_food_entry(food) for food in FOOD_CATALOG]


def get_food_catalog_version() -> str:
    return CATALOG_VERSION


def get_internal_food_lookup() -> dict[str, dict[str, Any]]:
    return {food["code"]: food for food in get_food_catalog()}


def get_food_lookup() -> dict[str, dict[str, Any]]:
    return get_internal_food_lookup()


def get_foods_by_codes(codes: list[str]) -> list[dict[str, Any]]:
    lookup = get_internal_food_lookup()
    return [lookup[code] for code in codes if code in lookup]


def get_cached_food(
    database,
    *,
    internal_code: str | None = None,
    normalized_names: list[str] | None = None,
    spoonacular_id: int | None = None,
) -> dict[str, Any] | None:
    collection = database.foods_catalog
    if spoonacular_id is not None:
        document = collection.find_one({"spoonacular_id": spoonacular_id})
        if document:
            return _serialize_cached_food(document)

    if internal_code:
        document = collection.find_one({"internal_code": internal_code})
        if document:
            return _serialize_cached_food(document)

    normalized_names = normalized_names or []
    for normalized_name in normalized_names:
        document = collection.find_one({"normalized_name": normalized_name})
        if document:
            return _serialize_cached_food(document)

        document = collection.find_one({"aliases": normalized_name})
        if document:
            return _serialize_cached_food(document)

    return None


def cache_spoonacular_food(database, food: dict[str, Any]) -> dict[str, Any]:
    collection = database.foods_catalog
    now = datetime.now(UTC)
    document = {
        **deepcopy(food),
        "display_name": food["name"],
        "source": SPOONACULAR_FOOD_SOURCE,
        "origin_source": SPOONACULAR_FOOD_SOURCE,
        "updated_at": now,
    }

    existing_document = None
    if food.get("spoonacular_id") is not None:
        existing_document = collection.find_one({"spoonacular_id": food["spoonacular_id"]})

    if existing_document is None and food.get("internal_code"):
        existing_document = collection.find_one({"internal_code": food["internal_code"]})

    if existing_document is None:
        existing_document = collection.find_one({"normalized_name": food["normalized_name"]})

    if existing_document:
        document["created_at"] = existing_document.get("created_at", now)
        collection.update_one(
            {"_id": existing_document["_id"]},
            {"$set": document},
        )
        cached_document = collection.find_one({"_id": existing_document["_id"]})
    else:
        document["created_at"] = now
        inserted = collection.insert_one(document)
        cached_document = collection.find_one({"_id": inserted.inserted_id})

    return _serialize_cached_food(cached_document)


def _fetch_spoonacular_food(
    *,
    query: str,
    internal_food: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    internal_aliases = internal_food.get("aliases", []) if internal_food else []
    aliases = build_food_aliases(
        query,
        *internal_aliases,
    )
    candidates = _merge_spoonacular_candidates(
        autocomplete_ingredients(query, number=5),
        search_ingredients(query, number=5),
    )
    best_candidate = _select_best_spoonacular_candidate(candidates, aliases)
    if not best_candidate:
        return None

    amount, unit = _build_spoonacular_request_reference(internal_food)
    ingredient_information = get_ingredient_information(
        int(best_candidate["id"]),
        amount=amount,
        unit=unit,
    )
    return _normalize_spoonacular_food(
        ingredient_information,
        matched_query=query,
        internal_food=internal_food,
    )


def search_internal_food(query: str, limit: int = 10) -> list[dict[str, Any]]:
    normalized_query = normalize_food_name(query)
    if not normalized_query:
        return []

    matched_foods = [
        food
        for food in get_food_catalog()
        if normalized_query in food["normalized_name"]
        or any(normalized_query in alias for alias in food.get("aliases", []))
    ]
    return matched_foods[:limit]


def search_cached_foods(database, query: str, limit: int = 10) -> list[dict[str, Any]]:
    normalized_query = normalize_food_name(query)
    if not normalized_query:
        return []

    collection = database.foods_catalog
    pattern = re.escape(normalized_query)
    cursor = collection.find(
        {
            "$or": [
                {"normalized_name": {"$regex": pattern}},
                {"aliases": normalized_query},
            ]
        }
    ).sort([("updated_at", -1)]).limit(limit)

    return [_serialize_cached_food(document) for document in cursor]


def search_spoonacular_food(database, query: str) -> dict[str, Any] | None:
    normalized_query = normalize_food_name(query)
    cached_food = get_cached_food(database, normalized_names=[normalized_query])
    if cached_food:
        return cached_food

    live_food = _fetch_spoonacular_food(query=query)
    if not live_food:
        return None

    cached_food = cache_spoonacular_food(database, live_food)
    return {
        **cached_food,
        "source": SPOONACULAR_FOOD_SOURCE,
    }


def resolve_food_candidate(
    database,
    internal_food: dict[str, Any],
    *,
    allow_external_enrichment: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = get_settings()
    prefer_spoonacular = settings.prefer_spoonacular_foods
    resolution_metadata = {
        "food_code": internal_food["code"],
        "food_name": internal_food["name"],
        "spoonacular_attempted": False,
        "attempted_queries": [],
        "matched_query": None,
        "final_source": INTERNAL_FOOD_SOURCE,
        "origin_source": INTERNAL_FOOD_SOURCE,
    }

    cached_food = get_cached_food(
        database,
        internal_code=internal_food["code"],
        normalized_names=internal_food.get("aliases", []),
    )
    if cached_food:
        resolution_metadata["final_source"] = LOCAL_CACHE_FOOD_SOURCE
        resolution_metadata["origin_source"] = cached_food.get("origin_source", SPOONACULAR_FOOD_SOURCE)
        return {
            **cached_food,
            "name": internal_food["name"],
            "display_name": internal_food["name"],
        }, resolution_metadata

    can_use_external = (
        allow_external_enrichment
        and (prefer_spoonacular or settings.spoonacular_generation_enrichment_enabled)
        and (prefer_spoonacular or internal_food.get("external_search_enabled", True))
    )
    if not can_use_external:
        return internal_food, resolution_metadata

    if prefer_spoonacular:
        search_queries = _build_spoonacular_search_queries(internal_food)
    else:
        search_queries = internal_food.get("spoonacular_queries") or [internal_food["name"]]

    for query in search_queries:
        resolution_metadata["spoonacular_attempted"] = True
        resolution_metadata["attempted_queries"].append(query)
        try:
            live_food = _fetch_spoonacular_food(query=query, internal_food=internal_food)
        except SpoonacularUnavailableError as exc:
            resolution_metadata["spoonacular_error"] = str(exc)
            return internal_food, resolution_metadata
        except SpoonacularError as exc:
            resolution_metadata["spoonacular_error"] = str(exc)
            continue

        if not live_food:
            continue

        cached_food = cache_spoonacular_food(database, live_food)
        resolution_metadata["matched_query"] = query
        resolution_metadata["final_source"] = SPOONACULAR_FOOD_SOURCE
        resolution_metadata["origin_source"] = SPOONACULAR_FOOD_SOURCE
        resolution_metadata.pop("spoonacular_error", None)
        return {
            **cached_food,
            "name": internal_food["name"],
            "display_name": internal_food["name"],
            "source": SPOONACULAR_FOOD_SOURCE,
        }, resolution_metadata

    return internal_food, resolution_metadata


def resolve_foods_by_codes(
    database,
    food_codes: list[str],
    *,
    allow_external_enrichment: bool = True,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    internal_lookup = get_internal_food_lookup()
    resolved_lookup: dict[str, dict[str, Any]] = {}
    used_sources: set[str] = set()
    resolution_details: list[dict[str, Any]] = []
    settings = get_settings()

    for code in food_codes:
        internal_food = internal_lookup[code]
        resolved_food, resolution_metadata = resolve_food_candidate(
            database,
            internal_food,
            allow_external_enrichment=allow_external_enrichment,
        )
        resolved_lookup[code] = resolved_food
        used_sources.add(resolved_food.get("source", INTERNAL_FOOD_SOURCE))
        resolution_details.append(resolution_metadata)

    ordered_sources = [
        source
        for source in (INTERNAL_FOOD_SOURCE, LOCAL_CACHE_FOOD_SOURCE, SPOONACULAR_FOOD_SOURCE)
        if source in used_sources
    ]
    if not ordered_sources:
        ordered_sources = [INTERNAL_FOOD_SOURCE]

    return resolved_lookup, {
        "food_data_source": ordered_sources[0] if len(ordered_sources) == 1 else "mixed",
        "food_data_sources": ordered_sources,
        "food_catalog_version": CATALOG_VERSION,
        **_build_resolution_summary(
            settings=settings,
            resolution_details=resolution_details,
        ),
    }


def merge_internal_and_external_food_sources(
    database,
    query: str,
    *,
    limit: int = 10,
    include_external: bool = False,
) -> list[dict[str, Any]]:
    merged_foods: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add_food(food: dict[str, Any]) -> None:
        dedupe_key = food.get("internal_code") or food["normalized_name"]
        if dedupe_key in seen_keys or len(merged_foods) >= limit:
            return

        merged_foods.append(food)
        seen_keys.add(dedupe_key)

    for food in search_cached_foods(database, query, limit=limit):
        add_food(food)

    for food in search_internal_food(query, limit=limit):
        add_food(food)

    if include_external and len(merged_foods) < limit:
        try:
            external_food = search_spoonacular_food(database, query)
        except SpoonacularUnavailableError:
            external_food = None
        except SpoonacularError:
            external_food = None

        if external_food:
            add_food(external_food)

    return merged_foods[:limit]


def get_food_catalog_status(database) -> dict[str, Any]:
    settings = get_settings()
    spoonacular_status = get_spoonacular_status()
    return {
        "internal_foods_count": len(FOOD_CATALOG),
        "cached_foods_count": database.foods_catalog.count_documents({}),
        "prefer_spoonacular_foods": settings.prefer_spoonacular_foods,
        "catalog_source_strategy": settings.food_resolution_strategy,
        **spoonacular_status,
    }
