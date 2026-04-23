"""Global diversity tracking and scoring for the diet generation v2 engine."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


BLUEPRINT_REPEAT_PENALTY = 3.2
STRUCTURAL_REPEAT_PENALTY = 2.1
VISUAL_FAMILY_REPEAT_PENALTY = 2.7
VISUAL_CONTINUITY_REPEAT_PENALTY = 2.35
STYLE_REPEAT_PENALTY = 0.85
CONSECUTIVE_STRUCTURE_PENALTY = 1.4
CONSECUTIVE_VISUAL_FAMILY_PENALTY = 2.0
CONSECUTIVE_VISUAL_CONTINUITY_PENALTY = 2.5
PROTEIN_REPEAT_PENALTY = 1.8
CARB_REPEAT_PENALTY = 1.9
CARB_CLUSTER_REPEAT_PENALTY = 1.1
PAIR_REPEAT_PENALTY = 2.35
FAMILY_REPEAT_PENALTY = 0.75
CONSECUTIVE_STYLE_PENALTY = 0.7
EARLY_VISUAL_REPEAT_PENALTY = 1.15
BREAKFAST_BOWL_REPEAT_PENALTY = 4.6
BREAKFAST_CEREAL_REPEAT_PENALTY = 3.0


def get_carb_cluster(carb_family: str | None) -> str | None:
    if not carb_family:
        return None
    if carb_family in {"oats_cereals", "cornflakes_cereals", "granola_cereals", "muesli_cereals"}:
        return "breakfast_cereal"
    if carb_family in {"rice_starches", "pasta_starches", "potato_starches", "sweet_potato_starches"}:
        return "main_starch"
    if carb_family in {"toast_breads", "bagel_breads", "wrap_breads"}:
        return "bread"
    if carb_family == "rice_cake_starches":
        return "light_snack_starch"
    if carb_family in {"banana_fruit", "apple_fruit", "berries_fruit"}:
        return "fruit"
    return carb_family


def create_diversity_state() -> dict[str, Any]:
    return {
        "blueprint_counts": {},
        "structural_family_counts": {},
        "visual_family_counts": {},
        "visual_continuity_group_counts": {},
        "meal_slot_visual_family_counts": {},
        "style_counts": {},
        "protein_family_counts": {},
        "carb_family_counts": {},
        "carb_cluster_counts": {},
        "meal_slot_carb_cluster_counts": {},
        "fat_family_counts": {},
        "pair_counts": {},
        "family_counts": {},
        "meal_descriptors": [],
    }


def clone_diversity_state(diversity_state: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(diversity_state)


def _increment(counter: dict[str, int], key: str | None) -> None:
    if not key:
        return
    counter[key] = int(counter.get(key, 0)) + 1


def _increment_nested(counter: dict[str, dict[str, int]], outer_key: str | None, inner_key: str | None) -> None:
    if not outer_key or not inner_key:
        return
    bucket = counter.setdefault(outer_key, {})
    bucket[inner_key] = int(bucket.get(inner_key, 0)) + 1


def _count_nested(counter: dict[str, dict[str, int]], outer_key: str | None, inner_key: str | None) -> int:
    if not outer_key or not inner_key:
        return 0
    return int(counter.get(outer_key, {}).get(inner_key, 0))


def build_blueprint_choice_penalty(
    *,
    blueprint_id: str,
    structural_family: str,
    visual_family: str,
    visual_continuity_group: str,
    style_tags: set[str] | frozenset[str] | tuple[str, ...],
    meal_slot: str,
    meal_role: str,
    diversity_state: dict[str, Any],
) -> float:
    penalty = 0.0
    penalty += float(diversity_state["blueprint_counts"].get(blueprint_id, 0)) * BLUEPRINT_REPEAT_PENALTY
    penalty += float(diversity_state["structural_family_counts"].get(structural_family, 0)) * STRUCTURAL_REPEAT_PENALTY
    penalty += float(diversity_state["visual_family_counts"].get(visual_family, 0)) * VISUAL_FAMILY_REPEAT_PENALTY
    penalty += (
        float(diversity_state["visual_continuity_group_counts"].get(visual_continuity_group, 0))
        * VISUAL_CONTINUITY_REPEAT_PENALTY
    )
    for style_tag in style_tags:
        penalty += float(diversity_state["style_counts"].get(style_tag, 0)) * STYLE_REPEAT_PENALTY
    if meal_slot == "early":
        penalty += _count_nested(
            diversity_state["meal_slot_visual_family_counts"],
            meal_slot,
            visual_family,
        ) * EARLY_VISUAL_REPEAT_PENALTY
        if visual_family == "breakfast_bowl":
            penalty += _count_nested(
                diversity_state["meal_slot_visual_family_counts"],
                meal_slot,
                visual_family,
            ) * BREAKFAST_BOWL_REPEAT_PENALTY

    previous_descriptor = diversity_state["meal_descriptors"][-1] if diversity_state["meal_descriptors"] else None
    if previous_descriptor and previous_descriptor.get("structural_family") == structural_family:
        penalty += CONSECUTIVE_STRUCTURE_PENALTY
    if previous_descriptor and previous_descriptor.get("visual_family") == visual_family:
        penalty += CONSECUTIVE_VISUAL_FAMILY_PENALTY
    if previous_descriptor and previous_descriptor.get("visual_continuity_group") == visual_continuity_group:
        penalty += CONSECUTIVE_VISUAL_CONTINUITY_PENALTY
    if previous_descriptor:
        previous_styles = set(previous_descriptor.get("style_tags", []))
        if previous_styles.intersection(style_tags):
            penalty += CONSECUTIVE_STYLE_PENALTY

    return penalty


def build_meal_diversity_penalty(
    *,
    blueprint_id: str,
    structural_family: str,
    visual_family: str,
    visual_continuity_group: str,
    style_tags: set[str] | frozenset[str] | tuple[str, ...],
    meal_slot: str,
    meal_role: str,
    protein_family: str | None,
    carb_family: str | None,
    fat_family: str | None,
    support_families: list[str] | tuple[str, ...],
    diversity_state: dict[str, Any],
) -> float:
    penalty = build_blueprint_choice_penalty(
        blueprint_id=blueprint_id,
        structural_family=structural_family,
        visual_family=visual_family,
        visual_continuity_group=visual_continuity_group,
        style_tags=style_tags,
        meal_slot=meal_slot,
        meal_role=meal_role,
        diversity_state=diversity_state,
    )
    if protein_family:
        penalty += float(diversity_state["protein_family_counts"].get(protein_family, 0)) * PROTEIN_REPEAT_PENALTY
    if carb_family:
        penalty += float(diversity_state["carb_family_counts"].get(carb_family, 0)) * CARB_REPEAT_PENALTY
        carb_cluster = get_carb_cluster(carb_family)
        if carb_cluster:
            penalty += float(diversity_state["carb_cluster_counts"].get(carb_cluster, 0)) * CARB_CLUSTER_REPEAT_PENALTY
            if meal_slot == "early" and carb_cluster == "breakfast_cereal":
                penalty += _count_nested(
                    diversity_state["meal_slot_carb_cluster_counts"],
                    meal_slot,
                    carb_cluster,
                ) * BREAKFAST_CEREAL_REPEAT_PENALTY
    if protein_family and carb_family:
        penalty += float(diversity_state["pair_counts"].get(f"{protein_family}::{carb_family}", 0)) * PAIR_REPEAT_PENALTY
    if fat_family:
        penalty += float(diversity_state["fat_family_counts"].get(fat_family, 0)) * 0.35
    for family_id in support_families:
        penalty += float(diversity_state["family_counts"].get(family_id, 0)) * FAMILY_REPEAT_PENALTY
    return penalty


def register_blueprint_choice(
    diversity_state: dict[str, Any],
    *,
    blueprint_id: str,
    structural_family: str,
    visual_family: str,
    visual_continuity_group: str,
    style_tags: list[str] | tuple[str, ...] | set[str],
    meal_slot: str,
    meal_role: str,
) -> dict[str, Any]:
    next_state = clone_diversity_state(diversity_state)
    _increment(next_state["blueprint_counts"], blueprint_id)
    _increment(next_state["structural_family_counts"], structural_family)
    _increment(next_state["visual_family_counts"], visual_family)
    _increment(next_state["visual_continuity_group_counts"], visual_continuity_group)
    _increment_nested(next_state["meal_slot_visual_family_counts"], meal_slot, visual_family)
    for style_tag in style_tags:
        _increment(next_state["style_counts"], style_tag)
    next_state["meal_descriptors"].append({
        "blueprint_id": blueprint_id,
        "structural_family": structural_family,
        "visual_family": visual_family,
        "visual_continuity_group": visual_continuity_group,
        "style_tags": list(style_tags),
        "meal_slot": meal_slot,
        "meal_role": meal_role,
    })
    return next_state


def register_instantiated_meal(
    diversity_state: dict[str, Any],
    *,
    blueprint_id: str,
    structural_family: str,
    visual_family: str,
    visual_continuity_group: str,
    style_tags: list[str] | tuple[str, ...] | set[str],
    meal_slot: str,
    meal_role: str,
    protein_family: str | None,
    carb_family: str | None,
    fat_family: str | None,
    support_families: list[str] | tuple[str, ...],
    selected_role_codes: dict[str, str],
) -> None:
    _increment(diversity_state["blueprint_counts"], blueprint_id)
    _increment(diversity_state["structural_family_counts"], structural_family)
    _increment(diversity_state["visual_family_counts"], visual_family)
    _increment(diversity_state["visual_continuity_group_counts"], visual_continuity_group)
    _increment_nested(diversity_state["meal_slot_visual_family_counts"], meal_slot, visual_family)
    for style_tag in style_tags:
        _increment(diversity_state["style_counts"], style_tag)
    _increment(diversity_state["protein_family_counts"], protein_family)
    _increment(diversity_state["carb_family_counts"], carb_family)
    carb_cluster = get_carb_cluster(carb_family)
    _increment(diversity_state["carb_cluster_counts"], carb_cluster)
    _increment_nested(diversity_state["meal_slot_carb_cluster_counts"], meal_slot, carb_cluster)
    _increment(diversity_state["fat_family_counts"], fat_family)
    for family_id in support_families:
        _increment(diversity_state["family_counts"], family_id)
    if protein_family and carb_family:
        _increment(diversity_state["pair_counts"], f"{protein_family}::{carb_family}")
    diversity_state["meal_descriptors"].append({
        "blueprint_id": blueprint_id,
        "structural_family": structural_family,
        "visual_family": visual_family,
        "visual_continuity_group": visual_continuity_group,
        "style_tags": list(style_tags),
        "meal_slot": meal_slot,
        "meal_role": meal_role,
        "protein_family": protein_family,
        "carb_family": carb_family,
        "carb_cluster": carb_cluster,
        "fat_family": fat_family,
        "support_families": list(support_families),
        "selected_role_codes": dict(selected_role_codes),
    })
