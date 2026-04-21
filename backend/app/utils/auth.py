"""Authentication helpers shared across schemas, routes, and services."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

AUTH_PROVIDER_PASSWORD = "password"
SUPPORTED_AUTH_PROVIDERS = {AUTH_PROVIDER_PASSWORD}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_name(name: str | None, fallback_email: str) -> str:
    candidate = (name or "").strip()
    if candidate:
        return candidate

    local_part = fallback_email.split("@", maxsplit=1)[0]
    readable_name = " ".join(
        segment.capitalize()
        for segment in local_part.replace(".", " ").replace("_", " ").replace("-", " ").split()
        if segment
    )
    return readable_name or fallback_email


def build_default_food_preferences() -> dict[str, list[str]]:
    return {
        "preferred_foods": [],
        "disliked_foods": [],
        "dietary_restrictions": [],
        "allergies": [],
    }


def build_user_document_base(*, name: str, email: str) -> dict[str, Any]:
    return {
        "name": normalize_name(name, email),
        "email": normalize_email(email),
        "password_hash": None,
        "auth_providers": [],
        "reset_password_token_hash": None,
        "reset_password_expires_at": None,
        "reset_password_requested_at": None,
        "created_at": datetime.now(timezone.utc),
        "age": None,
        "sex": None,
        "height": None,
        "current_weight": None,
        "training_days_per_week": None,
        "goal": None,
        "target_calories": None,
        "food_preferences": build_default_food_preferences(),
    }


def derive_auth_providers(document: dict[str, Any]) -> list[str]:
    providers: list[str] = []
    for provider in document.get("auth_providers") or []:
        if provider in SUPPORTED_AUTH_PROVIDERS and provider not in providers:
            providers.append(provider)

    if document.get("password_hash") and AUTH_PROVIDER_PASSWORD not in providers:
        providers.append(AUTH_PROVIDER_PASSWORD)

    return providers


def merge_auth_provider(document: dict[str, Any], provider: str) -> list[str]:
    providers = derive_auth_providers(document)
    if provider in SUPPORTED_AUTH_PROVIDERS and provider not in providers:
        providers.append(provider)
    return providers


def build_password_reset_clear_fields() -> dict[str, Any]:
    return {
        "reset_password_token_hash": None,
        "reset_password_expires_at": None,
        "reset_password_requested_at": None,
    }
