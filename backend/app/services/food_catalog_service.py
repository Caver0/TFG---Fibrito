"""Helpers to access the internal food catalog behind a service boundary."""
from copy import deepcopy

from app.data.food_catalog import CATALOG_VERSION, FOOD_CATALOG


def get_food_catalog() -> list[dict]:
    return [deepcopy(food) for food in FOOD_CATALOG]


def get_food_catalog_version() -> str:
    return CATALOG_VERSION


def get_food_lookup() -> dict[str, dict]:
    return {food["code"]: food for food in get_food_catalog()}


def get_foods_by_codes(codes: list[str]) -> list[dict]:
    lookup = get_food_lookup()
    return [lookup[code] for code in codes if code in lookup]
