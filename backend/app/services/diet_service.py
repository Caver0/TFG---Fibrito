"""Orquestador y capa de compatibilidad para la logica de dietas."""

import logging
import time
from typing import Any

from app.schemas.diet import DietMeal, TrainingTimeOfDay
from app.schemas.user import UserPublic
from app.services.food_catalog_service import get_food_catalog_version, get_internal_food_lookup, resolve_foods_by_codes
from app.services.food_preferences_service import build_user_food_preferences_profile, count_preferred_food_matches_in_meals
from app.services.meal_coherence_service import apply_generation_coherence, build_generation_food_lookup
from app.services.meal_distribution_service import generate_meal_distribution_targets

from app.services.diet.candidates import (
    apply_daily_usage_candidate_limits,
    apply_main_pair_repeat_penalty,
    apply_meal_candidate_constraints,
    apply_preference_priority,
    apply_repeat_penalty,
    apply_support_option_constraints,
    apply_user_food_preferences_to_meal_candidates,
    apply_weekly_repeat_penalty,
    build_weekly_food_usage,
    create_daily_food_usage_tracker,
    get_allowed_meal_slots_for_food,
    get_candidate_role_for_food,
    get_food_fat_density,
    get_food_macro_mass_profile,
    get_food_role_fit_score,
    get_food_slot_affinity_score,
    get_food_text_signature,
    get_food_usage_summary_from_meals,
    get_role_candidate_codes,
    get_support_candidate_foods,
    get_support_food_fit_score,
    get_support_option_specs,
    is_breakfast_fat,
    is_breakfast_only_protein,
    is_cooking_fat,
    is_fast_digesting_carb,
    is_food_allowed_for_role_and_slot,
    is_lean_protein_candidate,
    is_role_combination_coherent,
    is_savory_protein,
    is_savory_starch,
    is_support_food_allowed,
    is_sweet_breakfast_carb,
    sort_codes_by_meal_fit,
    sort_codes_by_slot_affinity,
    track_food_usage_across_day,
)
from app.services.diet.common import (
    build_variety_seed,
    calculate_difference,
    calculate_difference_summary,
    calculate_macro_calories,
    get_meal_slot,
    normalize_diet_food_source,
    normalize_meal_role,
    normalize_meal_slot,
    resolve_meal_context,
    rotate_codes,
    round_diet_value,
    round_food_value,
)
from app.services.diet.constants import (
    CACHE_FOOD_DATA_SOURCE,
    CATALOG_SOURCE_STRATEGY_DEFAULT,
    DEFAULT_FOOD_DATA_SOURCE,
    EXACT_SOLVER_TOLERANCE,
    SPOONACULAR_FOOD_DATA_SOURCE,
)
from app.services.diet_runtime_audit import emit_runtime_audit
from app.services.diet.payloads import (
    build_updated_diet_payload,
    calculate_daily_totals_from_meals,
    calculate_resolution_counters_from_meals,
    collect_selected_food_codes,
    generate_food_based_meal,
    summarize_food_sources,
)
from app.services.diet.persistence import (
    _build_diet_lifecycle_fields,
    _build_persistable_diet_fields,
    _build_persistable_food_payload,
    _build_persistable_meal_payload,
    _deactivate_user_active_diets,
    _get_optional_diet_object_id,
    _get_user_object_id,
    activate_user_diet,
    get_active_user_diet,
    get_active_user_diet_document,
    get_latest_user_diet,
    get_user_diet_by_id,
    get_user_diet_document_by_id,
    list_user_diets,
    save_diet,
    update_diet,
)
from app.services.diet.solver import (
    build_culinary_pairing_adjustment,
    build_exact_meal_solution,
    build_food_portion,
    build_hidden_fat_penalty,
    build_precise_food_values,
    build_solution_score,
    calculate_meal_actuals_from_foods,
    calculate_meal_totals_from_foods,
    calculate_support_totals,
    find_exact_solution_for_meal,
    get_food_macro_density,
    get_food_visibility_threshold,
    get_role_serving_floor,
    get_soft_role_minimum,
    solve_linear_system,
)
from app.services.diet_v2 import generate_day_meal_plans_v2
from app.services.diet_v2.nutrition_validation import summarize_daily_payload_nutrition, summarize_meal_payload_nutrition
from app.services.diet_v2.telemetry import get_last_generation_diagnostics, set_last_generation_diagnostics

logger = logging.getLogger(__name__)

STRICT_V2_GENERATION_SEED_OFFSETS: tuple[int, ...] = (0, 17, 53, 97, 149, 211)
STRICT_LEGACY_GENERATION_SEED_OFFSETS: tuple[int, ...] = (0, 29, 61)


def _meal_payload_supports_strict_validation(meal_payload: dict[str, Any]) -> bool:
    required_fields = (
        "target_calories",
        "target_protein_grams",
        "target_fat_grams",
        "target_carb_grams",
        "actual_calories",
        "actual_protein_grams",
        "actual_fat_grams",
        "actual_carb_grams",
        "foods",
    )
    return all(field_name in meal_payload for field_name in required_fields)


def _summarize_generated_payload_validation(
    *,
    meal_distribution: dict[str, Any],
    generated_meals: list[dict[str, Any]],
) -> dict[str, Any]:
    if not generated_meals or any(not _meal_payload_supports_strict_validation(meal_payload) for meal_payload in generated_meals):
        return {
            "validation_skipped": True,
            "within_tolerance": True,
            "invalid_meal_indexes": [],
            "meal_validations": [],
            "daily_validation": {
                "validation_skipped": True,
                "within_tolerance": True,
                "out_of_tolerance_fields": [],
                "normalized_error_score": 0.0,
                "normalized_overflow_score": 0.0,
            },
        }

    meal_validations = [
        summarize_meal_payload_nutrition(
            target_calories=float(meal_payload["target_calories"]),
            target_protein_grams=float(meal_payload["target_protein_grams"]),
            target_fat_grams=float(meal_payload["target_fat_grams"]),
            target_carb_grams=float(meal_payload["target_carb_grams"]),
            foods=list(meal_payload.get("foods", [])),
            actuals_override={
                "actual_calories": float(meal_payload["actual_calories"]),
                "actual_protein_grams": float(meal_payload["actual_protein_grams"]),
                "actual_fat_grams": float(meal_payload["actual_fat_grams"]),
                "actual_carb_grams": float(meal_payload["actual_carb_grams"]),
            },
        )
        for meal_payload in generated_meals
    ]
    daily_validation = summarize_daily_payload_nutrition(
        target_calories=float(meal_distribution["target_calories"]),
        target_protein_grams=float(meal_distribution["protein_grams"]),
        target_fat_grams=float(meal_distribution["fat_grams"]),
        target_carb_grams=float(meal_distribution["carb_grams"]),
        meals=generated_meals,
    )
    invalid_meal_indexes = [
        meal_index
        for meal_index, meal_validation in enumerate(meal_validations)
        if not meal_validation["within_tolerance"]
    ]
    return {
        "validation_skipped": False,
        "within_tolerance": daily_validation["within_tolerance"] and not invalid_meal_indexes,
        "invalid_meal_indexes": invalid_meal_indexes,
        "meal_validations": meal_validations,
        "daily_validation": daily_validation,
    }


def _score_generation_candidate(strict_validation: dict[str, Any]) -> float:
    if strict_validation.get("validation_skipped"):
        return 0.0
    daily_validation = dict(strict_validation.get("daily_validation") or {})
    meal_validations = list(strict_validation.get("meal_validations") or [])
    return (
        float(daily_validation.get("normalized_overflow_score") or 0.0) * 3.0
        + float(daily_validation.get("normalized_error_score") or 0.0) * 2.0
        + sum(float(meal_validation.get("normalized_overflow_score") or 0.0) for meal_validation in meal_validations)
        + sum(float(meal_validation.get("normalized_error_score") or 0.0) for meal_validation in meal_validations)
    )


def generate_food_based_diet(
    database,
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    generation_started_at = time.perf_counter()
    phase_timings: dict[str, float] = {}
    emit_runtime_audit(
        "diet_generation_service_started",
        {
            "meals_count": meals_count,
            "training_time_of_day": training_time_of_day,
        },
    )
    phase_started_at = time.perf_counter()
    preference_profile = build_user_food_preferences_profile(user)
    meal_distribution, focus_indexes = generate_meal_distribution_targets(
        user=user,
        meals_count=meals_count,
        custom_percentages=custom_percentages,
        training_time_of_day=training_time_of_day,
    )
    internal_food_lookup = get_internal_food_lookup()
    full_food_lookup = build_generation_food_lookup(
        database,
        internal_food_lookup=internal_food_lookup,
    )
    generation_variety_seed = build_variety_seed(
        user.id,
        meals_count,
        training_time_of_day,
        custom_percentages or [],
        sorted(preference_profile.get("preferred_foods", [])),
        sorted(preference_profile.get("disliked_foods", [])),
        sorted(preference_profile.get("dietary_restrictions", [])),
        sorted(preference_profile.get("allergies", [])),
    )

    daily_food_usage = create_daily_food_usage_tracker()
    weekly_food_usage = build_weekly_food_usage(database, user.id)
    phase_timings["setup"] = time.perf_counter() - phase_started_at

    # Calcular contexto de cada comida (slot, rol, foco de entrenamiento)
    # antes del loop para poder pasarlo al resolvedor de anclas sin duplicar lógica.
    phase_started_at = time.perf_counter()
    meals_context: list[dict] = []
    for meal_index, meal in enumerate(meal_distribution["meals"]):
        training_focus_i = meal_distribution["training_optimization_applied"] and meal_index in focus_indexes
        meal_slot_i, meal_role_i = resolve_meal_context(
            DietMeal.model_validate(meal),
            meal_index=meal_index,
            meals_count=meals_count,
            training_focus=training_focus_i,
        )
        meals_context.append({
            "meal_slot": meal_slot_i,
            "meal_role": meal_role_i,
            "training_focus": training_focus_i,
        })
    phase_timings["meal_context"] = time.perf_counter() - phase_started_at

    # ── Fase previa: inyectar alimentos preferidos en full_food_lookup ───────────────────────
    # Si el usuario indicó alimentos preferidos que no existen en el catálogo interno ni
    # en la base de datos local, intentamos resolverlos desde Spoonacular/caché y añadirlos
    # al lookup de trabajo ANTES de calcular anclas y generar comidas.
    # Sin este paso, 'buscar_alimentos_por_nombre' devuelve [] para esos alimentos y todo
    # el sistema de anclas/soportes queda inoperativo aunque la normalización sea correcta.
    phase_started_at = time.perf_counter()
    if preference_profile.get("has_positive_preferences"):
        from app.services.preferred_food_resolver import enrich_lookup_con_preferidos
        enrich_lookup_con_preferidos(
            database,
            preferred_foods=preference_profile.get("preferred_foods", []),
            full_food_lookup=full_food_lookup,
        )

    # Resolver qué alimentos preferidos anclar en qué comidas antes de iniciar el solver.
    # Solo se ejecuta si el usuario especificó alimentos que quiere que aparezcan.
    anclas_por_comida: dict[int, dict[str, str]] = {}
    soporte_por_comida: dict[int, list[dict]] = {}
    if preference_profile.get("has_positive_preferences"):
        from app.services.diet.preference_anchors import resolver_anclas_preferidas
        resultado_anclas = resolver_anclas_preferidas(
            preferred_foods=preference_profile.get("preferred_foods", []),
            food_lookup=full_food_lookup,
            meal_slots=[ctx["meal_slot"] for ctx in meals_context],
            meal_roles=[ctx["meal_role"] for ctx in meals_context],
            training_focus_flags=[ctx["training_focus"] for ctx in meals_context],
        )
        anclas_por_comida = resultado_anclas["anclas"]
        soporte_por_comida = resultado_anclas.get("soporte", {})
        # Los diagnósticos quedan en el perfil para depuración y para el campo de respuesta
        preference_profile["anchor_diagnostics"] = resultado_anclas["diagnosticos"]
    phase_timings["preference_anchors"] = time.perf_counter() - phase_started_at

    phase_started_at = time.perf_counter()
    planning_attempts: list[dict[str, Any]] = []
    accepted_candidate: dict[str, Any] | None = None
    best_rejected_candidate: dict[str, Any] | None = None
    best_rejected_score: float | None = None

    def build_candidate_payload(
        *,
        coherent_planned_meals: list[dict[str, Any]],
        planning_engine_name: str,
        seed_offset: int,
        planning_diagnostics: dict[str, Any] | None,
        extra_phase_timings: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        food_resolution_started_at = time.perf_counter()
        selected_food_codes = collect_selected_food_codes(coherent_planned_meals)
        internal_codes_to_resolve = [code for code in selected_food_codes if code in internal_food_lookup]
        if internal_codes_to_resolve:
            resolved_food_lookup, lookup_metadata = resolve_foods_by_codes(
                database,
                internal_codes_to_resolve,
                allow_external_enrichment=False,
            )
        else:
            resolved_food_lookup = {}
            lookup_metadata = {
                "food_catalog_version": get_food_catalog_version(),
                "catalog_source_strategy": CATALOG_SOURCE_STRATEGY_DEFAULT,
                "spoonacular_attempted": False,
                "spoonacular_attempts": 0,
                "resolved_foods_count": len(selected_food_codes),
            }
        if not internal_codes_to_resolve:
            lookup_metadata["resolved_foods_count"] = len(selected_food_codes)
        resolved_food_lookup_time = time.perf_counter() - food_resolution_started_at
        payload_started_at = time.perf_counter()
        generated_meals = [
            generate_food_based_meal(
                meal=DietMeal.model_validate(meal),
                meal_index=meal_index,
                meals_count=meals_count,
                training_focus=meal_distribution["training_optimization_applied"] and meal_index in focus_indexes,
                meal_plan=coherent_planned_meals[meal_index],
                food_lookup={
                    **full_food_lookup,
                    **resolved_food_lookup,
                },
            )
            for meal_index, meal in enumerate(meal_distribution["meals"])
        ]
        food_data_source, food_data_sources = summarize_food_sources(generated_meals)
        preferred_food_matches = count_preferred_food_matches_in_meals(generated_meals, preference_profile)
        daily_totals = calculate_daily_totals_from_meals(
            target_calories=meal_distribution["target_calories"],
            target_protein_grams=meal_distribution["protein_grams"],
            target_fat_grams=meal_distribution["fat_grams"],
            target_carb_grams=meal_distribution["carb_grams"],
            meals=generated_meals,
        )
        strict_payload_validation = _summarize_generated_payload_validation(
            meal_distribution=meal_distribution,
            generated_meals=generated_meals,
        )
        payload_build_time = time.perf_counter() - payload_started_at
        return {
            "planning_engine": planning_engine_name,
            "seed_offset": seed_offset,
            "coherent_planned_meals": coherent_planned_meals,
            "selected_food_codes": selected_food_codes,
            "lookup_metadata": lookup_metadata,
            "generated_meals": generated_meals,
            "food_data_source": food_data_source,
            "food_data_sources": food_data_sources,
            "preferred_food_matches": preferred_food_matches,
            "daily_totals": daily_totals,
            "strict_payload_validation": strict_payload_validation,
            "generation_diagnostics": dict(planning_diagnostics or {}),
            "phase_timings": {
                **dict(extra_phase_timings or {}),
                "food_resolution": resolved_food_lookup_time,
                "payload_build": payload_build_time,
            },
        }

    for seed_offset in STRICT_V2_GENERATION_SEED_OFFSETS:
        attempt_daily_food_usage = create_daily_food_usage_tracker()
        attempt_phase_timings: dict[str, float] = {}
        try:
            v2_result = generate_day_meal_plans_v2(
                meal_distribution=meal_distribution,
                meals_context=meals_context,
                meals_count=meals_count,
                food_lookup=full_food_lookup,
                preference_profile=preference_profile,
                daily_food_usage=attempt_daily_food_usage,
                weekly_food_usage=weekly_food_usage,
                forced_role_codes_by_meal=anclas_por_comida,
                preferred_support_candidates_by_meal=soporte_por_comida,
                variety_seed=generation_variety_seed + seed_offset,
            )
            coherent_planned_meals = list(v2_result.get("meal_plans", []))
            if v2_result.get("used_legacy_fallback") or len(coherent_planned_meals) != len(meal_distribution["meals"]):
                raise RuntimeError("diet_v2 returned incomplete meal plans")
            attempt_phase_timings["v2_day_planning"] = v2_result.get("phase_timings", {}).get("day_planning", 0.0)
            attempt_phase_timings["v2_instantiation"] = v2_result.get("phase_timings", {}).get("instantiation_and_fit", 0.0)
            candidate_payload = build_candidate_payload(
                coherent_planned_meals=coherent_planned_meals,
                planning_engine_name="v2",
                seed_offset=seed_offset,
                planning_diagnostics=v2_result.get("diagnostics") or get_last_generation_diagnostics(),
                extra_phase_timings=attempt_phase_timings,
            )
        except Exception as exc:
            planning_attempts.append({
                "planning_engine": "v2",
                "seed_offset": seed_offset,
                "status": "planning_failed",
                "error_type": type(exc).__name__,
                "error_detail": str(exc),
                "resolution_summary": dict((get_last_generation_diagnostics() or {}).get("resolution_summary") or {}),
            })
            logger.warning(
                "Diet generation strict attempt rejected before payload validation user=%s engine=v2 seed_offset=%s error=%s",
                user.id,
                seed_offset,
                exc,
            )
            continue

        strict_payload_validation = dict(candidate_payload["strict_payload_validation"])
        daily_validation = dict(strict_payload_validation.get("daily_validation") or {})
        planning_attempts.append({
            "planning_engine": "v2",
            "seed_offset": seed_offset,
            "status": "accepted" if strict_payload_validation.get("within_tolerance") else "rejected_out_of_tolerance",
            "validation_skipped": bool(strict_payload_validation.get("validation_skipped")),
            "within_tolerance": bool(strict_payload_validation.get("within_tolerance")),
            "invalid_meal_indexes": list(strict_payload_validation.get("invalid_meal_indexes") or []),
            "daily_out_of_tolerance_fields": list(daily_validation.get("out_of_tolerance_fields") or []),
            "daily_normalized_error_score": float(daily_validation.get("normalized_error_score") or 0.0),
            "resolution_summary": dict(candidate_payload["generation_diagnostics"].get("resolution_summary") or {}),
        })
        if strict_payload_validation.get("within_tolerance"):
            accepted_candidate = candidate_payload
            break
        candidate_score = _score_generation_candidate(strict_payload_validation)
        if best_rejected_candidate is None or best_rejected_score is None or candidate_score < best_rejected_score:
            best_rejected_candidate = candidate_payload
            best_rejected_score = candidate_score
        logger.warning(
            "Diet generation strict payload rejected user=%s engine=v2 seed_offset=%s invalid_meals=%s daily_fields=%s",
            user.id,
            seed_offset,
            strict_payload_validation.get("invalid_meal_indexes") or [],
            daily_validation.get("out_of_tolerance_fields") or [],
        )

    if accepted_candidate is None:
        for seed_offset in STRICT_LEGACY_GENERATION_SEED_OFFSETS:
            attempt_daily_food_usage = create_daily_food_usage_tracker()
            legacy_fallback_meal_timings: list[dict[str, float | int | str | bool | None]] = []
            try:
                coherent_planned_meals = []
                for meal_index, meal in enumerate(meal_distribution["meals"]):
                    meal_model = DietMeal.model_validate(meal)
                    legacy_meal_started_at = time.perf_counter()
                    planned_meal = find_exact_solution_for_meal(
                        meal=meal_model,
                        meal_index=meal_index,
                        meals_count=meals_count,
                        training_focus=meals_context[meal_index]["training_focus"],
                        food_lookup=full_food_lookup,
                        preference_profile=preference_profile,
                        daily_food_usage=attempt_daily_food_usage,
                        weekly_food_usage=weekly_food_usage,
                        forced_role_codes=anclas_por_comida.get(meal_index),
                        preferred_support_candidates=soporte_por_comida.get(meal_index),
                        variety_seed=generation_variety_seed + seed_offset + meal_index,
                    )
                    coherent_meal = apply_generation_coherence(
                        meal=meal_model,
                        meal_index=meal_index,
                        meals_count=meals_count,
                        training_focus=meals_context[meal_index]["training_focus"],
                        meal_plan=planned_meal,
                        food_lookup=full_food_lookup,
                        preference_profile=preference_profile,
                        daily_diversity_context=attempt_daily_food_usage,
                        variety_seed=generation_variety_seed + seed_offset + meal_index,
                    )
                    coherent_planned_meals.append(coherent_meal)
                    track_food_usage_across_day(attempt_daily_food_usage, coherent_meal)
                    legacy_fallback_meal_timings.append({
                        "meal_index": meal_index,
                        "meal_slot": meals_context[meal_index]["meal_slot"],
                        "meal_role": meals_context[meal_index]["meal_role"],
                        "training_focus": meals_context[meal_index]["training_focus"],
                        "elapsed_seconds": time.perf_counter() - legacy_meal_started_at,
                    })
                candidate_payload = build_candidate_payload(
                    coherent_planned_meals=coherent_planned_meals,
                    planning_engine_name="legacy_fallback",
                    seed_offset=seed_offset,
                    planning_diagnostics={
                        "legacy_fallback_meal_timings": legacy_fallback_meal_timings,
                    },
                )
            except Exception as exc:
                planning_attempts.append({
                    "planning_engine": "legacy_fallback",
                    "seed_offset": seed_offset,
                    "status": "planning_failed",
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                })
                logger.warning(
                    "Diet generation strict attempt rejected before payload validation user=%s engine=legacy_fallback seed_offset=%s error=%s",
                    user.id,
                    seed_offset,
                    exc,
                )
                continue

            strict_payload_validation = dict(candidate_payload["strict_payload_validation"])
            daily_validation = dict(strict_payload_validation.get("daily_validation") or {})
            planning_attempts.append({
                "planning_engine": "legacy_fallback",
                "seed_offset": seed_offset,
                "status": "accepted" if strict_payload_validation.get("within_tolerance") else "rejected_out_of_tolerance",
                "validation_skipped": bool(strict_payload_validation.get("validation_skipped")),
                "within_tolerance": bool(strict_payload_validation.get("within_tolerance")),
                "invalid_meal_indexes": list(strict_payload_validation.get("invalid_meal_indexes") or []),
                "daily_out_of_tolerance_fields": list(daily_validation.get("out_of_tolerance_fields") or []),
                "daily_normalized_error_score": float(daily_validation.get("normalized_error_score") or 0.0),
            })
            if strict_payload_validation.get("within_tolerance"):
                accepted_candidate = candidate_payload
                break
            candidate_score = _score_generation_candidate(strict_payload_validation)
            if best_rejected_candidate is None or best_rejected_score is None or candidate_score < best_rejected_score:
                best_rejected_candidate = candidate_payload
                best_rejected_score = candidate_score
            logger.warning(
                "Diet generation strict payload rejected user=%s engine=legacy_fallback seed_offset=%s invalid_meals=%s daily_fields=%s",
                user.id,
                seed_offset,
                strict_payload_validation.get("invalid_meal_indexes") or [],
                daily_validation.get("out_of_tolerance_fields") or [],
            )

    phase_timings["planning_and_coherence"] = time.perf_counter() - phase_started_at
    if accepted_candidate is None:
        failure_diagnostics = dict((best_rejected_candidate or {}).get("generation_diagnostics") or {})
        failure_diagnostics.update({
            "planning_attempts": planning_attempts,
            "best_rejected_strict_payload_validation": dict(
                (best_rejected_candidate or {}).get("strict_payload_validation") or {}
            ),
            "service_phase_timings": dict(phase_timings),
            "planning_engine": None,
            "resolved_foods_count": 0,
        })
        set_last_generation_diagnostics(failure_diagnostics)
        raise RuntimeError("Unable to generate a diet within strict nutrition tolerances with current catalog")

    planning_engine = str(accepted_candidate["planning_engine"])
    coherent_planned_meals = list(accepted_candidate["coherent_planned_meals"])
    selected_food_codes = list(accepted_candidate["selected_food_codes"])
    lookup_metadata = dict(accepted_candidate["lookup_metadata"])
    generated_meals = list(accepted_candidate["generated_meals"])
    food_data_source = accepted_candidate["food_data_source"]
    food_data_sources = accepted_candidate["food_data_sources"]
    preferred_food_matches = int(accepted_candidate["preferred_food_matches"])
    daily_totals = dict(accepted_candidate["daily_totals"])
    if "v2_day_planning" in accepted_candidate["phase_timings"]:
        phase_timings["v2_day_planning"] = float(accepted_candidate["phase_timings"]["v2_day_planning"])
    if "v2_instantiation" in accepted_candidate["phase_timings"]:
        phase_timings["v2_instantiation"] = float(accepted_candidate["phase_timings"]["v2_instantiation"])
    phase_timings["food_resolution"] = float(accepted_candidate["phase_timings"].get("food_resolution", 0.0))
    phase_timings["payload_build"] = float(accepted_candidate["phase_timings"].get("payload_build", 0.0))
    phase_timings["total"] = time.perf_counter() - generation_started_at

    logger.info(
        "Diet generation timings user=%s meals=%s setup=%.4fs context=%.4fs anchors=%.4fs planning=%.4fs resolution=%.4fs payload=%.4fs total=%.4fs resolved_foods=%s",
        user.id,
        meals_count,
        phase_timings["setup"],
        phase_timings["meal_context"],
        phase_timings["preference_anchors"],
        phase_timings["planning_and_coherence"],
        phase_timings["food_resolution"],
        phase_timings["payload_build"],
        phase_timings["total"],
        len(selected_food_codes),
    )
    logger.info("Diet generation engine user=%s engine=%s", user.id, planning_engine)
    generation_diagnostics = dict(accepted_candidate.get("generation_diagnostics") or get_last_generation_diagnostics() or {})
    generation_diagnostics.update({
        "planning_attempts": planning_attempts,
        "strict_payload_validation": dict(accepted_candidate["strict_payload_validation"]),
        "service_phase_timings": dict(phase_timings),
        "planning_engine": planning_engine,
        "resolved_foods_count": len(selected_food_codes),
    })
    set_last_generation_diagnostics(generation_diagnostics)
    emit_runtime_audit(
        "diet_generation_service_completed",
        {
            "planning_engine": planning_engine,
            "phase_timings": phase_timings,
            "generation_diagnostics": generation_diagnostics,
            "selected_food_codes": selected_food_codes,
            "generated_meal_foods": [
                [food["name"] for food in meal["foods"]]
                for meal in generated_meals
            ],
        },
    )

    return {
        "meals_count": meal_distribution["meals_count"],
        "target_calories": meal_distribution["target_calories"],
        "protein_grams": meal_distribution["protein_grams"],
        "fat_grams": meal_distribution["fat_grams"],
        "carb_grams": meal_distribution["carb_grams"],
        "actual_calories": daily_totals["actual_calories"],
        "actual_protein_grams": daily_totals["actual_protein_grams"],
        "actual_fat_grams": daily_totals["actual_fat_grams"],
        "actual_carb_grams": daily_totals["actual_carb_grams"],
        "calorie_difference": daily_totals["calorie_difference"],
        "protein_difference": daily_totals["protein_difference"],
        "fat_difference": daily_totals["fat_difference"],
        "carb_difference": daily_totals["carb_difference"],
        "distribution_percentages": meal_distribution["distribution_percentages"],
        "training_time_of_day": meal_distribution["training_time_of_day"],
        "training_optimization_applied": meal_distribution["training_optimization_applied"],
        "food_data_source": food_data_source,
        "food_data_sources": food_data_sources,
        "food_catalog_version": lookup_metadata.get("food_catalog_version", get_food_catalog_version()),
        "food_preferences_applied": preference_profile.get("has_preferences", False),
        "applied_dietary_restrictions": preference_profile.get("dietary_restrictions", []),
        "applied_allergies": preference_profile.get("allergies", []),
        "preferred_food_matches": preferred_food_matches,
        "diversity_strategy_applied": True,
        "food_usage_summary": get_food_usage_summary_from_meals(generated_meals),
        "food_filter_warnings": preference_profile.get("warnings", []),
        "anchor_diagnostics": preference_profile.get("anchor_diagnostics", []),
        "catalog_source_strategy": lookup_metadata.get("catalog_source_strategy", CATALOG_SOURCE_STRATEGY_DEFAULT),
        "spoonacular_attempted": lookup_metadata.get("spoonacular_attempted", False),
        "spoonacular_attempts": lookup_metadata.get("spoonacular_attempts", 0),
        "spoonacular_hits": lookup_metadata.get("spoonacular_hits", 0),
        "cache_hits": lookup_metadata.get("cache_hits", 0),
        "internal_fallbacks": lookup_metadata.get("internal_fallbacks", 0),
        "resolved_foods_count": lookup_metadata.get("resolved_foods_count", len(selected_food_codes)),
        "meals": generated_meals,
    }


def generate_daily_diet(
    database,
    user: UserPublic,
    meals_count: int,
    custom_percentages: list[float] | None = None,
    training_time_of_day: TrainingTimeOfDay | None = None,
) -> dict:
    return generate_food_based_diet(
        database,
        user=user,
        meals_count=meals_count,
        custom_percentages=custom_percentages,
        training_time_of_day=training_time_of_day,
    )
