"""Temporary diagnostics storage for diet v2 audits."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_last_generation_diagnostics: dict[str, Any] | None = None
_last_regeneration_diagnostics: dict[str, Any] | None = None


def set_last_generation_diagnostics(payload: dict[str, Any] | None) -> None:
    global _last_generation_diagnostics
    _last_generation_diagnostics = deepcopy(payload) if payload is not None else None


def get_last_generation_diagnostics() -> dict[str, Any] | None:
    return deepcopy(_last_generation_diagnostics) if _last_generation_diagnostics is not None else None


def set_last_regeneration_diagnostics(payload: dict[str, Any] | None) -> None:
    global _last_regeneration_diagnostics
    _last_regeneration_diagnostics = deepcopy(payload) if payload is not None else None


def get_last_regeneration_diagnostics() -> dict[str, Any] | None:
    return deepcopy(_last_regeneration_diagnostics) if _last_regeneration_diagnostics is not None else None
