"""Schemas for catalog foods, cache responses, and Spoonacular status."""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field

FoodSource = Literal["internal_catalog", "local_cache", "spoonacular"]
FoodOriginSource = Literal["internal_catalog", "spoonacular"]
FoodFunctionalGroup = Literal["protein", "carb", "fat", "fruit", "vegetable", "dairy", "other"]
FOOD_PRECISION = Decimal("0.01")


def _round_food_value(value: float | Decimal | None) -> float:
    if value is None:
        value = 0.0

    return float(Decimal(str(value)).quantize(FOOD_PRECISION, rounding=ROUND_HALF_UP))


def _derive_functional_group(document: dict) -> FoodFunctionalGroup:
    explicit_group = str(document.get("functional_group") or "").strip().lower()
    if explicit_group in {"protein", "carb", "fat", "fruit", "vegetable", "dairy", "other"}:
        return explicit_group  # type: ignore[return-value]

    category = str(document.get("category") or "").strip().lower()
    if category == "proteinas":
        return "protein"
    if category == "carbohidratos":
        return "carb"
    if category == "grasas":
        return "fat"
    if category == "frutas":
        return "fruit"
    if category == "vegetales":
        return "vegetable"
    if category == "lacteos":
        return "dairy"

    return "other"


class FoodCatalogItem(BaseModel):
    code: str
    internal_code: str | None = None
    normalized_name: str
    original_name: str
    display_name: str
    category: str
    functional_group: FoodFunctionalGroup = "other"
    source: FoodSource
    origin_source: FoodOriginSource = "internal_catalog"
    spoonacular_id: int | None = None
    reference_amount: float = Field(gt=0)
    reference_unit: str
    grams_per_reference: float = Field(gt=0)
    calories: float = Field(ge=0)
    protein_grams: float = Field(ge=0)
    fat_grams: float = Field(ge=0)
    carb_grams: float = Field(ge=0)
    default_quantity: float = Field(gt=0)
    min_quantity: float = Field(gt=0)
    max_quantity: float = Field(gt=0)
    step: float = Field(gt=0)
    matched_query: str | None = None
    image: str | None = None
    dietary_tags: list[str] = Field(default_factory=list)
    allergen_tags: list[str] = Field(default_factory=list)
    compatibility_notes: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FoodSearchResponse(BaseModel):
    foods: list[FoodCatalogItem]


class FoodCatalogStatusResponse(BaseModel):
    internal_foods_count: int = Field(ge=0)
    cached_foods_count: int = Field(ge=0)
    spoonacular_enabled: bool = False
    spoonacular_temporarily_blocked: bool = False
    prefer_spoonacular_foods: bool = False
    catalog_source_strategy: str = "internal_catalog_with_optional_spoonacular_enrichment"
    quota_blocked_until: datetime | None = None
    last_error: str | None = None


def serialize_food_catalog_item(document: dict) -> FoodCatalogItem:
    return FoodCatalogItem(
        code=document["code"],
        internal_code=document.get("internal_code"),
        normalized_name=document["normalized_name"],
        original_name=document.get("original_name", document.get("name", document["normalized_name"])),
        display_name=document.get("display_name", document.get("name", document["normalized_name"])),
        category=document.get("category", "otros"),
        functional_group=_derive_functional_group(document),
        source=document.get("source", "internal_catalog"),
        origin_source=document.get("origin_source", "internal_catalog"),
        spoonacular_id=document.get("spoonacular_id"),
        reference_amount=_round_food_value(document.get("reference_amount")),
        reference_unit=document.get("reference_unit", "g"),
        grams_per_reference=_round_food_value(document.get("grams_per_reference")),
        calories=_round_food_value(document.get("calories")),
        protein_grams=_round_food_value(document.get("protein_grams")),
        fat_grams=_round_food_value(document.get("fat_grams")),
        carb_grams=_round_food_value(document.get("carb_grams")),
        default_quantity=_round_food_value(document.get("default_quantity")),
        min_quantity=_round_food_value(document.get("min_quantity")),
        max_quantity=_round_food_value(document.get("max_quantity")),
        step=_round_food_value(document.get("step")),
        matched_query=document.get("matched_query"),
        image=document.get("image"),
        dietary_tags=document.get("dietary_tags", []),
        allergen_tags=document.get("allergen_tags", []),
        compatibility_notes=document.get("compatibility_notes", []),
        created_at=document.get("created_at"),
        updated_at=document.get("updated_at"),
    )
