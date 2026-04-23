from __future__ import annotations

import hashlib
import json
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.schemas.diet import DietMeal
from app.schemas.user import FoodPreferencesProfile, UserPublic
from app.services import diet_service, meal_regeneration_service
from app.services.diet.candidates import (
    create_daily_food_usage_tracker,
    get_meal_structure_signature,
    track_food_usage_across_day,
)
from app.services.diet_v2.regenerator import regenerate_meal_plan_v2, summarize_visible_difference
from app.services.diet_v2.families import get_primary_family_id
from app.services.diet_v2.telemetry import (
    get_last_generation_diagnostics,
    get_last_regeneration_diagnostics,
    set_last_generation_diagnostics,
    set_last_regeneration_diagnostics,
)
from app.services.food_catalog_service import get_internal_food_lookup
from app.services.food_preferences_service import build_user_food_preferences_profile


REPORT_PATH = Path(__file__).resolve().with_name("diet_v2_audit_report.json")


class _DummyFoodsCatalog:
    def find(self, *args, **kwargs):
        return []

    def find_one(self, *args, **kwargs):
        return None


class _DummyDietsCollection:
    def find(self, *args, **kwargs):
        return []


class _DummyDatabase:
    foods_catalog = _DummyFoodsCatalog()
    diets = _DummyDietsCollection()


DATABASE = _DummyDatabase()


@dataclass(frozen=True)
class AuditScenario:
    id: str
    meals_count: int
    training_time_of_day: str | None
    target_calories: float
    goal: str
    sex: str
    current_weight: float
    training_days_per_week: int
    food_preferences: FoodPreferencesProfile


SCENARIOS: tuple[AuditScenario, ...] = (
    AuditScenario(
        id="gain_4_tarde",
        meals_count=4,
        training_time_of_day="tarde",
        target_calories=2500.0,
        goal="ganar_masa",
        sex="Masculino",
        current_weight=80.0,
        training_days_per_week=4,
        food_preferences=FoodPreferencesProfile(),
    ),
    AuditScenario(
        id="gain_5_manana_pref",
        meals_count=5,
        training_time_of_day="manana",
        target_calories=2850.0,
        goal="ganar_masa",
        sex="Masculino",
        current_weight=84.0,
        training_days_per_week=5,
        food_preferences=FoodPreferencesProfile(
            preferred_foods=["avena", "arroz", "pollo"],
        ),
    ),
    AuditScenario(
        id="cut_4_mediodia",
        meals_count=4,
        training_time_of_day="mediodia",
        target_calories=1900.0,
        goal="perder_grasa",
        sex="Femenino",
        current_weight=63.0,
        training_days_per_week=4,
        food_preferences=FoodPreferencesProfile(),
    ),
    AuditScenario(
        id="maintain_3_none",
        meals_count=3,
        training_time_of_day=None,
        target_calories=2200.0,
        goal="mantener_peso",
        sex="Masculino",
        current_weight=76.0,
        training_days_per_week=2,
        food_preferences=FoodPreferencesProfile(),
    ),
    AuditScenario(
        id="gluten_free_4_tarde",
        meals_count=4,
        training_time_of_day="tarde",
        target_calories=2300.0,
        goal="ganar_masa",
        sex="Masculino",
        current_weight=78.0,
        training_days_per_week=4,
        food_preferences=FoodPreferencesProfile(
            dietary_restrictions=["sin_gluten"],
        ),
    ),
    AuditScenario(
        id="lactose_free_4_noche",
        meals_count=4,
        training_time_of_day="noche",
        target_calories=2100.0,
        goal="perder_grasa",
        sex="Femenino",
        current_weight=61.0,
        training_days_per_week=3,
        food_preferences=FoodPreferencesProfile(
            dietary_restrictions=["sin_lactosa"],
        ),
    ),
)


RUNS_PER_SCENARIO = 8


def _stable_int(*parts: object, modulo: int = 1_000_000_007) -> int:
    digest = hashlib.blake2b(
        "|".join(str(part) for part in parts).encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") % modulo


def _stable_object_id(*parts: object) -> str:
    digest = hashlib.blake2b(
        "|".join(str(part) for part in parts).encode("utf-8"),
        digest_size=12,
    ).hexdigest()
    return digest[:24]


@contextmanager
def _patched_attr(obj: Any, attribute: str, value: Any) -> Iterator[None]:
    previous_value = getattr(obj, attribute)
    setattr(obj, attribute, value)
    try:
        yield
    finally:
        setattr(obj, attribute, previous_value)


def _build_user(scenario: AuditScenario, *, run_index: int) -> UserPublic:
    user_id = _stable_object_id("user", scenario.id, run_index)
    return UserPublic(
        id=user_id,
        name=f"Audit {scenario.id}",
        email=f"{scenario.id}-{run_index}@example.com",
        created_at=datetime(2026, 1, 1),
        age=30,
        sex=scenario.sex,  # type: ignore[arg-type]
        height=172.0 if scenario.sex == "Femenino" else 180.0,
        current_weight=scenario.current_weight,
        training_days_per_week=scenario.training_days_per_week,
        goal=scenario.goal,  # type: ignore[arg-type]
        target_calories=scenario.target_calories,
        food_preferences=scenario.food_preferences,
        auth_providers=["password"],
    )


def _build_generation_seed(scenario: AuditScenario, run_index: int) -> int:
    return _stable_int("generation", scenario.id, run_index, modulo=1_000_000_000)


def _serialize_meal_example(meal: dict[str, Any], meal_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "meal_number": meal["meal_number"],
        "meal_slot": meal["meal_slot"],
        "meal_role": meal["meal_role"],
        "blueprint": None if meal_summary is None else meal_summary.get("applied_blueprint_id"),
        "foods": [food["name"] for food in meal["foods"]],
        "food_codes": [food["food_code"] for food in meal["foods"]],
    }


def _infer_visible_meal_summary(run_result: dict[str, Any], meal_payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        meal_model = DietMeal.model_validate(meal_payload)
        inferred = meal_regeneration_service.infer_existing_meal_plan(
            meal_model,
            meal_index=meal_payload["meal_number"] - 1,
            meals_count=run_result["diet"]["meals_count"],
            training_focus=meal_payload["meal_role"] in {"pre_workout", "post_workout", "training_focus"},
            food_lookup=get_internal_food_lookup(),
        )
        return inferred
    except Exception:
        return None


def _structure_signature_from_summary(meal_summary: dict[str, Any]) -> str:
    return get_meal_structure_signature(
        selected_role_codes=meal_summary.get("selected_role_codes", {}),
        support_food_specs=meal_summary.get("support_food_specs", []),
    )


def _get_meal_training_focus(run_result: dict[str, Any], meal_index: int) -> bool:
    meal_diagnostics = run_result["diagnostics"].get("meal_diagnostics", [])
    if meal_index < len(meal_diagnostics):
        return bool(meal_diagnostics[meal_index].get("training_focus"))
    meal_role = run_result["diet"]["meals"][meal_index]["meal_role"]
    return meal_role in {"pre_workout", "post_workout", "training_focus"}


def _run_generation(
    scenario: AuditScenario,
    *,
    run_index: int,
    force_legacy: bool,
) -> dict[str, Any]:
    user = _build_user(scenario, run_index=run_index)
    seed = _build_generation_seed(scenario, run_index)
    set_last_generation_diagnostics(None)

    def _seed_builder(*_parts: object) -> int:
        return seed

    def _forced_legacy_engine(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("forced legacy benchmark")

    start = time.perf_counter()
    generated: dict[str, Any] | None = None
    error: str | None = None
    try:
        if force_legacy:
            with _patched_attr(diet_service, "build_variety_seed", _seed_builder), _patched_attr(
                diet_service,
                "generate_day_meal_plans_v2",
                _forced_legacy_engine,
            ):
                generated = diet_service.generate_food_based_diet(
                    DATABASE,
                    user=user,
                    meals_count=scenario.meals_count,
                    training_time_of_day=scenario.training_time_of_day,
                )
        else:
            with _patched_attr(diet_service, "build_variety_seed", _seed_builder):
                generated = diet_service.generate_food_based_diet(
                    DATABASE,
                    user=user,
                    meals_count=scenario.meals_count,
                    training_time_of_day=scenario.training_time_of_day,
                )
    except Exception as exc:
        error = str(exc)
    elapsed_seconds = time.perf_counter() - start
    diagnostics = get_last_generation_diagnostics() or {}
    generated_meal_summaries = diagnostics.get("generated_meal_summaries", [])
    return {
        "scenario_id": scenario.id,
        "run_index": run_index,
        "seed": seed,
        "elapsed_seconds": elapsed_seconds,
        "diet": generated,
        "error": error,
        "diagnostics": diagnostics,
        "generated_meal_summaries": generated_meal_summaries,
    }


def _summarize_generation_examples(run_results: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for run_result in [result for result in run_results if result["diet"] is not None][:limit]:
        meal_summaries_by_index = {
            meal_summary["meal_index"]: meal_summary
            for meal_summary in run_result.get("generated_meal_summaries", [])
        }
        examples.append({
            "scenario_id": run_result["scenario_id"],
            "run_index": run_result["run_index"],
            "planning_engine": run_result["diagnostics"].get("planning_engine"),
            "meals": [
                _serialize_meal_example(
                    meal,
                    meal_summaries_by_index.get(index),
                )
                for index, meal in enumerate(run_result["diet"]["meals"])
            ],
        })
    return examples


def _aggregate_phase_timings(run_results: list[dict[str, Any]], *, key: str) -> dict[str, float]:
    phase_values: dict[str, list[float]] = {}
    for run_result in run_results:
        if run_result["diet"] is None:
            continue
        phase_timings = run_result["diagnostics"].get(key, {})
        for phase_name, value in phase_timings.items():
            phase_values.setdefault(phase_name, []).append(float(value))
    return {
        phase_name: round(statistics.mean(values), 6)
        for phase_name, values in sorted(phase_values.items())
        if values
    }


def _collect_structure_metrics(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    breakfast_blueprint_counts: dict[str, int] = {}
    breakfast_dairy_cereal_count = 0
    total_breakfasts = 0
    diets_with_repeated_blueprints = 0
    diets_with_repeated_proteins = 0
    diets_with_repeated_carbs = 0
    diets_with_repeated_pairs = 0
    diets_with_repeated_structures = 0
    diets_with_consecutive_repeated_structures = 0
    diets_with_repeated_chicken_rice = 0
    repeated_protein_examples: list[dict[str, Any]] = []
    top_proteins: dict[str, int] = {}
    top_carbs: dict[str, int] = {}
    top_pairs: dict[str, int] = {}
    top_structures: dict[str, int] = {}

    for run_result in run_results:
        if run_result["diet"] is None:
            continue
        meal_summaries = [
            _infer_visible_meal_summary(run_result, meal_payload)
            for meal_payload in run_result["diet"]["meals"]
        ]
        if any(meal_summary is None for meal_summary in meal_summaries):
            continue
        meal_summaries = [meal_summary for meal_summary in meal_summaries if meal_summary is not None]

        structure_signatures = [_structure_signature_from_summary(meal_summary) for meal_summary in meal_summaries]
        protein_codes = [meal_summary["selected_role_codes"].get("protein") for meal_summary in meal_summaries]
        carb_codes = [meal_summary["selected_role_codes"].get("carb") for meal_summary in meal_summaries]
        pair_codes = [
            f"{meal_summary['selected_role_codes'].get('protein')}::{meal_summary['selected_role_codes'].get('carb')}"
            for meal_summary in meal_summaries
        ]

        generated_meal_summaries = run_result.get("generated_meal_summaries", [])
        if len(generated_meal_summaries) == len(run_result["diet"]["meals"]):
            blueprint_ids = [meal_summary.get("applied_blueprint_id") for meal_summary in generated_meal_summaries]
            if len(blueprint_ids) != len(set(blueprint_ids)):
                diets_with_repeated_blueprints += 1
        if len(protein_codes) != len(set(protein_codes)):
            diets_with_repeated_proteins += 1
            repeated_protein_examples.append({
                "scenario_id": run_result["scenario_id"],
                "run_index": run_result["run_index"],
                "proteins": protein_codes,
            })
        if len(carb_codes) != len(set(carb_codes)):
            diets_with_repeated_carbs += 1
        if len(pair_codes) != len(set(pair_codes)):
            diets_with_repeated_pairs += 1
        if len(structure_signatures) != len(set(structure_signatures)):
            diets_with_repeated_structures += 1
        if any(
            structure_signatures[index] == structure_signatures[index + 1]
            for index in range(len(structure_signatures) - 1)
        ):
            diets_with_consecutive_repeated_structures += 1
        if pair_codes.count("chicken_breast::rice") > 1:
            diets_with_repeated_chicken_rice += 1

        for meal_summary in meal_summaries:
            protein_code = meal_summary["selected_role_codes"].get("protein")
            carb_code = meal_summary["selected_role_codes"].get("carb")
            pair_code = f"{protein_code}::{carb_code}"
            structure_signature = _structure_signature_from_summary(meal_summary)
            if protein_code:
                top_proteins[protein_code] = top_proteins.get(protein_code, 0) + 1
            if carb_code:
                top_carbs[carb_code] = top_carbs.get(carb_code, 0) + 1
            top_pairs[pair_code] = top_pairs.get(pair_code, 0) + 1
            top_structures[structure_signature] = top_structures.get(structure_signature, 0) + 1

        breakfast_summary = next((meal_summaries[index] for index, meal_payload in enumerate(run_result["diet"]["meals"]) if meal_payload["meal_role"] == "breakfast"), None)
        if breakfast_summary is not None:
            total_breakfasts += 1
            breakfast_index = next(index for index, meal_payload in enumerate(run_result["diet"]["meals"]) if meal_payload["meal_role"] == "breakfast")
            if len(generated_meal_summaries) == len(run_result["diet"]["meals"]):
                blueprint_id = str(generated_meal_summaries[breakfast_index].get("applied_blueprint_id") or "unknown")
                breakfast_blueprint_counts[blueprint_id] = breakfast_blueprint_counts.get(blueprint_id, 0) + 1
            protein_code = breakfast_summary["selected_role_codes"].get("protein")
            carb_code = breakfast_summary["selected_role_codes"].get("carb")
            if protein_code == "greek_yogurt" and carb_code in {"oats", "cornflakes"}:
                breakfast_dairy_cereal_count += 1

    total_diets = max(len(run_results), 1)
    return {
        "breakfast_blueprint_counts": dict(sorted(breakfast_blueprint_counts.items(), key=lambda item: (-item[1], item[0]))),
        "breakfast_dairy_cereal_rate": round(breakfast_dairy_cereal_count / max(total_breakfasts, 1), 4),
        "repeated_blueprint_diet_rate": round(diets_with_repeated_blueprints / total_diets, 4),
        "repeated_structure_diet_rate": round(diets_with_repeated_structures / total_diets, 4),
        "repeated_consecutive_structure_diet_rate": round(diets_with_consecutive_repeated_structures / total_diets, 4),
        "repeated_protein_diet_rate": round(diets_with_repeated_proteins / total_diets, 4),
        "repeated_carb_diet_rate": round(diets_with_repeated_carbs / total_diets, 4),
        "repeated_pair_diet_rate": round(diets_with_repeated_pairs / total_diets, 4),
        "repeated_chicken_rice_diet_rate": round(diets_with_repeated_chicken_rice / total_diets, 4),
        "top_proteins": dict(sorted(top_proteins.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "top_carbs": dict(sorted(top_carbs.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "top_pairs": dict(sorted(top_pairs.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "top_structures": dict(sorted(top_structures.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "repeated_protein_examples": repeated_protein_examples[:5],
    }


def _collect_coherence_metrics(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = get_internal_food_lookup()
    meals_with_duplicate_food_codes = 0
    meals_with_duplicate_families = 0
    meals_with_duplicate_visible_names = 0
    total_meals = 0
    duplicate_family_examples: list[dict[str, Any]] = []

    for run_result in run_results:
        if run_result["diet"] is None:
            continue
        meal_summaries = [
            _infer_visible_meal_summary(run_result, meal_payload)
            for meal_payload in run_result["diet"]["meals"]
        ]
        if any(meal_summary is None for meal_summary in meal_summaries):
            continue
        meal_summaries = [meal_summary for meal_summary in meal_summaries if meal_summary is not None]
        for index, meal_summary in enumerate(meal_summaries):
            meal_payload = run_result["diet"]["meals"][index]
            total_meals += 1
            all_codes = list(meal_summary.get("selected_role_codes", {}).values()) + [
                support_food["food_code"]
                for support_food in meal_summary.get("support_food_specs", [])
            ]
            if len(all_codes) != len(set(all_codes)):
                meals_with_duplicate_food_codes += 1

            family_ids: list[str] = []
            for role, food_code in meal_summary.get("selected_role_codes", {}).items():
                if food_code in lookup:
                    family_ids.append(get_primary_family_id(lookup[food_code], role=role))
            for support_food in meal_summary.get("support_food_specs", []):
                support_code = support_food["food_code"]
                if support_code in lookup:
                    family_ids.append(get_primary_family_id(lookup[support_code], role=support_food["role"]))
            if len(family_ids) != len(set(family_ids)):
                meals_with_duplicate_families += 1
                duplicate_family_examples.append({
                    "scenario_id": run_result["scenario_id"],
                    "run_index": run_result["run_index"],
                    "meal_number": meal_payload["meal_number"],
                    "foods": [food["name"] for food in meal_payload["foods"]],
                    "families": family_ids,
                })

            visible_names = [food["name"].strip().lower() for food in meal_payload["foods"]]
            if len(visible_names) != len(set(visible_names)):
                meals_with_duplicate_visible_names += 1

    total_meals = max(total_meals, 1)
    return {
        "duplicate_food_code_rate": round(meals_with_duplicate_food_codes / total_meals, 4),
        "duplicate_family_rate": round(meals_with_duplicate_families / total_meals, 4),
        "duplicate_visible_name_rate": round(meals_with_duplicate_visible_names / total_meals, 4),
        "duplicate_family_examples": duplicate_family_examples[:5],
    }


def _benchmark_regenerations(current_run_results: list[dict[str, Any]]) -> dict[str, Any]:
    regeneration_results: list[dict[str, Any]] = []
    examples: list[dict[str, Any]] = []
    lookup = get_internal_food_lookup()

    for run_result in current_run_results:
        if run_result["diet"] is None:
            continue
        if run_result["diagnostics"].get("planning_engine") != "v2":
            continue
        user = _build_user(next(scenario for scenario in SCENARIOS if scenario.id == run_result["scenario_id"]), run_index=run_result["run_index"])
        preference_profile = build_user_food_preferences_profile(user)
        meal_summaries = run_result.get("generated_meal_summaries", [])
        if len(meal_summaries) != len(run_result["diet"]["meals"]):
            continue

        for meal_index, meal_payload in enumerate(run_result["diet"]["meals"]):
            current_meal_plan = meal_summaries[meal_index]
            current_food_codes = {
                food["food_code"]
                for food in meal_payload["foods"]
            }
            daily_food_usage = create_daily_food_usage_tracker()
            for other_index, other_meal_plan in enumerate(meal_summaries):
                if other_index == meal_index:
                    continue
                track_food_usage_across_day(daily_food_usage, other_meal_plan)

            meal_model = DietMeal.model_validate(meal_payload)
            seed = _stable_int("regeneration", run_result["scenario_id"], run_result["run_index"], meal_index, modulo=1_000_000_000)
            set_last_regeneration_diagnostics(None)
            regen_start = time.perf_counter()
            regenerated_plan = regenerate_meal_plan_v2(
                meal=meal_model,
                meal_index=meal_index,
                meals_count=run_result["diet"]["meals_count"],
                training_focus=_get_meal_training_focus(run_result, meal_index),
                meal_slot=meal_payload["meal_slot"],
                meal_role=meal_payload["meal_role"],
                food_lookup=lookup,
                preference_profile=preference_profile,
                daily_food_usage=daily_food_usage,
                weekly_food_usage={},
                current_food_codes=current_food_codes,
                current_meal_plan=current_meal_plan,
                variety_seed=seed,
            )
            v2_elapsed = time.perf_counter() - regen_start
            regen_diag = get_last_regeneration_diagnostics() or {}
            used_legacy = regenerated_plan is None
            legacy_elapsed = 0.0
            regeneration_error: str | None = None
            if used_legacy:
                try:
                    legacy_start = time.perf_counter()
                    regenerated_plan = meal_regeneration_service._solve_regenerated_meal_plan(
                        meal=meal_model,
                        meal_index=meal_index,
                        meals_count=run_result["diet"]["meals_count"],
                        training_focus=_get_meal_training_focus(run_result, meal_index),
                        full_food_lookup=lookup,
                        current_meal_food_lookup=lookup,
                        preference_profile=preference_profile,
                        daily_food_usage=daily_food_usage,
                        current_food_codes=current_food_codes,
                        variety_seed=seed,
                    )
                    legacy_elapsed = time.perf_counter() - legacy_start
                except Exception as exc:
                    regeneration_error = str(exc)
                    regeneration_results.append({
                        "scenario_id": run_result["scenario_id"],
                        "run_index": run_result["run_index"],
                        "meal_number": meal_payload["meal_number"],
                        "current_blueprint_id": current_meal_plan.get("applied_blueprint_id"),
                        "regenerated_blueprint_id": None,
                        "blueprint_changed": False,
                        "base_changed": False,
                        "visible_change_count": 0,
                        "changed_roles": [],
                        "used_legacy": True,
                        "v2_elapsed_seconds": v2_elapsed,
                        "legacy_elapsed_seconds": legacy_elapsed,
                        "regeneration_diagnostics": regen_diag,
                        "regeneration_error": regeneration_error,
                        "before_foods": [food["name"] for food in meal_payload["foods"]],
                        "after_foods": [],
                    })
                    continue
            difference = summarize_visible_difference(
                current_meal_plan=current_meal_plan,
                current_food_codes=current_food_codes,
                candidate_plan=regenerated_plan,
            )
            base_changed = any(
                current_meal_plan["selected_role_codes"].get(role) != regenerated_plan["selected_role_codes"].get(role)
                for role in ("protein", "carb")
            )
            result_entry = {
                "scenario_id": run_result["scenario_id"],
                "run_index": run_result["run_index"],
                "meal_number": meal_payload["meal_number"],
                "current_blueprint_id": current_meal_plan.get("applied_blueprint_id"),
                "regenerated_blueprint_id": regenerated_plan.get("applied_blueprint_id"),
                "blueprint_changed": current_meal_plan.get("applied_blueprint_id") != regenerated_plan.get("applied_blueprint_id"),
                "base_changed": base_changed,
                "visible_change_count": difference["visible_change_count"],
                "changed_roles": difference["changed_roles"],
                "used_legacy": used_legacy,
                "v2_elapsed_seconds": v2_elapsed,
                "legacy_elapsed_seconds": legacy_elapsed,
                "regeneration_diagnostics": regen_diag,
                "regeneration_error": regeneration_error,
                "before_foods": [food["name"] for food in meal_payload["foods"]],
                "after_foods": [food["name"] for food in regenerated_plan.get("foods", [])],
            }
            regeneration_results.append(result_entry)
            if len(examples) < 6 and (
                result_entry["blueprint_changed"]
                or result_entry["visible_change_count"] >= 2
                or result_entry["used_legacy"]
            ):
                examples.append({
                    "scenario_id": result_entry["scenario_id"],
                    "run_index": result_entry["run_index"],
                    "meal_number": result_entry["meal_number"],
                    "before_blueprint": result_entry["current_blueprint_id"],
                    "after_blueprint": result_entry["regenerated_blueprint_id"],
                    "before_foods": result_entry["before_foods"],
                    "after_foods": result_entry["after_foods"],
                    "visible_change_count": result_entry["visible_change_count"],
                    "used_legacy": result_entry["used_legacy"],
                })

    total_regenerations = max(len(regeneration_results), 1)
    return {
        "total_regenerations": len(regeneration_results),
        "legacy_fallback_rate": round(
            sum(1 for result in regeneration_results if result["used_legacy"]) / total_regenerations,
            4,
        ),
        "blueprint_changed_rate": round(
            sum(1 for result in regeneration_results if result["blueprint_changed"]) / total_regenerations,
            4,
        ),
        "base_changed_rate": round(
            sum(1 for result in regeneration_results if result["base_changed"]) / total_regenerations,
            4,
        ),
        "visible_two_plus_rate": round(
            sum(1 for result in regeneration_results if result["visible_change_count"] >= 2) / total_regenerations,
            4,
        ),
        "avg_v2_elapsed_seconds": round(
            statistics.mean(result["v2_elapsed_seconds"] for result in regeneration_results),
            6,
        ) if regeneration_results else 0.0,
        "max_v2_elapsed_seconds": round(
            max(result["v2_elapsed_seconds"] for result in regeneration_results),
            6,
        ) if regeneration_results else 0.0,
        "examples": examples,
    }


def _build_report() -> dict[str, Any]:
    current_run_results: list[dict[str, Any]] = []
    legacy_run_results: list[dict[str, Any]] = []

    for scenario in SCENARIOS:
        for run_index in range(RUNS_PER_SCENARIO):
            current_run_results.append(_run_generation(scenario, run_index=run_index, force_legacy=False))
            legacy_run_results.append(_run_generation(scenario, run_index=run_index, force_legacy=True))

    current_successful_runs = [run_result for run_result in current_run_results if run_result["diet"] is not None]
    legacy_successful_runs = [run_result for run_result in legacy_run_results if run_result["diet"] is not None]
    current_elapsed = [run_result["elapsed_seconds"] for run_result in current_successful_runs]
    legacy_elapsed = [run_result["elapsed_seconds"] for run_result in legacy_successful_runs]
    current_successful_by_key = {
        (run_result["scenario_id"], run_result["run_index"]): run_result
        for run_result in current_successful_runs
    }
    legacy_successful_by_key = {
        (run_result["scenario_id"], run_result["run_index"]): run_result
        for run_result in legacy_successful_runs
    }
    paired_keys = sorted(set(current_successful_by_key).intersection(legacy_successful_by_key))
    paired_current_elapsed = [current_successful_by_key[key]["elapsed_seconds"] for key in paired_keys]
    paired_legacy_elapsed = [legacy_successful_by_key[key]["elapsed_seconds"] for key in paired_keys]
    fallback_runs = [
        run_result
        for run_result in current_successful_runs
        if run_result["diagnostics"].get("planning_engine") == "legacy_fallback"
    ]
    fallback_reason_counts: dict[str, int] = {}
    fallback_slot_counts: dict[str, int] = {}
    for run_result in fallback_runs:
        resolution_summary = run_result["diagnostics"].get("resolution_summary", {})
        fallback_reason = str(resolution_summary.get("fallback_reason") or "unknown")
        fallback_reason_counts[fallback_reason] = fallback_reason_counts.get(fallback_reason, 0) + 1
        failed_index = resolution_summary.get("fallback_failed_meal_index")
        meal_diagnostics = run_result["diagnostics"].get("meal_diagnostics", [])
        if isinstance(failed_index, int) and failed_index < len(meal_diagnostics):
            failed_slot = str(meal_diagnostics[failed_index].get("meal_slot") or "unknown")
            fallback_slot_counts[failed_slot] = fallback_slot_counts.get(failed_slot, 0) + 1

    current_service_phase_means = _aggregate_phase_timings(current_successful_runs, key="service_phase_timings")
    current_engine_phase_means = _aggregate_phase_timings(current_successful_runs, key="phase_timings")
    current_meal_elapsed = [
        float(meal_diag["elapsed_seconds"])
        for run_result in current_successful_runs
        for meal_diag in run_result["diagnostics"].get("meal_diagnostics", [])
    ]

    current_exact_meals = sum(
        int(run_result["diagnostics"].get("resolution_summary", {}).get("exact_fit_meals", 0))
        for run_result in current_successful_runs
    )
    current_approx_meals = sum(
        int(run_result["diagnostics"].get("resolution_summary", {}).get("approximate_fit_meals", 0))
        for run_result in current_successful_runs
    )

    variety_current = _collect_structure_metrics(current_successful_runs)
    variety_legacy = _collect_structure_metrics(legacy_successful_runs)
    coherence_metrics = _collect_coherence_metrics(current_successful_runs)
    regeneration_metrics = _benchmark_regenerations(current_successful_runs)

    return {
        "audit_config": {
            "scenario_count": len(SCENARIOS),
            "runs_per_scenario": RUNS_PER_SCENARIO,
            "total_generation_runs": len(current_run_results),
            "current_successful_runs": len(current_successful_runs),
            "legacy_successful_runs": len(legacy_successful_runs),
        },
        "route_dominance": {
            "v2_service_runs": len(current_successful_runs) - len(fallback_runs),
            "legacy_fallback_runs": len(fallback_runs),
            "legacy_fallback_rate": round(len(fallback_runs) / max(len(current_successful_runs), 1), 4) if current_successful_runs else 0.0,
            "v2_resolved_meals": current_exact_meals + current_approx_meals,
            "v2_exact_fit_meals": current_exact_meals,
            "v2_approximate_fit_meals": current_approx_meals,
            "fallback_reason_counts": dict(sorted(fallback_reason_counts.items())),
            "fallback_slot_counts": dict(sorted(fallback_slot_counts.items())),
            "current_generation_failures": [
                {
                    "scenario_id": run_result["scenario_id"],
                    "run_index": run_result["run_index"],
                    "error": run_result["error"],
                }
                for run_result in current_run_results
                if run_result["diet"] is None
            ],
        },
        "benchmark": {
            "current_mean_seconds": round(statistics.mean(current_elapsed), 6) if current_elapsed else 0.0,
            "current_min_seconds": round(min(current_elapsed), 6) if current_elapsed else 0.0,
            "current_max_seconds": round(max(current_elapsed), 6) if current_elapsed else 0.0,
            "legacy_mean_seconds": round(statistics.mean(legacy_elapsed), 6) if legacy_elapsed else 0.0,
            "legacy_min_seconds": round(min(legacy_elapsed), 6) if legacy_elapsed else 0.0,
            "legacy_max_seconds": round(max(legacy_elapsed), 6) if legacy_elapsed else 0.0,
            "mean_speedup_ratio_vs_legacy": round(statistics.mean(legacy_elapsed) / max(statistics.mean(current_elapsed), 1e-9), 4) if current_elapsed and legacy_elapsed else None,
            "paired_successful_run_count": len(paired_keys),
            "paired_current_mean_seconds": round(statistics.mean(paired_current_elapsed), 6) if paired_current_elapsed else 0.0,
            "paired_legacy_mean_seconds": round(statistics.mean(paired_legacy_elapsed), 6) if paired_legacy_elapsed else 0.0,
            "paired_speedup_ratio_vs_legacy": round(
                statistics.mean(paired_legacy_elapsed) / max(statistics.mean(paired_current_elapsed), 1e-9),
                4,
            ) if paired_current_elapsed and paired_legacy_elapsed else None,
            "current_service_phase_means": current_service_phase_means,
            "current_engine_phase_means": current_engine_phase_means,
            "avg_meal_elapsed_seconds": round(statistics.mean(current_meal_elapsed), 6) if current_meal_elapsed else 0.0,
            "max_meal_elapsed_seconds": round(max(current_meal_elapsed), 6) if current_meal_elapsed else 0.0,
            "legacy_generation_failures": [
                {
                    "scenario_id": run_result["scenario_id"],
                    "run_index": run_result["run_index"],
                    "error": run_result["error"],
                }
                for run_result in legacy_run_results
                if run_result["diet"] is None
            ],
        },
        "variety_current": variety_current,
        "variety_legacy": variety_legacy,
        "coherence": coherence_metrics,
        "regeneration": regeneration_metrics,
        "generation_examples": _summarize_generation_examples(current_run_results),
    }


def main() -> None:
    report = _build_report()
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nAudit report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
