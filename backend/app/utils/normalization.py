"""Utility helpers to normalize food names across local and external sources."""
from __future__ import annotations

import re
import unicodedata

_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_food_name(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    cleaned_value = _NON_ALPHANUMERIC_PATTERN.sub(" ", ascii_value)
    return _WHITESPACE_PATTERN.sub(" ", cleaned_value).strip()


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
