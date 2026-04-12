"""Schemas and serialization helpers for food-based daily diets."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TrainingTimeOfDay = Literal["manana", "mediodia", "tarde", "noche"]
PERCENTAGE_PRECISION = Decimal("0.1")
NUTRITION_PRECISION = Decimal("0.1")
FOOD_PRECISION = Decimal("0.01")
DEFAULT_DIET_SOURCE = "internal"
DIET_SOURCE_MAP = {
    "internal_catalog": DEFAULT_DIET_SOURCE,
    "local_cache": "cache",
    "spoonacular": "spoonacular",
    DEFAULT_DIET_SOURCE: DEFAULT_DIET_SOURCE,
    "cache": "cache",
}
DEFAULT_CATALOG_SOURCE_STRATEGY = "internal_catalog_with_optional_spoonacular_enrichment"


def _round_decimal(value: float | Decimal | None, precision: Decimal = NUTRITION_PRECISION) -> float:
    if value is None:
        value = 0.0

    return float(Decimal(str(value)).quantize(precision, rounding=ROUND_HALF_UP))


def _calculate_difference(actual_value: float | Decimal, target_value: float | Decimal) -> float:
    return _round_decimal(Decimal(str(actual_value)) - Decimal(str(target_value)))


def _normalize_diet_source(value: str | None) -> str:
    normalized_value = str(value or "").strip()
    if normalized_value in {"mixed", "legacy_structural"}:
        return normalized_value

    return DIET_SOURCE_MAP.get(normalized_value, DEFAULT_DIET_SOURCE)


def _derive_distribution_percentages(document: dict[str, Any]) -> list[float]:
    explicit_distribution = document.get("distribution_percentages")
    if explicit_distribution:
        return [_round_decimal(value, PERCENTAGE_PRECISION) for value in explicit_distribution]

    meals = document.get("meals", [])
    total_calories = document.get("target_calories")
    if not meals or total_calories in (None, 0):
        return []

    remaining_percentage = Decimal("100.0")
    remaining_calories = Decimal(str(total_calories))
    derived_percentages: list[float] = []

    for index, meal in enumerate(meals):
        meal_calories = Decimal(str(meal.get("target_calories", 0)))
        remaining_slots = len(meals) - index
        if remaining_slots == 1 or remaining_calories == 0:
            percentage = remaining_percentage
        else:
            percentage = (
                (meal_calories / remaining_calories) * remaining_percentage
            ).quantize(PERCENTAGE_PRECISION, rounding=ROUND_HALF_UP)

        derived_percentages.append(float(percentage))
        remaining_percentage -= percentage
        remaining_calories -= meal_calories

    return derived_percentages


def _calculate_food_totals(food_documents: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "calories": _round_decimal(sum(Decimal(str(food.get("calories", 0))) for food in food_documents)),
        "protein_grams": _round_decimal(
            sum(Decimal(str(food.get("protein_grams", 0))) for food in food_documents)
        ),
        "fat_grams": _round_decimal(sum(Decimal(str(food.get("fat_grams", 0))) for food in food_documents)),
        "carb_grams": _round_decimal(sum(Decimal(str(food.get("carb_grams", 0))) for food in food_documents)),
    }


def _build_difference_summary(
    *,
    target_calories: float,
    target_protein_grams: float,
    target_fat_grams: float,
    target_carb_grams: float,
    actual_calories: float,
    actual_protein_grams: float,
    actual_fat_grams: float,
    actual_carb_grams: float,
) -> dict[str, float]:
    return {
        "calorie_difference": _calculate_difference(actual_calories, target_calories),
        "protein_difference": _calculate_difference(actual_protein_grams, target_protein_grams),
        "fat_difference": _calculate_difference(actual_fat_grams, target_fat_grams),
        "carb_difference": _calculate_difference(actual_carb_grams, target_carb_grams),
    }


def _derive_meal_actuals(document: dict[str, Any]) -> dict[str, float]:
    if all(document.get(field_name) is not None for field_name in (
        "actual_calories",
        "actual_protein_grams",
        "actual_fat_grams",
        "actual_carb_grams",
    )):
        return {
            "actual_calories": _round_decimal(document.get("actual_calories")),
            "actual_protein_grams": _round_decimal(document.get("actual_protein_grams")),
            "actual_fat_grams": _round_decimal(document.get("actual_fat_grams")),
            "actual_carb_grams": _round_decimal(document.get("actual_carb_grams")),
        }

    foods = document.get("foods") or []
    if foods:
        totals = _calculate_food_totals(foods)
        return {
            "actual_calories": totals["calories"],
            "actual_protein_grams": totals["protein_grams"],
            "actual_fat_grams": totals["fat_grams"],
            "actual_carb_grams": totals["carb_grams"],
        }

    return {
        "actual_calories": _round_decimal(document.get("target_calories")),
        "actual_protein_grams": _round_decimal(document.get("target_protein_grams")),
        "actual_fat_grams": _round_decimal(document.get("target_fat_grams")),
        "actual_carb_grams": _round_decimal(document.get("target_carb_grams")),
    }


def _derive_meal_differences(document: dict[str, Any], actuals: dict[str, float]) -> dict[str, float]:
    if all(document.get(field_name) is not None for field_name in (
        "calorie_difference",
        "protein_difference",
        "fat_difference",
        "carb_difference",
    )):
        return {
            "calorie_difference": _round_decimal(document.get("calorie_difference")),
            "protein_difference": _round_decimal(document.get("protein_difference")),
            "fat_difference": _round_decimal(document.get("fat_difference")),
            "carb_difference": _round_decimal(document.get("carb_difference")),
        }

    return _build_difference_summary(
        target_calories=_round_decimal(document.get("target_calories")),
        target_protein_grams=_round_decimal(document.get("target_protein_grams")),
        target_fat_grams=_round_decimal(document.get("target_fat_grams")),
        target_carb_grams=_round_decimal(document.get("target_carb_grams")),
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
    )


def _derive_food_data_source(document: dict[str, Any]) -> str:
    explicit_sources = document.get("food_data_sources")
    if explicit_sources:
        normalized_sources = [_normalize_diet_source(source) for source in explicit_sources if source]
        if len(normalized_sources) == 1:
            return normalized_sources[0]
        if normalized_sources:
            return "mixed"

    if document.get("food_data_source"):
        return _normalize_diet_source(document["food_data_source"])

    meals = document.get("meals") or []
    for meal in meals:
        foods = meal.get("foods") or []
        for food in foods:
            if food.get("source"):
                return _normalize_diet_source(food["source"])

    return "legacy_structural"


def _derive_food_data_sources(document: dict[str, Any]) -> list[str]:
    explicit_sources = document.get("food_data_sources")
    if explicit_sources:
        return [_normalize_diet_source(source) for source in explicit_sources if source]

    collected_sources: list[str] = []
    seen_sources: set[str] = set()
    meals = document.get("meals") or []
    for meal in meals:
        for food in meal.get("foods") or []:
            source = _normalize_diet_source(food.get("source"))
            if not source or source in seen_sources:
                continue

            collected_sources.append(source)
            seen_sources.add(source)

    if collected_sources:
        return collected_sources

    return [_derive_food_data_source(document)]


def _derive_resolution_counters(document: dict[str, Any]) -> dict[str, int]:
    counters = {
        "spoonacular_hits": 0,
        "cache_hits": 0,
        "internal_fallbacks": 0,
    }

    for meal in document.get("meals") or []:
        for food in meal.get("foods") or []:
            source = _normalize_diet_source(food.get("source"))
            if source == "spoonacular":
                counters["spoonacular_hits"] += 1
            elif source == "cache":
                counters["cache_hits"] += 1
            else:
                counters["internal_fallbacks"] += 1

    return counters


class DietGenerateRequest(BaseModel):
    meals_count: int = Field(ge=3, le=6)
    custom_percentages: list[float] | None = None
    training_time_of_day: TrainingTimeOfDay | None = None


class ReplaceFoodRequest(BaseModel):
    current_food_name: str = Field(min_length=2, max_length=120)
    current_food_code: str | None = None
    replacement_food_name: str | None = Field(default=None, min_length=2, max_length=120)
    replacement_food_code: str | None = None


class DietFood(BaseModel):
    food_code: str | None = None
    source: str = DEFAULT_DIET_SOURCE
    origin_source: str = DEFAULT_DIET_SOURCE
    spoonacular_id: int | None = None
    name: str
    category: str
    quantity: float = Field(gt=0)
    unit: str
    grams: float | None = Field(default=None, ge=0)
    calories: float = Field(ge=0)
    protein_grams: float = Field(ge=0)
    fat_grams: float = Field(ge=0)
    carb_grams: float = Field(ge=0)


class DietMeal(BaseModel):
    meal_number: int = Field(ge=1)
    distribution_percentage: float | None = Field(default=None, gt=0)
    target_calories: float = Field(gt=0)
    target_protein_grams: float = Field(ge=0)
    target_fat_grams: float = Field(ge=0)
    target_carb_grams: float = Field(ge=0)
    actual_calories: float = Field(ge=0)
    actual_protein_grams: float = Field(ge=0)
    actual_fat_grams: float = Field(ge=0)
    actual_carb_grams: float = Field(ge=0)
    calorie_difference: float = 0.0
    protein_difference: float = 0.0
    fat_difference: float = 0.0
    carb_difference: float = 0.0
    foods: list[DietFood] = Field(default_factory=list)


class DietBase(BaseModel):
    meals_count: int = Field(ge=3, le=6)
    target_calories: float = Field(gt=0)
    protein_grams: float = Field(ge=0)
    fat_grams: float = Field(ge=0)
    carb_grams: float = Field(ge=0)
    actual_calories: float = Field(ge=0)
    actual_protein_grams: float = Field(ge=0)
    actual_fat_grams: float = Field(ge=0)
    actual_carb_grams: float = Field(ge=0)
    calorie_difference: float = 0.0
    protein_difference: float = 0.0
    fat_difference: float = 0.0
    carb_difference: float = 0.0
    distribution_percentages: list[float] = Field(default_factory=list)
    training_time_of_day: TrainingTimeOfDay | None = None
    training_optimization_applied: bool = False
    food_data_source: str = DEFAULT_DIET_SOURCE
    food_data_sources: list[str] = Field(default_factory=list)
    food_catalog_version: str | None = None
    food_preferences_applied: bool = False
    applied_dietary_restrictions: list[str] = Field(default_factory=list)
    applied_allergies: list[str] = Field(default_factory=list)
    preferred_food_matches: int = Field(default=0, ge=0)
    diversity_strategy_applied: bool = False
    food_usage_summary: dict[str, int] = Field(default_factory=dict)
    food_filter_warnings: list[str] = Field(default_factory=list)
    catalog_source_strategy: str = DEFAULT_CATALOG_SOURCE_STRATEGY
    spoonacular_attempted: bool = False
    spoonacular_attempts: int = Field(default=0, ge=0)
    spoonacular_hits: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    internal_fallbacks: int = Field(default=0, ge=0)
    resolved_foods_count: int = Field(default=0, ge=0)


class DailyDiet(DietBase):
    id: str
    created_at: datetime
    meals: list[DietMeal]

    model_config = ConfigDict(from_attributes=True)


class DietMutationSummary(BaseModel):
    action: Literal["meal_regenerated", "food_replaced"]
    meal_number: int = Field(ge=1)
    message: str
    current_food_name: str | None = None
    replacement_food_name: str | None = None
    preserved_meal_numbers: list[int] = Field(default_factory=list)
    changed_food_names: list[str] = Field(default_factory=list)
    strategy_notes: list[str] = Field(default_factory=list)


class DietMutationResponse(BaseModel):
    diet: DailyDiet
    summary: DietMutationSummary


class DietListItem(DietBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DietListResponse(BaseModel):
    diets: list[DietListItem]


def serialize_diet_food(document: dict[str, Any]) -> DietFood:
    return DietFood(
        food_code=document.get("food_code") or document.get("code"),
        source=_normalize_diet_source(document.get("source")),
        origin_source=_normalize_diet_source(document.get("origin_source", document.get("source"))),
        spoonacular_id=document.get("spoonacular_id"),
        name=document["name"],
        category=document.get("category", "otros"),
        quantity=_round_decimal(document["quantity"], FOOD_PRECISION),
        unit=document["unit"],
        grams=_round_decimal(document["grams"], FOOD_PRECISION) if document.get("grams") is not None else None,
        calories=_round_decimal(document.get("calories"), FOOD_PRECISION),
        protein_grams=_round_decimal(document.get("protein_grams"), FOOD_PRECISION),
        fat_grams=_round_decimal(document.get("fat_grams"), FOOD_PRECISION),
        carb_grams=_round_decimal(document.get("carb_grams"), FOOD_PRECISION),
    )


def serialize_diet_meal(
    document: dict[str, Any],
    distribution_percentage: float | None = None,
) -> DietMeal:
    meal_distribution_percentage = document.get("distribution_percentage", distribution_percentage)
    foods = [serialize_diet_food(food) for food in document.get("foods", [])]
    actuals = _derive_meal_actuals(document)
    differences = _derive_meal_differences(document, actuals)

    return DietMeal(
        meal_number=document["meal_number"],
        distribution_percentage=meal_distribution_percentage,
        target_calories=_round_decimal(document["target_calories"]),
        target_protein_grams=_round_decimal(document["target_protein_grams"]),
        target_fat_grams=_round_decimal(document["target_fat_grams"]),
        target_carb_grams=_round_decimal(document["target_carb_grams"]),
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
        calorie_difference=differences["calorie_difference"],
        protein_difference=differences["protein_difference"],
        fat_difference=differences["fat_difference"],
        carb_difference=differences["carb_difference"],
        foods=foods,
    )


def _derive_diet_actuals(document: dict[str, Any], meals: list[DietMeal]) -> dict[str, float]:
    if all(document.get(field_name) is not None for field_name in (
        "actual_calories",
        "actual_protein_grams",
        "actual_fat_grams",
        "actual_carb_grams",
    )):
        return {
            "actual_calories": _round_decimal(document.get("actual_calories")),
            "actual_protein_grams": _round_decimal(document.get("actual_protein_grams")),
            "actual_fat_grams": _round_decimal(document.get("actual_fat_grams")),
            "actual_carb_grams": _round_decimal(document.get("actual_carb_grams")),
        }

    if meals:
        return {
            "actual_calories": _round_decimal(sum(meal.actual_calories for meal in meals)),
            "actual_protein_grams": _round_decimal(sum(meal.actual_protein_grams for meal in meals)),
            "actual_fat_grams": _round_decimal(sum(meal.actual_fat_grams for meal in meals)),
            "actual_carb_grams": _round_decimal(sum(meal.actual_carb_grams for meal in meals)),
        }

    return {
        "actual_calories": _round_decimal(document.get("target_calories")),
        "actual_protein_grams": _round_decimal(document.get("protein_grams")),
        "actual_fat_grams": _round_decimal(document.get("fat_grams")),
        "actual_carb_grams": _round_decimal(document.get("carb_grams")),
    }


def _derive_diet_differences(document: dict[str, Any], actuals: dict[str, float]) -> dict[str, float]:
    if all(document.get(field_name) is not None for field_name in (
        "calorie_difference",
        "protein_difference",
        "fat_difference",
        "carb_difference",
    )):
        return {
            "calorie_difference": _round_decimal(document.get("calorie_difference")),
            "protein_difference": _round_decimal(document.get("protein_difference")),
            "fat_difference": _round_decimal(document.get("fat_difference")),
            "carb_difference": _round_decimal(document.get("carb_difference")),
        }

    return _build_difference_summary(
        target_calories=_round_decimal(document.get("target_calories")),
        target_protein_grams=_round_decimal(document.get("protein_grams")),
        target_fat_grams=_round_decimal(document.get("fat_grams")),
        target_carb_grams=_round_decimal(document.get("carb_grams")),
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
    )


def serialize_daily_diet(document: dict[str, Any]) -> DailyDiet:
    distribution_percentages = _derive_distribution_percentages(document)
    food_data_source = _derive_food_data_source(document)
    food_data_sources = _derive_food_data_sources(document)
    resolution_counters = _derive_resolution_counters(document)
    meals = [
        serialize_diet_meal(
            meal,
            distribution_percentages[index] if index < len(distribution_percentages) else None,
        )
        for index, meal in enumerate(document["meals"])
    ]
    actuals = _derive_diet_actuals(document, meals)
    differences = _derive_diet_differences(document, actuals)

    return DailyDiet(
        id=str(document["_id"]),
        created_at=document["created_at"],
        meals_count=document["meals_count"],
        target_calories=_round_decimal(document["target_calories"]),
        protein_grams=_round_decimal(document["protein_grams"]),
        fat_grams=_round_decimal(document["fat_grams"]),
        carb_grams=_round_decimal(document["carb_grams"]),
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
        calorie_difference=differences["calorie_difference"],
        protein_difference=differences["protein_difference"],
        fat_difference=differences["fat_difference"],
        carb_difference=differences["carb_difference"],
        distribution_percentages=distribution_percentages,
        training_time_of_day=document.get("training_time_of_day"),
        training_optimization_applied=document.get("training_optimization_applied", False),
        food_data_source=food_data_source,
        food_data_sources=food_data_sources,
        food_catalog_version=document.get("food_catalog_version"),
        food_preferences_applied=document.get("food_preferences_applied", False),
        applied_dietary_restrictions=document.get("applied_dietary_restrictions", []),
        applied_allergies=document.get("applied_allergies", []),
        preferred_food_matches=document.get("preferred_food_matches", 0),
        diversity_strategy_applied=document.get("diversity_strategy_applied", False),
        food_usage_summary=document.get("food_usage_summary", {}),
        food_filter_warnings=document.get("food_filter_warnings", []),
        catalog_source_strategy=document.get("catalog_source_strategy", DEFAULT_CATALOG_SOURCE_STRATEGY),
        spoonacular_attempted=document.get(
            "spoonacular_attempted",
            bool(document.get("spoonacular_attempts") or document.get("spoonacular_hits")),
        ),
        spoonacular_attempts=document.get("spoonacular_attempts", document.get("spoonacular_hits", 0)),
        spoonacular_hits=document.get("spoonacular_hits", resolution_counters["spoonacular_hits"]),
        cache_hits=document.get("cache_hits", resolution_counters["cache_hits"]),
        internal_fallbacks=document.get("internal_fallbacks", resolution_counters["internal_fallbacks"]),
        resolved_foods_count=document.get("resolved_foods_count", sum(resolution_counters.values())),
        meals=meals,
    )


def serialize_diet_list_item(document: dict[str, Any]) -> DietListItem:
    distribution_percentages = _derive_distribution_percentages(document)
    food_data_source = _derive_food_data_source(document)
    food_data_sources = _derive_food_data_sources(document)
    resolution_counters = _derive_resolution_counters(document)
    meals = [serialize_diet_meal(meal) for meal in document.get("meals", [])]
    actuals = _derive_diet_actuals(document, meals)
    differences = _derive_diet_differences(document, actuals)

    return DietListItem(
        id=str(document["_id"]),
        created_at=document["created_at"],
        meals_count=document["meals_count"],
        target_calories=_round_decimal(document["target_calories"]),
        protein_grams=_round_decimal(document["protein_grams"]),
        fat_grams=_round_decimal(document["fat_grams"]),
        carb_grams=_round_decimal(document["carb_grams"]),
        actual_calories=actuals["actual_calories"],
        actual_protein_grams=actuals["actual_protein_grams"],
        actual_fat_grams=actuals["actual_fat_grams"],
        actual_carb_grams=actuals["actual_carb_grams"],
        calorie_difference=differences["calorie_difference"],
        protein_difference=differences["protein_difference"],
        fat_difference=differences["fat_difference"],
        carb_difference=differences["carb_difference"],
        distribution_percentages=distribution_percentages,
        training_time_of_day=document.get("training_time_of_day"),
        training_optimization_applied=document.get("training_optimization_applied", False),
        food_data_source=food_data_source,
        food_data_sources=food_data_sources,
        food_catalog_version=document.get("food_catalog_version"),
        food_preferences_applied=document.get("food_preferences_applied", False),
        applied_dietary_restrictions=document.get("applied_dietary_restrictions", []),
        applied_allergies=document.get("applied_allergies", []),
        preferred_food_matches=document.get("preferred_food_matches", 0),
        diversity_strategy_applied=document.get("diversity_strategy_applied", False),
        food_usage_summary=document.get("food_usage_summary", {}),
        food_filter_warnings=document.get("food_filter_warnings", []),
        catalog_source_strategy=document.get("catalog_source_strategy", DEFAULT_CATALOG_SOURCE_STRATEGY),
        spoonacular_attempted=document.get(
            "spoonacular_attempted",
            bool(document.get("spoonacular_attempts") or document.get("spoonacular_hits")),
        ),
        spoonacular_attempts=document.get("spoonacular_attempts", document.get("spoonacular_hits", 0)),
        spoonacular_hits=document.get("spoonacular_hits", resolution_counters["spoonacular_hits"]),
        cache_hits=document.get("cache_hits", resolution_counters["cache_hits"]),
        internal_fallbacks=document.get("internal_fallbacks", resolution_counters["internal_fallbacks"]),
        resolved_foods_count=document.get("resolved_foods_count", sum(resolution_counters.values())),
    )
