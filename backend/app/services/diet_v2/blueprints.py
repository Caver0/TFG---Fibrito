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
    visual_family: str
    visual_continuity_group: str
    allowed_meal_slots: frozenset[str]
    allowed_meal_roles: frozenset[str]
    style_tags: frozenset[str]
    training_focus_compatibility: frozenset[str]
    required_components: tuple[BlueprintComponent, ...]
    optional_components: tuple[BlueprintComponent, ...] = field(default_factory=tuple)
    breakfast_visual_family: str | None = None
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
        visual_family="cold_assembled_meal",
        visual_continuity_group="cold_assembled_meal",
        breakfast_visual_family="breakfast_bowl",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "pre_workout", "training_focus"}),
        style_tags=frozenset({"sweet", "bowl", "breakfast"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("greek_yogurt_protein", "skyr_protein", "cottage_cheese_protein")),
            BlueprintComponent("carb_base", "carb", ("oats_cereals",)),
            BlueprintComponent("fat_topper", "fat", ("mixed_nuts_fats", "peanut_butter_fats")),
        ),
        optional_components=(
            BlueprintComponent("fruit_support", "fruit", ("banana_fruit", "apple_fruit", "berries_fruit"), optional=True),
        ),
        base_priority=0.94,
        sibling_blueprints=("yogurt_cereal_bowl", "fruit_protein_snack", "sweet_toast_breakfast", "rice_cake_snack"),
    ),
    MealBlueprint(
        id="yogurt_cereal_bowl",
        structural_family="cereal_bowl",
        visual_family="cold_assembled_meal",
        visual_continuity_group="cold_assembled_meal",
        breakfast_visual_family="breakfast_bowl",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "post_workout", "training_focus"}),
        style_tags=frozenset({"sweet", "bowl", "cereal"}),
        training_focus_compatibility=frozenset({"any", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("greek_yogurt_protein", "skyr_protein", "cottage_cheese_protein")),
            BlueprintComponent("carb_base", "carb", ("cornflakes_cereals", "granola_cereals", "muesli_cereals")),
            BlueprintComponent("fat_topper", "fat", ("mixed_nuts_fats", "peanut_butter_fats")),
        ),
        optional_components=(
            BlueprintComponent("fruit_support", "fruit", ("banana_fruit", "apple_fruit", "berries_fruit"), optional=True),
        ),
        base_priority=0.88,
        sibling_blueprints=("dairy_bowl", "fruit_protein_snack", "rice_cake_snack"),
    ),
    MealBlueprint(
        id="savory_toast",
        structural_family="toast_meal",
        visual_family="toast_meal",
        visual_continuity_group="bread_based_meal",
        breakfast_visual_family="breakfast_toast",
        allowed_meal_slots=frozenset({"early", "main"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "dinner", "training_focus"}),
        style_tags=frozenset({"savory", "toast"}),
        training_focus_compatibility=frozenset({"any", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("egg_proteins", "lean_poultry", "tuna_fish", "salmon_fish")),
            BlueprintComponent("carb_base", "carb", ("toast_breads", "bagel_breads")),
            BlueprintComponent("fat_layer", "fat", ("avocado_fats",)),
        ),
        optional_components=(
            BlueprintComponent("vegetable_companion", "vegetable", ("vegetable_sides", "salad_vegetables"), optional=True),
        ),
        base_priority=1.05,
        sibling_blueprints=("sweet_toast_breakfast", "breakfast_wrap", "sandwich_meal", "fruit_protein_snack", "egg_rice_cake_breakfast"),
    ),
    MealBlueprint(
        id="fruit_protein_snack",
        structural_family="fruit_protein_combo",
        visual_family="cold_snack",
        visual_continuity_group="cold_assembled_meal",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "pre_workout", "post_workout", "training_focus"}),
        style_tags=frozenset({"snack", "sweet", "fruit_forward"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("greek_yogurt_protein", "skyr_protein", "cottage_cheese_protein", "egg_proteins")),
            BlueprintComponent("carb_base", "carb", ("banana_fruit", "apple_fruit", "berries_fruit", "toast_breads", "rice_cake_starches")),
            BlueprintComponent("fat_companion", "fat", ("mixed_nuts_fats", "peanut_butter_fats", "avocado_fats")),
        ),
        base_priority=0.78,
        sibling_blueprints=("dairy_bowl", "rice_cake_snack", "sweet_toast_breakfast", "savory_toast"),
    ),
    MealBlueprint(
        id="rice_plate",
        structural_family="savory_plate",
        visual_family="main_starch_plate",
        visual_continuity_group="protein_starch_veg_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "pre_workout", "post_workout", "training_focus"}),
        style_tags=frozenset({"savory", "plate", "rice"}),
        training_focus_compatibility=frozenset({"any", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "tuna_fish", "salmon_fish", "egg_proteins", "lean_beef")),
            BlueprintComponent("carb_main", "carb", ("rice_starches",)),
            BlueprintComponent("fat_finish", "fat", ("cooking_fats", "avocado_fats")),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides", "salad_vegetables")),
        ),
        base_priority=1.08,
        sibling_blueprints=("pasta_plate", "potato_plate", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="pasta_plate",
        structural_family="savory_plate",
        visual_family="main_starch_plate",
        visual_continuity_group="protein_starch_veg_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "post_workout", "training_focus"}),
        style_tags=frozenset({"savory", "plate", "pasta"}),
        training_focus_compatibility=frozenset({"any", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "tuna_fish", "salmon_fish", "lean_beef")),
            BlueprintComponent("carb_main", "carb", ("pasta_starches",)),
            BlueprintComponent("fat_finish", "fat", ("cooking_fats",)),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides", "salad_vegetables")),
        ),
        base_priority=1.0,
        sibling_blueprints=("rice_plate", "potato_plate", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="potato_plate",
        structural_family="savory_plate",
        visual_family="main_starch_plate",
        visual_continuity_group="protein_starch_veg_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "pre_workout", "training_focus"}),
        style_tags=frozenset({"savory", "plate", "potato"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "salmon_fish", "egg_proteins", "lean_beef")),
            BlueprintComponent("carb_main", "carb", ("potato_starches", "sweet_potato_starches")),
            BlueprintComponent("fat_finish", "fat", ("cooking_fats", "avocado_fats")),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides", "salad_vegetables")),
        ),
        base_priority=1.0,
        sibling_blueprints=("rice_plate", "pasta_plate", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="sandwich_meal",
        structural_family="bread_meal",
        visual_family="wrap_sandwich_meal",
        visual_continuity_group="bread_based_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "training_focus"}),
        style_tags=frozenset({"savory", "bread", "sandwich"}),
        training_focus_compatibility=frozenset({"any", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "tuna_fish", "egg_proteins", "lean_beef")),
            BlueprintComponent("carb_main", "carb", ("toast_breads", "bagel_breads")),
            BlueprintComponent("fat_finish", "fat", ("avocado_fats",)),
        ),
        optional_components=(
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides", "salad_vegetables"), optional=True),
        ),
        base_priority=1.02,
        sibling_blueprints=("savory_toast", "breakfast_wrap", "wrap_meal", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="wrap_meal",
        structural_family="bread_meal",
        visual_family="wrap_sandwich_meal",
        visual_continuity_group="bread_based_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "training_focus"}),
        style_tags=frozenset({"savory", "wrap"}),
        training_focus_compatibility=frozenset({"any", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "tuna_fish", "egg_proteins", "lean_beef")),
            BlueprintComponent("carb_main", "carb", ("wrap_breads",)),
            BlueprintComponent("fat_finish", "fat", ("avocado_fats", "cooking_fats")),
        ),
        optional_components=(
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides", "salad_vegetables"), optional=True),
        ),
        base_priority=0.98,
        sibling_blueprints=("breakfast_wrap", "sandwich_meal", "salad_protein_carb"),
    ),
    MealBlueprint(
        id="salad_protein_carb",
        structural_family="salad_combo",
        visual_family="salad_meal",
        visual_continuity_group="protein_starch_veg_meal",
        allowed_meal_slots=frozenset({"main", "late"}),
        allowed_meal_roles=frozenset({"meal", "dinner", "training_focus", "pre_workout"}),
        style_tags=frozenset({"savory", "salad", "bowl"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_main", "protein", ("lean_poultry", "tuna_fish", "salmon_fish", "egg_proteins", "lean_beef")),
            BlueprintComponent("carb_main", "carb", ("rice_starches", "potato_starches", "sweet_potato_starches", "toast_breads", "bagel_breads")),
            BlueprintComponent("fat_finish", "fat", ("avocado_fats", "cooking_fats")),
            BlueprintComponent("vegetable_side", "vegetable", ("vegetable_sides", "salad_vegetables")),
        ),
        base_priority=0.9,
        sibling_blueprints=("rice_plate", "potato_plate", "sandwich_meal"),
    ),
    MealBlueprint(
        id="sweet_toast_breakfast",
        structural_family="toast_meal",
        visual_family="toast_meal",
        visual_continuity_group="bread_based_meal",
        breakfast_visual_family="breakfast_toast",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "pre_workout", "training_focus"}),
        style_tags=frozenset({"sweet", "toast", "breakfast"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("greek_yogurt_protein", "skyr_protein", "cottage_cheese_protein")),
            BlueprintComponent("carb_base", "carb", ("toast_breads", "bagel_breads")),
            BlueprintComponent("fat_layer", "fat", ("peanut_butter_fats", "mixed_nuts_fats")),
        ),
        optional_components=(
            BlueprintComponent("fruit_support", "fruit", ("banana_fruit", "apple_fruit", "berries_fruit"), optional=True),
        ),
        base_priority=1.08,
        sibling_blueprints=("savory_toast", "breakfast_wrap", "fruit_protein_snack", "rice_cake_snack"),
    ),
    MealBlueprint(
        id="egg_rice_cake_breakfast",
        structural_family="breakfast_plate",
        visual_family="egg_breakfast_plate",
        visual_continuity_group="light_snack_meal",
        breakfast_visual_family="egg_breakfast_plate",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "pre_workout", "training_focus"}),
        style_tags=frozenset({"savory", "plate", "egg_breakfast"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("egg_proteins",)),
            BlueprintComponent("carb_base", "carb", ("rice_cake_starches",)),
            BlueprintComponent("fat_layer", "fat", ("avocado_fats",)),
        ),
        optional_components=(
            BlueprintComponent("fruit_support", "fruit", ("banana_fruit", "apple_fruit", "berries_fruit"), optional=True),
        ),
        base_priority=1.02,
        sibling_blueprints=("savory_toast", "breakfast_wrap", "rice_cake_snack"),
    ),
    MealBlueprint(
        id="breakfast_wrap",
        structural_family="wrap_meal",
        visual_family="wrap_sandwich_meal",
        visual_continuity_group="bread_based_meal",
        breakfast_visual_family="breakfast_wrap",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "training_focus"}),
        style_tags=frozenset({"savory", "wrap", "breakfast"}),
        training_focus_compatibility=frozenset({"any", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("egg_proteins",)),
            BlueprintComponent("carb_base", "carb", ("wrap_breads",)),
            BlueprintComponent("fat_layer", "fat", ("avocado_fats",)),
        ),
        optional_components=(
            BlueprintComponent("vegetable_companion", "vegetable", ("vegetable_sides", "salad_vegetables"), optional=True),
        ),
        base_priority=1.04,
        sibling_blueprints=("savory_toast", "sweet_toast_breakfast", "wrap_meal", "egg_rice_cake_breakfast"),
    ),
    MealBlueprint(
        id="rice_cake_snack",
        structural_family="light_snack",
        visual_family="stacked_snack",
        visual_continuity_group="light_snack_meal",
        allowed_meal_slots=frozenset({"early"}),
        allowed_meal_roles=frozenset({"breakfast", "meal", "pre_workout", "post_workout", "training_focus"}),
        style_tags=frozenset({"snack", "stacked", "sweet"}),
        training_focus_compatibility=frozenset({"any", "pre_workout", "post_workout", "training_focus"}),
        required_components=(
            BlueprintComponent("protein_base", "protein", ("greek_yogurt_protein", "skyr_protein", "cottage_cheese_protein")),
            BlueprintComponent("carb_base", "carb", ("rice_cake_starches",)),
            BlueprintComponent("fat_layer", "fat", ("peanut_butter_fats", "mixed_nuts_fats")),
        ),
        optional_components=(
            BlueprintComponent("fruit_support", "fruit", ("banana_fruit", "apple_fruit", "berries_fruit"), optional=True),
        ),
        base_priority=0.86,
        sibling_blueprints=("fruit_protein_snack", "sweet_toast_breakfast", "egg_rice_cake_breakfast"),
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


def get_blueprint_visual_family(
    blueprint: MealBlueprint,
    *,
    meal_slot: str | None = None,
) -> str:
    if meal_slot == "early" and blueprint.breakfast_visual_family:
        return blueprint.breakfast_visual_family
    return blueprint.visual_family


def get_blueprint_role_family_hints(
    blueprint: MealBlueprint,
    *,
    role: str,
) -> tuple[str, ...]:
    family_ids: list[str] = []
    for component in blueprint.required_components:
        if component.role != role:
            continue
        family_ids.extend(component.allowed_families)
    return tuple(dict.fromkeys(family_ids))


def blueprint_metadata(
    blueprint: MealBlueprint,
    *,
    meal_slot: str | None = None,
) -> dict[str, Any]:
    return {
        "applied_blueprint_id": blueprint.id,
        "applied_blueprint_family": blueprint.structural_family,
        "applied_blueprint_visual_family": get_blueprint_visual_family(
            blueprint,
            meal_slot=meal_slot,
        ),
        "applied_blueprint_visual_continuity_group": blueprint.visual_continuity_group,
        "applied_blueprint_style_tags": sorted(blueprint.style_tags),
    }
