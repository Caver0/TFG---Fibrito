"""Thin Spoonacular client focused on low-volume ingredient lookups."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.utils.normalization import translate_food_query_for_search

_quota_blocked_until: datetime | None = None
_last_error_message: str | None = None


class SpoonacularError(Exception):
    """Base Spoonacular integration error."""


class SpoonacularUnavailableError(SpoonacularError):
    """Raised when Spoonacular is not configured or temporarily unavailable."""


class SpoonacularQuotaExceededError(SpoonacularUnavailableError):
    """Raised when Spoonacular quota is exhausted."""


def _mark_last_error(message: str | None) -> None:
    global _last_error_message
    _last_error_message = message


def _set_quota_blocked_until(value: datetime | None) -> None:
    global _quota_blocked_until
    _quota_blocked_until = value


def _get_next_utc_midnight(now: datetime) -> datetime:
    return datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1)


def get_spoonacular_status() -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(UTC)
    blocked_until = _quota_blocked_until if _quota_blocked_until and _quota_blocked_until > now else None

    return {
        "spoonacular_enabled": settings.spoonacular_enabled,
        "spoonacular_temporarily_blocked": blocked_until is not None,
        "quota_blocked_until": blocked_until,
        "last_error": _last_error_message,
    }


def _request_json(path: str, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, str]]:
    settings = get_settings()
    if not settings.spoonacular_enabled:
        raise SpoonacularUnavailableError("Spoonacular API key is not configured")

    status = get_spoonacular_status()
    if status["spoonacular_temporarily_blocked"]:
        raise SpoonacularUnavailableError("Spoonacular calls are temporarily suspended")

    query_params = {
        "apiKey": settings.spoonacular_api_key,
        **(params or {}),
    }
    request_url = f"{settings.spoonacular_base_url}{path}?{urlencode(query_params, doseq=True)}"
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.spoonacular_user_agent,
        },
    )

    try:
        with urlopen(request, timeout=settings.spoonacular_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            response_headers = {key: value for key, value in response.headers.items()}
            _set_quota_blocked_until(None)
            _mark_last_error(None)
            return payload, response_headers
    except HTTPError as exc:
        now = datetime.now(UTC)
        if exc.code == 402:
            _set_quota_blocked_until(_get_next_utc_midnight(now))
            _mark_last_error("Spoonacular daily quota exhausted")
            raise SpoonacularQuotaExceededError("Spoonacular daily quota exhausted") from exc
        if exc.code == 429:
            cooldown = timedelta(seconds=settings.spoonacular_rate_limit_cooldown_seconds)
            _set_quota_blocked_until(now + cooldown)
            _mark_last_error("Spoonacular rate limit reached")
            raise SpoonacularUnavailableError("Spoonacular rate limit reached") from exc

        error_body = exc.read().decode("utf-8", errors="ignore")
        _mark_last_error(f"Spoonacular request failed with HTTP {exc.code}")
        raise SpoonacularError(f"Spoonacular request failed with HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        _mark_last_error("Spoonacular connection failed")
        raise SpoonacularUnavailableError("Spoonacular connection failed") from exc


def autocomplete_ingredients(query: str, number: int = 5) -> list[dict[str, Any]]:
    # Traducir el término al inglés antes de enviarlo a Spoonacular,
    # ya que la API opera principalmente en inglés.
    query_en = translate_food_query_for_search(query)
    payload, _ = _request_json(
        "/food/ingredients/autocomplete",
        {
            "query": query_en,
            "number": max(1, min(number, 10)),
            "metaInformation": True,
        },
    )
    return list(payload)


def search_ingredients(query: str, number: int = 10) -> list[dict[str, Any]]:
    # Traducir el término al inglés antes de enviarlo a Spoonacular.
    query_en = translate_food_query_for_search(query)
    payload, _ = _request_json(
        "/food/ingredients/search",
        {
            "query": query_en,
            "number": max(1, min(number, 10)),
            "metaInformation": False,
        },
    )
    return list(payload.get("results", []))


def get_ingredient_information(
    ingredient_id: int,
    *,
    amount: float | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if amount is not None:
        params["amount"] = amount
    if unit:
        params["unit"] = unit

    payload, _ = _request_json(
        f"/food/ingredients/{ingredient_id}/information",
        params,
    )
    return dict(payload)
