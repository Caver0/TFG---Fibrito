"""Meal blueprint definitions for the diet generation v2 engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BlueprintComponent:
    name: str
    role: str
    allowed_families: tuple[str, ...]
    optional: bool = False


@dataclass(frozen=True)
class MealBlueprint:
    id: str
    structural_family: str
    allowed_meal_slots: frozenset[str]
    allowed_meal_roles: frozenset[str]
    style_tags: frozenset[str]
    training_focus_compatibility: frozenset[str]
    required_components: tuple[BlueprintComponent, ...]
    optional_components: tuple[BlueprintComponent, ...] = field(default_factory=tuple)
    daily_max_repetitions: int = 1
    allow_repeat: bool = False
    base_priority: float = 1.0
    macro_tolerance: dict[str, float] = field(default_factory=lambda: {
        "calories_pct": 0.18,
        "protein_pct": 0.2,
        "fat_pct": 0.22,
        "carb_pct": 0.22,
    })
    sibling_blueprints: tuple[str, ...] = field(default_factory=tuple)


BLUEPRINTS: tuple[MealBlueprint, ...] = (
    MealBlueprint(
        id="dairy_bowl",
        structural_family="sweet_bowl",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "pre_workout", "training_focus"}),
        style_tags=frozenset({"sweet", "bowl", "breakfast"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("dairy_high_protein",)),
            BlueprintComponent("carb_base", "carb", ("oats_cereals",)),
            BlueprintComponent("fat_topper", "fat", ("nuts_and_fats",)),
        ),
        optional_components=(
            BlueprintComponent("fruit_support", "fruit", ("fruit_carbs",), optional=True),
        ),
        base_priority=1.05,
        sibling_blueprints=("yogurt_cereal_bowl", "fruit_protein_snack"),
    ),
    MealBlueprint(
        id="yogurt_cereal_bowl",
        structural_family="cereal_bowl",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "post_workout", "training_focus"}),
        style_tags=frozenset({"sweet", "bowl", "cereal"}),
        training_focus_compatibility=frozenset({"any", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("dairy_high_protein",)),
            BlueprintComponent("carb_base", "carb", ("breakfast_cereals",)),
            BlueprintComponent("fat_topper", "fat", ("nuts_and_fats",)),
        ),
        optional_components=(
            BlueprintComponent("fruit_support", "fruit", ("fruit_carbs",), optional=True),
        ),
        base_priority=1.0,
        sibling_blueprints=("dairy_bowl", "fruit_protein_snack"),
    ),
    MealBlueprint(
        id="savory_toast",
        structural_family="toast_meal",
        allowed_meal_slots=frozenset({"early", "main"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "dinner", "training_focus"}),
        style_tags=frozenset({"savory", "toast"}),
        training_focus_compatibility=frozenset({"any", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("egg_proteins", "lean_poultry", "lean_fish")),
            BlueprintComponent("carb_base", "carb", ("toast_breads",)),
            BlueprintComponent("fat_layer", "fat", ("avocado_fats",)),
        ),
        optional_components=(
            BlueprintComponent("vegetable_companion", "vegetable", ("vegetable_sides",), optional=True),
        ),
        base_priority=1.0,
        sibling_blueprints=("sandwich_meal", "fruit_protein_snack"),
    ),
    MealBlueprint(
        id="fruit_protein_snack",
        structural_family="fruit_protein_combo",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "pre_workout", "post_workout", "training_focus"}),
        style_tags=frozenset({"snack", "sweet", "fruit_forward"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("dairy_high_protein", "egg_proteins")),
            BlueprintComponent("carb_base", "carb", ("fruit_carbs", "toast_breads")),
            BlueprintComponent("fat_companion", "fat", ("nuts_and_fats", "avocado_fats")),
        ),
        base_priority=0.9,
        sibling_blueprints=("dairy_bowl", "savory_toast"),
    ),
    MealBlueprint(
        id="rice_plate",
        structural_family="savory_plate",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "pre_workout", "post_workout", "training_focus"}),
        style_tags=frozenset({"savory", "plate", "rice"}),
        training_focus_compatibility=frozenset({"any", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "lean_fish", "egg_proteins")),
            BlueprintComponent("carb_main", "carb", ("rice_starches",)),
            BlueprintComponent("fat_finish", "fat", ("cooking_fats", "avocado_fats")),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides",)),
        ),
        base_priority=1.08,
        sibling_blueprints=("pasta_plate", "potato_plate", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="pasta_plate",
        structural_family="savory_plate",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "post_workout", "training_focus"}),
        style_tags=frozenset({"savory", "plate", "pasta"}),
        training_focus_compatibility=frozenset({"any", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "lean_fish")),
            BlueprintComponent("carb_main", "carb", ("pasta_starches",)),
            BlueprintComponent("fat_finish", "fat", ("cooking_fats",)),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides",)),
        ),
        base_priority=1.0,
        sibling_blueprints=("rice_plate", "potato_plate", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="potato_plate",
        structural_family="savory_plate",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "pre_workout", "training_focus"}),
        style_tags=frozenset({"savory", "plate", "potato"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "lean_fish", "egg_proteins")),
            BlueprintComponent("carb_main", "carb", ("potato_starches",)),
            BlueprintComponent("fat_finish", "fat", ("cooking_fats", "avocado_fats")),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides",)),
        ),
        base_priority=1.0,
        sibling_blueprints=("rice_plate", "pasta_plate", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="sandwich_meal",
        structural_family="bread_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "training_focus"}),
        style_tags=frozenset({"savory", "bread", "sandwich"}),
        training_focus_compatibility=frozenset({"any", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "lean_fish", "egg_proteins")),
            BlueprintComponent("carb_main", "carb", ("toast_breads",)),
            BlueprintComponent("fat_finish", "fat", ("avocado_fats",)),
        ),
        optional_components=(
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides",), optional=True),
        ),
        base_priority=0.92,
        sibling_blueprints=("savory_toast", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="wrap_meal",
        structural_family="bread_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "training_focus"}),
        style_tags=frozenset({"savory", "wrap"}),
        training_focus_compatibility=frozenset({"any", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "lean_fish", "egg_proteins")),
            BlueprintComponent("carb_main", "carb", ("wrap_breads",)),
            BlueprintComponent("fat_finish", "fat", ("avocado_fats", "cooking_fats")),
        ),
        optional_components=(
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides",), optional=True),
        ),
        base_priority=0.88,
        sibling_blueprints=("sandwich_meal", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="salad_protein_carb",
        structural_family="salad_combo",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "training_focus", "pre_workout"}),
        style_tags=frozenset({"savory", "salad", "bowl"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "lean_fish", "egg_proteins")),
            BlueprintComponent("carb_main", "carb", ("rice_starches", "potato_starches", "toast_breads")),
            BlueprintComponent("fat_finish", "fat", ("avocado_fats", "cooking_fats")),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides",)),
        ),
        base_priority=0.95,
        sibling_blueprints=("rice_plate", "potato_plate", "sandwich_meal"),
    ),
)

_BLUEPRINT_LOOKUP = {blueprint.id: blueprint for blueprint in BLUEPRINTS}


def get_blueprint(blueprint_id: str) -> MealBlueprint | None:
    return _BLUEPRINT_LOOKUP.get(blueprint_id)


def iter_blueprints() -> tuple[MealBlueprint, ...]:
    return BLUEPRINTS


def blueprint_is_compatible_with_context(
    blueprint: MealBlueprint,
    *,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> bool:
    if meal_slot not in blueprint.allowed_meal_slots:
        return False
    if meal_role not in blueprint.allowed_meal_roles:
        return False
    if not training_focus:
        return True
    return "any" in blueprint.training_focus_compatibility or meal_role in blueprint.training_focus_compatibility


def blueprint_metadata(blueprint: MealBlueprint) -> dict[str, Any]:
    return {
        "applied_blueprint_id": blueprint.id,
        "applied_blueprint_family": blueprint.structural_family,
        "applied_blueprint_style_tags": sorted(blueprint.style_tags),
    }
