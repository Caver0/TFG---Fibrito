"""Global diversity tracking and scoring for the diet generation v2 engine."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


BLUEPRINT_REPEAT_PENALTY = 3.2
STRUCTURAL_REPEAT_PENALTY = 2.3
STYLE_REPEAT_PENALTY = 1.1
CONSECUTIVE_STRUCTURE_PENALTY = 1.8
PROTEIN_REPEAT_PENALTY = 1.8
CARB_REPEAT_PENALTY = 1.45
PAIR_REPEAT_PENALTY = 2.0
FAMILY_REPEAT_PENALTY = 0.8
CONSECUTIVE_STYLE_PENALTY = 1.0


def create_diversity_state() -> dict[str, Any]:
    return {
        "blueprint_counts": {},
        "structural_family_counts": {},
        "style_counts": {},
        "protein_family_counts": {},
        "carb_family_counts": {},
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


def build_blueprint_choice_penalty(
    *,
    blueprint_id: str,
    structural_family: str,
    style_tags: set[str] | frozenset[str] | tuple[str, ...],
    diversity_state: dict[str, Any],
) -> float:
    penalty = 0.0
    penalty += float(diversity_state["blueprint_counts"].get(blueprint_id, 0)) * BLUEPRINT_REPEAT_PENALTY
    penalty += float(diversity_state["structural_family_counts"].get(structural_family, 0)) * STRUCTURAL_REPEAT_PENALTY
    for style_tag in style_tags:
        penalty += float(diversity_state["style_counts"].get(style_tag, 0)) * STYLE_REPEAT_PENALTY

    previous_descriptor = diversity_state["meal_descriptors"][-1] if diversity_state["meal_descriptors"] else None
    if previous_descriptor and previous_descriptor.get("structural_family") == structural_family:
        penalty += CONSECUTIVE_STRUCTURE_PENALTY
    if previous_descriptor:
        previous_styles = set(previous_descriptor.get("style_tags", []))
        if previous_styles.intersection(style_tags):
            penalty += CONSECUTIVE_STYLE_PENALTY

    return penalty


def build_meal_diversity_penalty(
    *,
    blueprint_id: str,
    structural_family: str,
    style_tags: set[str] | frozenset[str] | tuple[str, ...],
    protein_family: str | None,
    carb_family: str | None,
    fat_family: str | None,
    support_families: list[str] | tuple[str, ...],
    diversity_state: dict[str, Any],
) -> float:
    penalty = build_blueprint_choice_penalty(
        blueprint_id=blueprint_id,
        structural_family=structural_family,
        style_tags=style_tags,
        diversity_state=diversity_state,
    )
    if protein_family:
        penalty += float(diversity_state["protein_family_counts"].get(protein_family, 0)) * PROTEIN_REPEAT_PENALTY
    if carb_family:
        penalty += float(diversity_state["carb_family_counts"].get(carb_family, 0)) * CARB_REPEAT_PENALTY
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
    style_tags: list[str] | tuple[str, ...] | set[str],
) -> dict[str, Any]:
    next_state = clone_diversity_state(diversity_state)
    _increment(next_state["blueprint_counts"], blueprint_id)
    _increment(next_state["structural_family_counts"], structural_family)
    for style_tag in style_tags:
        _increment(next_state["style_counts"], style_tag)
    next_state["meal_descriptors"].append({
        "blueprint_id": blueprint_id,
        "structural_family": structural_family,
        "style_tags": list(style_tags),
    })
    return next_state


def register_instantiated_meal(
    diversity_state: dict[str, Any],
    *,
    blueprint_id: str,
    structural_family: str,
    style_tags: list[str] | tuple[str, ...] | set[str],
    protein_family: str | None,
    carb_family: str | None,
    fat_family: str | None,
    support_families: list[str] | tuple[str, ...],
    selected_role_codes: dict[str, str],
) -> None:
    _increment(diversity_state["blueprint_counts"], blueprint_id)
    _increment(diversity_state["structural_family_counts"], structural_family)
    for style_tag in style_tags:
        _increment(diversity_state["style_counts"], style_tag)
    _increment(diversity_state["protein_family_counts"], protein_family)
    _increment(diversity_state["carb_family_counts"], carb_family)
    _increment(diversity_state["fat_family_counts"], fat_family)
    for family_id in support_families:
        _increment(diversity_state["family_counts"], family_id)
    if protein_family and carb_family:
        _increment(diversity_state["pair_counts"], f"{protein_family}::{carb_family}")
    diversity_state["meal_descriptors"].append({
        "blueprint_id": blueprint_id,
        "structural_family": structural_family,
        "style_tags": list(style_tags),
        "protein_family": protein_family,
        "carb_family": carb_family,
        "fat_family": fat_family,
        "support_families": list(support_families),
        "selected_role_codes": dict(selected_role_codes),
    })
