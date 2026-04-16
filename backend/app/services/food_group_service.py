"""Shared helpers to infer the functional group of a food item."""
from __future__ import annotations

from typing import Any


VALID_FUNCTIONAL_GROUPS = {"protein", "carb", "fat", "fruit", "vegetable", "dairy", "other"}


def derive_functional_group(food: dict[str, Any]) -> str:
    explicit_group = str(food.get("functional_group") or "").strip().lower()
    if explicit_group in VALID_FUNCTIONAL_GROUPS:
        return explicit_group

    category = str(food.get("category") or "").strip().lower()
    if category == "proteinas":
        return "protein"
    if category == "carbohidratos":
        return "carb"
    if category == "cereales":
        return "carb"
    if category == "grasas":
        return "fat"
    if category == "frutas":
        return "fruit"
    if category == "vegetales":
        return "vegetable"
    if category == "lacteos":
        protein_grams = float(food.get("protein_grams") or 0.0)
        fat_grams = float(food.get("fat_grams") or 0.0)
        carb_grams = float(food.get("carb_grams") or 0.0)
        if protein_grams >= max(fat_grams, carb_grams):
            return "protein"

        return "dairy"

    return "other"
