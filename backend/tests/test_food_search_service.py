from __future__ import annotations

from unittest.mock import patch

from app.services.food_catalog_service import search_food_sources
from app.services.spoonacular_service import SpoonacularQuotaExceededError


def test_search_food_sources_reports_local_empty_reason_without_external_lookup():
    with patch("app.services.food_catalog_service._build_query_variants", return_value=["mango"]), patch(
        "app.services.food_catalog_service.search_cached_foods",
        return_value=[],
    ), patch(
        "app.services.food_catalog_service.search_internal_food",
        return_value=[],
    ):
        foods, meta = search_food_sources(object(), "mango", include_external=False)

    assert foods == []
    assert meta["cache_matches"] == 0
    assert meta["internal_matches"] == 0
    assert meta["external_attempted"] is False
    assert meta["empty_reason_code"] == "no_local_matches"
    assert "base local" in meta["empty_reason"]


def test_search_food_sources_reports_external_quota_reason():
    with patch("app.services.food_catalog_service._build_query_variants", return_value=["mango"]), patch(
        "app.services.food_catalog_service.search_cached_foods",
        return_value=[],
    ), patch(
        "app.services.food_catalog_service.search_internal_food",
        return_value=[],
    ), patch(
        "app.services.food_catalog_service.search_spoonacular_food",
        side_effect=SpoonacularQuotaExceededError("Spoonacular daily quota exhausted"),
    ):
        foods, meta = search_food_sources(object(), "mango", include_external=True)

    assert foods == []
    assert meta["external_attempted"] is True
    assert meta["external_source"] == "spoonacular"
    assert meta["empty_reason_code"] == "external_quota_unavailable"
    assert "llamadas disponibles" in meta["empty_reason"]


def test_search_food_sources_reports_no_matches_when_all_sources_return_empty():
    with patch("app.services.food_catalog_service._build_query_variants", return_value=["mango"]), patch(
        "app.services.food_catalog_service.search_cached_foods",
        return_value=[],
    ), patch(
        "app.services.food_catalog_service.search_internal_food",
        return_value=[],
    ), patch(
        "app.services.food_catalog_service.search_spoonacular_food",
        return_value=None,
    ):
        foods, meta = search_food_sources(object(), "mango", include_external=True)

    assert foods == []
    assert meta["external_attempted"] is True
    assert meta["empty_reason_code"] == "no_matches_any_source"
    assert "ninguna fuente" in meta["empty_reason"]
