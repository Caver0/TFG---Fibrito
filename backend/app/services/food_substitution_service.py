"""Servicios de sustitucion controlada de alimentos dentro de una comida."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.schemas.diet import (
    AlimentoSustitutoCandidato,
    BuscarAlimentoSustitutoRequest,
    BuscarAlimentoSustitutoResponse,
    DietMutationResponse,
    DietMutationSummary,
    FoodReplacementOption,
    FoodReplacementOptionsResponse,
    ReplaceFoodRequest,
)
from app.schemas.user import UserPublic
from app.services.diet.candidates import (
    get_food_role_fit_score,
    get_support_food_fit_score,
    is_food_allowed_for_role_and_slot,
    is_support_food_allowed,
)
from app.services.diet.common import calculate_difference_summary
from app.services.diet.solver import (
    build_food_portion,
    calculate_meal_actuals_from_foods,
    get_food_visibility_threshold,
)
from app.services.diet_service import get_user_diet_by_id, resolve_meal_context
from app.services.food_catalog_service import (
    build_catalog_food_from_diet_food,
    find_food_by_code_or_name,
    get_internal_food_lookup,
    merge_internal_and_external_food_sources,
)
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import (
    build_user_food_preferences_profile,
    is_food_allowed_for_user,
)
from app.services.meal_regeneration_service import (
    build_diet_context_food_lookup,
    get_training_focus_for_meal,
    infer_existing_meal_plan,
    persist_updated_meal_in_diet,
    track_daily_food_usage_excluding_current_meal,
)
from app.utils.normalization import normalize_food_name

MACROS_PRINCIPALES = ("protein", "carb", "fat")
ETIQUETAS_MACRO = {
    "protein": "proteina",
    "carb": "carbohidrato",
    "fat": "grasa",
}
ETIQUETAS_MACRO_CATEGORIA = {
    "protein": "proteinas",
    "carb": "carbohidratos",
    "fat": "grasas",
}
PESOS_REAJUSTE = {
    "calories": 0.015,
    "protein_grams": 3.4,
    "fat_grams": 3.0,
    "carb_grams": 2.4,
}
UMBRALES_AJUSTE_ESTRICTO = {
    "calories": 90.0,
    "protein_grams": 8.0,
    "fat_grams": 6.0,
    "carb_grams": 12.0,
}
UMBRALES_AJUSTE_RAZONABLE = {
    "calories": 240.0,
    "protein_grams": 16.0,
    "fat_grams": 12.0,
    "carb_grams": 26.0,
}
PENALIZACION_RELATIVA_EXISTENTE = 72.0
PENALIZACION_RELATIVA_SUSTITUTO = 34.0
FUENTE_PRIORIDAD = {
    "internal_catalog": 0.0,
    "internal": 0.0,
    "local_cache": 0.35,
    "cache": 0.35,
    "spoonacular": 0.75,
}
MAX_CANDIDATOS_SUGERIDOS = 18
MAX_CANDIDATOS_BUSQUEDA = 12
ITERACIONES_REAJUSTE = 18
CATEGORIA_MACRO_PREFERIDA = {
    "proteinas": "protein",
    "carbohidratos": "carb",
    "cereales": "carb",
    "frutas": "carb",
    "grasas": "fat",
}
TOKEN_MACRO_PREFERIDO = {
    "protein": (
        "yogur", "yogurt", "skyr", "quark", "cottage", "queso batido",
        "pollo", "chicken", "pavo", "turkey", "atun", "tuna", "egg",
        "huevo", "claras", "tofu", "whey", "protein",
    ),
    "carb": (
        "banana", "platano", "manzana", "apple", "mango", "fruta", "fruit",
        "arroz", "rice", "avena", "oats", "pasta", "patata", "potato",
        "pan", "bread", "cereal",
    ),
    "fat": (
        "aceite", "oil", "olive oil", "aguacate", "avocado", "nueces",
        "nuts", "almendra", "almond", "peanut", "cacahuete", "seed",
        "chia", "lino", "mantequilla de cacahuete", "peanut butter",
    ),
}
GENERIC_SOLVER_EXACT_ERROR = "unable to fit meal exactly with current food catalog"


def _format_status_note(note: str, *, compatible: bool) -> str:
    cleaned_note = str(note or "").strip()
    prefix = "Compatible:" if compatible else "No compatible:"
    if not cleaned_note:
        return prefix[:-1]

    normalized_note = normalize_food_name(cleaned_note)
    if normalized_note.startswith(normalize_food_name(prefix)):
        return cleaned_note

    leading_note = cleaned_note[0].lower() + cleaned_note[1:] if cleaned_note else cleaned_note
    return f"{prefix} {leading_note}"


def _macro_energetico(food: dict[str, Any]) -> dict[str, float]:
    referencia = max(float(food.get("reference_amount") or 1.0), 1e-6)
    protein = float(food.get("protein_grams") or 0.0) / referencia * 4.0
    fat = float(food.get("fat_grams") or 0.0) / referencia * 9.0
    carb = float(food.get("carb_grams") or 0.0) / referencia * 4.0
    return {
        "protein": protein,
        "fat": fat,
        "carb": carb,
    }


def _macro_hint_por_categoria(food: dict[str, Any]) -> str | None:
    category = str(food.get("category") or "").strip().lower()
    return CATEGORIA_MACRO_PREFERIDA.get(category)


def _macro_hint_por_texto(food: dict[str, Any]) -> str | None:
    food_text = normalize_food_name(" ".join(
        value
        for value in (
            str(food.get("name") or ""),
            str(food.get("display_name") or ""),
            str(food.get("original_name") or ""),
            str(food.get("code") or "").replace("_", " "),
            *[str(alias) for alias in (food.get("aliases") or [])],
        )
        if value
    ))
    if not food_text:
        return None

    for macro, tokens in TOKEN_MACRO_PREFERIDO.items():
        if any(token in food_text for token in tokens):
            return macro
    return None


def _macro_fallback(food: dict[str, Any]) -> str:
    return _macro_hint_por_categoria(food) or _macro_hint_por_texto(food) or "carb"


def _ordenar_macros_por_prioridad(food: dict[str, Any]) -> tuple[list[str], dict[str, float]]:
    macro_energetico = _macro_energetico(food)
    ordered_macros = sorted(
        MACROS_PRINCIPALES,
        key=lambda macro: (
            macro_energetico[macro],
            _densidad_nutriente(food, f"{macro}_grams"),
        ),
        reverse=True,
    )
    return ordered_macros, macro_energetico


def _densidad_nutriente(food: dict[str, Any], field_name: str) -> float:
    referencia = max(float(food.get("reference_amount") or 1.0), 1e-6)
    return float(food.get(field_name) or 0.0) / referencia


def _densidad_calorica(food: dict[str, Any]) -> float:
    return _densidad_nutriente(food, "calories")


def _redondear_a_step(quantity: float, step: float) -> float:
    return round(round(quantity / step) * step, 2)


def _derivar_limites_cantidad(food: dict[str, Any], baseline_quantity: float, *, es_sustituto: bool) -> tuple[float, float, float]:
    step = max(float(food.get("step") or 1.0), 0.1)
    min_configurada = float(food.get("min_quantity") or 0.0)
    max_configurada = float(food.get("max_quantity") or 0.0)
    umbral_visibilidad = float(get_food_visibility_threshold(food) or 0.0)

    factor_minimo = 0.3 if es_sustituto else 0.42
    minimo_fallback = max(step, baseline_quantity * factor_minimo)
    min_quantity = max(umbral_visibilidad, min_configurada or minimo_fallback, step)

    max_fallback = max(min_quantity + step, baseline_quantity * 2.6, baseline_quantity + step)
    max_quantity = max(max_configurada, min_quantity) if max_configurada > 0 else max_fallback
    return min_quantity, max_quantity, step


def _clamp_quantity(food: dict[str, Any], quantity: float, *, baseline_quantity: float, es_sustituto: bool) -> float:
    min_quantity, max_quantity, step = _derivar_limites_cantidad(food, baseline_quantity, es_sustituto=es_sustituto)
    quantity = max(min_quantity, min(max_quantity, quantity))
    return _redondear_a_step(quantity, step)


def _grams_for_quantity(food: dict[str, Any], quantity: float) -> float:
    return float(build_food_portion(food, quantity)["grams"] or 0.0)


def determinar_macro_dominante(food: dict[str, Any]) -> str:
    """Clasifica el alimento por su macronutriente dominante."""
    ordered_macros, macro_energetico = _ordenar_macros_por_prioridad(food)
    functional_group = derive_functional_group(food)
    macro_fallback = _macro_fallback(food)

    if functional_group == "protein":
        return "protein"
    if functional_group == "fat":
        return "fat"
    if functional_group in {"carb", "fruit"}:
        return "carb"

    if functional_group == "dairy":
        if macro_energetico["protein"] >= max(macro_energetico["fat"], macro_energetico["carb"]) * 0.8:
            return "protein"
        if macro_energetico["fat"] >= macro_energetico["carb"]:
            return "fat"
        return "carb"

    if max(macro_energetico.values()) <= 1e-6:
        return macro_fallback

    primary_macro = ordered_macros[0]
    secondary_macro = ordered_macros[1]
    primary_energy = macro_energetico[primary_macro]
    secondary_energy = macro_energetico[secondary_macro]
    if primary_energy >= (secondary_energy * 1.08) or (primary_energy - secondary_energy) >= 4.0:
        return primary_macro
    if macro_fallback in ordered_macros[:2]:
        return macro_fallback
    return primary_macro


def calcular_cantidad_equivalente(
    original_food: dict[str, Any],
    original_qty: float,
    replacement_food: dict[str, Any],
    *,
    macro_principal: str | None = None,
) -> float:
    """Devuelve una cantidad inicial equivalente del sustituto."""
    macro = macro_principal or determinar_macro_dominante(original_food)
    densidad_macro_original = _densidad_nutriente(original_food, f"{macro}_grams")
    densidad_macro_sustituto = _densidad_nutriente(replacement_food, f"{macro}_grams")
    densidad_calorias_original = _densidad_calorica(original_food)
    densidad_calorias_sustituto = _densidad_calorica(replacement_food)

    cantidad_macro = None
    if densidad_macro_original > 0 and densidad_macro_sustituto > 0:
        macro_objetivo = densidad_macro_original * original_qty
        cantidad_macro = macro_objetivo / densidad_macro_sustituto

    cantidad_calorias = None
    if densidad_calorias_original > 0 and densidad_calorias_sustituto > 0:
        calorias_objetivo = densidad_calorias_original * original_qty
        cantidad_calorias = calorias_objetivo / densidad_calorias_sustituto

    if cantidad_macro is not None and cantidad_calorias is not None:
        cantidad_equivalente = (cantidad_macro * 0.7) + (cantidad_calorias * 0.3)
    elif cantidad_macro is not None:
        cantidad_equivalente = cantidad_macro
    elif cantidad_calorias is not None:
        cantidad_equivalente = cantidad_calorias
    else:
        cantidad_equivalente = float(
            replacement_food.get("default_quantity")
            or replacement_food.get("reference_amount")
            or 100.0
        )

    return _clamp_quantity(
        replacement_food,
        cantidad_equivalente,
        baseline_quantity=max(cantidad_equivalente, 1.0),
        es_sustituto=True,
    )


def _find_current_food_in_meal(meal, *, current_food_name: str, current_food_code: str | None = None):
    normalized_target_name = normalize_food_name(current_food_name)

    for food in meal.foods:
        if current_food_code and str(food.food_code or "").strip() == current_food_code:
            return food
        if normalize_food_name(food.name) == normalized_target_name:
            return food

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No se encontro el alimento '{current_food_name}' en la comida seleccionada.",
    )


def _build_current_meal_food_lookup(base_lookup: dict[str, dict[str, Any]], meal) -> dict[str, dict[str, Any]]:
    meal_lookup = dict(base_lookup)
    for food in meal.foods:
        food_code = str(food.food_code or "").strip()
        if not food_code:
            continue
        meal_lookup[food_code] = build_catalog_food_from_diet_food(food.model_dump())
    return meal_lookup


def _derive_replacement_slot(current_food_code: str, inferred_plan: dict[str, Any], current_food_entry: dict[str, Any]) -> dict[str, str]:
    for role, food_code in inferred_plan.get("selected_role_codes", {}).items():
        if food_code == current_food_code:
            return {"kind": "role", "role": role}

    for support_food in inferred_plan.get("support_food_specs", []):
        if support_food.get("food_code") == current_food_code:
            return {"kind": "support", "role": str(support_food.get("role") or "support")}

    functional_group = derive_functional_group(current_food_entry)
    if functional_group in {"fruit", "vegetable", "dairy"}:
        return {"kind": "support", "role": functional_group}
    return {"kind": "role", "role": determinar_macro_dominante(current_food_entry)}


def _build_food_replacement_context(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
    current_food_name: str,
    current_food_code: str | None = None,
) -> dict[str, Any]:
    diet = get_user_diet_by_id(database, user.id, diet_id)
    meal_index = meal_number - 1
    if meal_index < 0 or meal_index >= len(diet.meals):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found in the selected diet",
        )

    meal = diet.meals[meal_index]
    current_food = _find_current_food_in_meal(
        meal,
        current_food_name=current_food_name,
        current_food_code=current_food_code,
    )
    context_food_lookup = build_diet_context_food_lookup(database, diet)
    meal_food_lookup = _build_current_meal_food_lookup(context_food_lookup, meal)
    current_food_entry = meal_food_lookup.get(str(current_food.food_code or "").strip()) or build_catalog_food_from_diet_food(
        current_food.model_dump()
    )
    preference_profile = build_user_food_preferences_profile(user)
    training_focus = get_training_focus_for_meal(diet, meal_index)
    inferred_plan = infer_existing_meal_plan(
        meal,
        meal_index=meal_index,
        meals_count=diet.meals_count,
        training_focus=training_focus,
        food_lookup=meal_food_lookup,
    )
    meal_slot, meal_role = resolve_meal_context(
        meal,
        meal_index=meal_index,
        meals_count=diet.meals_count,
        training_focus=training_focus,
    )
    slot = _derive_replacement_slot(str(current_food.food_code or "").strip(), inferred_plan, current_food_entry)
    daily_food_usage = track_daily_food_usage_excluding_current_meal(
        diet,
        meal_index_to_exclude=meal_index,
        food_lookup=context_food_lookup,
    )

    return {
        "diet": diet,
        "meal": meal,
        "meal_index": meal_index,
        "current_food": current_food,
        "current_food_entry": current_food_entry,
        "context_food_lookup": context_food_lookup,
        "meal_food_lookup": meal_food_lookup,
        "preference_profile": preference_profile,
        "training_focus": training_focus,
        "meal_slot": meal_slot,
        "meal_role": meal_role,
        "inferred_plan": inferred_plan,
        "slot": slot,
        "daily_food_usage": daily_food_usage,
        "current_macro_dominante": determinar_macro_dominante(current_food_entry),
        "meal_food_codes": {
            str(food.food_code or "").strip()
            for food in meal.foods
            if str(food.food_code or "").strip()
        },
    }


def _food_can_fit_in_meal_context(
    food: dict[str, Any],
    *,
    macro_dominante: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> bool:
    del training_focus
    if macro_dominante in MACROS_PRINCIPALES and is_food_allowed_for_role_and_slot(
        food,
        role=macro_dominante,
        meal_slot=meal_slot,
    ):
        return True

    functional_group = derive_functional_group(food)
    if functional_group == "fruit" and macro_dominante == "carb":
        return is_support_food_allowed(food, support_role="fruit", meal_slot=meal_slot, meal_role=meal_role)
    if functional_group == "vegetable" and macro_dominante == "carb":
        return is_support_food_allowed(food, support_role="vegetable", meal_slot=meal_slot, meal_role=meal_role)
    if functional_group == "dairy" and macro_dominante == "protein":
        return is_support_food_allowed(food, support_role="dairy", meal_slot=meal_slot, meal_role=meal_role)
    return False


def _get_meal_fit_score(
    food: dict[str, Any],
    *,
    macro_dominante: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> float:
    scores: list[float] = []

    if macro_dominante in MACROS_PRINCIPALES and is_food_allowed_for_role_and_slot(
        food,
        role=macro_dominante,
        meal_slot=meal_slot,
    ):
        scores.append(
            get_food_role_fit_score(
                food,
                role=macro_dominante,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            )
        )

    functional_group = derive_functional_group(food)
    if functional_group == "fruit" and macro_dominante == "carb" and is_support_food_allowed(
        food,
        support_role="fruit",
        meal_slot=meal_slot,
        meal_role=meal_role,
    ):
        scores.append(
            get_support_food_fit_score(
                food,
                support_role="fruit",
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            )
        )
    elif functional_group == "vegetable" and macro_dominante == "carb" and is_support_food_allowed(
        food,
        support_role="vegetable",
        meal_slot=meal_slot,
        meal_role=meal_role,
    ):
        scores.append(
            get_support_food_fit_score(
                food,
                support_role="vegetable",
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            )
        )
    elif functional_group == "dairy" and macro_dominante == "protein" and is_support_food_allowed(
        food,
        support_role="dairy",
        meal_slot=meal_slot,
        meal_role=meal_role,
    ):
        scores.append(
            get_support_food_fit_score(
                food,
                support_role="dairy",
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            )
        )

    return max(scores, default=-999.0)


def _validar_candidato_base(
    candidate_food: dict[str, Any],
    current_food_entry: dict[str, Any],
    *,
    preference_profile: dict[str, Any],
    meal_food_codes: set[str] | None = None,
) -> tuple[bool, str]:
    macro_original = determinar_macro_dominante(current_food_entry)
    macro_candidato = determinar_macro_dominante(candidate_food)

    candidate_code = str(candidate_food.get("code") or "").strip()
    current_code = str(current_food_entry.get("code") or "").strip()

    if candidate_code and current_code and candidate_code == current_code:
        return False, _format_status_note(
            "Debes elegir un alimento distinto del actual.",
            compatible=False,
        )

    if meal_food_codes and candidate_code and candidate_code in meal_food_codes and candidate_code != current_code:
        return False, _format_status_note(
            f"'{candidate_food['name']}' ya esta presente en esta comida.",
            compatible=False,
        )

    if macro_candidato != macro_original:
        return (
            False,
            _format_status_note(
                f"'{candidate_food['name']}' pertenece a "
                f"{ETIQUETAS_MACRO_CATEGORIA.get(macro_candidato, macro_candidato)} y el alimento original es "
                f"{ETIQUETAS_MACRO.get(macro_original, macro_original)}.",
                compatible=False,
            ),
        )

    permitido, razones = is_food_allowed_for_user(candidate_food, preference_profile)
    if not permitido:
        return (
            False,
            _format_status_note(
                f"'{candidate_food['name']}' no esta permitido por las restricciones activas: {', '.join(razones)}.",
                compatible=False,
            ),
        )

    return True, _format_status_note(
        "Mismo macro dominante y restricciones activas respetadas.",
        compatible=True,
    )


def _validar_candidato_encaje_comida(
    candidate_food: dict[str, Any],
    current_food_entry: dict[str, Any],
    *,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> tuple[bool, str]:
    macro_original = determinar_macro_dominante(current_food_entry)
    if not _food_can_fit_in_meal_context(
        candidate_food,
        macro_dominante=macro_original,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
    ):
        return False, _format_status_note(
            f"'{candidate_food['name']}' no encaja de forma razonable en esta comida.",
            compatible=False,
        )

    return True, _format_status_note(
        "Mismo macro dominante y buen encaje en esta comida.",
        compatible=True,
    )


def validar_alimento_para_sustitucion(
    candidate_food: dict[str, Any],
    current_food_entry: dict[str, Any],
    *,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    preference_profile: dict[str, Any],
    meal_food_codes: set[str] | None = None,
) -> tuple[bool, str]:
    base_valido, base_nota = _validar_candidato_base(
        candidate_food,
        current_food_entry,
        preference_profile=preference_profile,
        meal_food_codes=meal_food_codes,
    )
    if not base_valido:
        return False, base_nota

    return _validar_candidato_encaje_comida(
        candidate_food,
        current_food_entry,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
    )


def _score_equivalent_candidate(
    candidate_food: dict[str, Any],
    *,
    current_food_entry: dict[str, Any],
    current_macro: str,
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
) -> float:
    fit_score = _get_meal_fit_score(
        candidate_food,
        macro_dominante=current_macro,
        meal_slot=meal_slot,
        meal_role=meal_role,
        training_focus=training_focus,
    )
    current_macro_density = _densidad_nutriente(current_food_entry, f"{current_macro}_grams")
    candidate_macro_density = _densidad_nutriente(candidate_food, f"{current_macro}_grams")
    calorie_density_gap = abs(_densidad_calorica(candidate_food) - _densidad_calorica(current_food_entry))
    macro_density_gap = abs(candidate_macro_density - current_macro_density)
    protein_gap = abs(_densidad_nutriente(candidate_food, "protein_grams") - _densidad_nutriente(current_food_entry, "protein_grams"))
    fat_gap = abs(_densidad_nutriente(candidate_food, "fat_grams") - _densidad_nutriente(current_food_entry, "fat_grams"))
    carb_gap = abs(_densidad_nutriente(candidate_food, "carb_grams") - _densidad_nutriente(current_food_entry, "carb_grams"))
    same_group_bonus = -0.75 if derive_functional_group(candidate_food) == derive_functional_group(current_food_entry) else 0.0
    source_penalty = FUENTE_PRIORIDAD.get(str(candidate_food.get("source") or "internal_catalog"), 0.9)

    return (
        macro_density_gap * 42.0
        + calorie_density_gap * 8.0
        + protein_gap * 18.0
        + fat_gap * 20.0
        + carb_gap * 16.0
        + source_penalty
        + same_group_bonus
        - (fit_score * 1.8)
    )


def find_equivalent_food_candidates(
    *,
    current_food_entry: dict[str, Any],
    meal_slot: str,
    meal_role: str,
    training_focus: bool,
    preference_profile: dict[str, Any],
    meal_food_codes: set[str],
    food_lookup: dict[str, dict[str, Any]],
    candidate_foods: list[dict[str, Any]] | None = None,
    limit: int = 8,
    allow_relaxed_meal_fit: bool = False,
) -> list[dict[str, Any]]:
    current_macro = determinar_macro_dominante(current_food_entry)
    pool = candidate_foods if candidate_foods is not None else list(food_lookup.values())
    ranked_candidates: list[tuple[float, dict[str, Any]]] = []
    seen_codes: set[str] = set()

    for candidate_food in pool:
        candidate_code = str(candidate_food.get("code") or "").strip()
        if not candidate_code or candidate_code in seen_codes:
            continue

        if allow_relaxed_meal_fit:
            valid, _ = _validar_candidato_base(
                candidate_food,
                current_food_entry,
                preference_profile=preference_profile,
                meal_food_codes=meal_food_codes,
            )
        else:
            valid, _ = validar_alimento_para_sustitucion(
                candidate_food,
                current_food_entry,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
                preference_profile=preference_profile,
                meal_food_codes=meal_food_codes,
            )
        if not valid:
            continue

        ranked_candidates.append((
            _score_equivalent_candidate(
                candidate_food,
                current_food_entry=current_food_entry,
                current_macro=current_macro,
                meal_slot=meal_slot,
                meal_role=meal_role,
                training_focus=training_focus,
            ),
            candidate_food,
        ))
        seen_codes.add(candidate_code)

    ranked_candidates.sort(key=lambda item: (item[0], item[1]["name"].lower()))
    return [food for _, food in ranked_candidates[:limit]]


def _find_replacement_candidates_with_fallback(
    *,
    context: dict[str, Any],
    food_lookup: dict[str, dict[str, Any]],
    candidate_foods: list[dict[str, Any]] | None = None,
    limit: int,
) -> list[dict[str, Any]]:
    strict_candidates = find_equivalent_food_candidates(
        current_food_entry=context["current_food_entry"],
        meal_slot=context["meal_slot"],
        meal_role=context["meal_role"],
        training_focus=context["training_focus"],
        preference_profile=context["preference_profile"],
        meal_food_codes=context["meal_food_codes"],
        food_lookup=food_lookup,
        candidate_foods=candidate_foods,
        limit=limit,
    )
    if strict_candidates:
        return strict_candidates

    return find_equivalent_food_candidates(
        current_food_entry=context["current_food_entry"],
        meal_slot=context["meal_slot"],
        meal_role=context["meal_role"],
        training_focus=context["training_focus"],
        preference_profile=context["preference_profile"],
        meal_food_codes=context["meal_food_codes"],
        food_lookup=food_lookup,
        candidate_foods=candidate_foods,
        limit=limit,
        allow_relaxed_meal_fit=True,
    )


def _resolve_requested_replacement_candidates(
    database,
    *,
    food_name: str | None,
    food_code: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    def add_candidate(food: dict[str, Any] | None) -> None:
        if not food:
            return
        code = str(food.get("code") or "").strip()
        if not code or code in seen_codes:
            return
        candidates.append(food)
        seen_codes.add(code)

    add_candidate(
        find_food_by_code_or_name(
            database,
            food_code=food_code,
            food_name=food_name,
            include_external=True,
        )
    )

    if food_name:
        for food in merge_internal_and_external_food_sources(
            database,
            food_name,
            limit=max(limit, 6),
            include_external=True,
        ):
            add_candidate(food)

    return candidates[:limit]


def _build_search_candidate(
    candidate_food: dict[str, Any],
    *,
    context: dict[str, Any],
) -> AlimentoSustitutoCandidato:
    valid, validation_note = validar_alimento_para_sustitucion(
        candidate_food,
        context["current_food_entry"],
        meal_slot=context["meal_slot"],
        meal_role=context["meal_role"],
        training_focus=context["training_focus"],
        preference_profile=context["preference_profile"],
        meal_food_codes=context["meal_food_codes"],
    )
    equivalent_quantity = calcular_cantidad_equivalente(
        context["current_food_entry"],
        float(context["current_food"].quantity),
        candidate_food,
        macro_principal=context["current_macro_dominante"],
    )
    return AlimentoSustitutoCandidato(
        food_code=str(candidate_food.get("code") or ""),
        name=str(candidate_food.get("name") or ""),
        category=str(candidate_food.get("category") or "otros"),
        macro_dominante=determinar_macro_dominante(candidate_food),
        valid=valid,
        validation_note=validation_note,
        calories=float(candidate_food.get("calories") or 0.0),
        protein_grams=float(candidate_food.get("protein_grams") or 0.0),
        fat_grams=float(candidate_food.get("fat_grams") or 0.0),
        carb_grams=float(candidate_food.get("carb_grams") or 0.0),
        source=str(candidate_food.get("source") or "internal_catalog"),
        equivalent_grams=_grams_for_quantity(candidate_food, equivalent_quantity),
    )


def _sanitize_substitution_exception(
    exc: HTTPException,
    *,
    candidate_name: str | None = None,
) -> HTTPException:
    detail = str(exc.detail or "").strip()
    normalized_detail = normalize_food_name(detail)
    if GENERIC_SOLVER_EXACT_ERROR in normalized_detail:
        candidate_label = f"'{candidate_name}' " if candidate_name else ""
        detail = (
            f"{candidate_label}tiene el macro correcto, pero no se puede reajustar razonablemente "
            "la comida actual con el catalogo disponible."
        ).strip()
    elif normalized_detail == normalize_food_name("No se pudo completar la sustitucion con una solucion valida.") and candidate_name:
        detail = (
            f"'{candidate_name}' tiene el macro correcto, pero no se ha podido construir una "
            "previsualizacion razonable para esta comida."
        )
    if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        detail = _format_status_note(detail, compatible=False)

    return HTTPException(status_code=exc.status_code, detail=detail)


def _resolve_valid_requested_candidates(
    *,
    context: dict[str, Any],
    candidate_foods: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    valid_candidates: list[dict[str, Any]] = []
    first_error: str | None = None

    for candidate_food in candidate_foods:
        base_valid, base_note = _validar_candidato_base(
            candidate_food,
            context["current_food_entry"],
            preference_profile=context["preference_profile"],
            meal_food_codes=context["meal_food_codes"],
        )
        if not base_valid:
            first_error = first_error or base_note
            continue

        meal_valid, meal_note = _validar_candidato_encaje_comida(
            candidate_food,
            context["current_food_entry"],
            meal_slot=context["meal_slot"],
            meal_role=context["meal_role"],
            training_focus=context["training_focus"],
        )
        if meal_valid:
            valid_candidates.append(candidate_food)
            continue

        first_error = first_error or meal_note

    return valid_candidates, first_error


def search_replacement_food(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
    payload: BuscarAlimentoSustitutoRequest,
) -> BuscarAlimentoSustitutoResponse:
    context = _build_food_replacement_context(
        database,
        user=user,
        diet_id=diet_id,
        meal_number=meal_number,
        current_food_name=payload.current_food_name,
        current_food_code=payload.current_food_code,
    )
    resolved_candidates = _resolve_requested_replacement_candidates(
        database,
        food_name=payload.query,
        food_code=None,
        limit=MAX_CANDIDATOS_BUSQUEDA,
    )
    if not resolved_candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se pudo localizar un alimento para '{payload.query}'.",
        )

    ranked_candidates = sorted(
        (_build_search_candidate(candidate_food, context=context) for candidate_food in resolved_candidates),
        key=lambda candidate: (
            not candidate.valid,
            FUENTE_PRIORIDAD.get(candidate.source, 0.9),
            candidate.name.lower(),
        ),
    )
    return BuscarAlimentoSustitutoResponse(
        current_food_name=context["current_food"].name,
        current_macro_dominante=context["current_macro_dominante"],
        candidates=ranked_candidates,
    )


def _build_reajuste_specs(
    *,
    meal,
    current_food,
    current_food_entry: dict[str, Any],
    replacement_food: dict[str, Any],
    meal_food_lookup: dict[str, dict[str, Any]],
    macro_principal: str,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    current_code = str(current_food.food_code or "").strip()

    for meal_food in meal.foods:
        meal_food_code = str(meal_food.food_code or "").strip()
        is_target = meal_food_code == current_code or (
            not meal_food_code and normalize_food_name(meal_food.name) == normalize_food_name(current_food.name)
        )

        if is_target:
            food_entry = replacement_food
            baseline_quantity = calcular_cantidad_equivalente(
                current_food_entry,
                float(current_food.quantity),
                replacement_food,
                macro_principal=macro_principal,
            )
            preservation_weight = PENALIZACION_RELATIVA_SUSTITUTO
        else:
            food_entry = meal_food_lookup.get(meal_food_code) or build_catalog_food_from_diet_food(meal_food.model_dump())
            baseline_quantity = float(meal_food.quantity)
            preservation_weight = PENALIZACION_RELATIVA_EXISTENTE

        specs.append({
            "food": food_entry,
            "food_code": str(food_entry.get("code") or meal_food_code),
            "name": str(food_entry.get("name") or meal_food.name),
            "baseline_quantity": float(baseline_quantity),
            "current_quantity": float(meal_food.quantity),
            "is_replacement": is_target,
            "preservation_weight": preservation_weight,
        })

    return specs


def _densidad_reajuste(food: dict[str, Any]) -> dict[str, float]:
    return {
        "calories": _densidad_calorica(food),
        "protein_grams": _densidad_nutriente(food, "protein_grams"),
        "fat_grams": _densidad_nutriente(food, "fat_grams"),
        "carb_grams": _densidad_nutriente(food, "carb_grams"),
    }


def _totales_desde_especificaciones(specs: list[dict[str, Any]], quantities: list[float]) -> dict[str, float]:
    totals = {
        "calories": 0.0,
        "protein_grams": 0.0,
        "fat_grams": 0.0,
        "carb_grams": 0.0,
    }
    for spec, quantity in zip(specs, quantities, strict=True):
        densidad = _densidad_reajuste(spec["food"])
        for field_name in totals:
            totals[field_name] += densidad[field_name] * quantity
    return totals


def _reajustar_cantidades(specs: list[dict[str, Any]], meal) -> list[float]:
    quantities = [
        _clamp_quantity(
            spec["food"],
            spec["baseline_quantity"],
            baseline_quantity=max(spec["baseline_quantity"], 1.0),
            es_sustituto=bool(spec["is_replacement"]),
        )
        for spec in specs
    ]
    targets = {
        "calories": float(meal.target_calories),
        "protein_grams": float(meal.target_protein_grams),
        "fat_grams": float(meal.target_fat_grams),
        "carb_grams": float(meal.target_carb_grams),
    }

    for _ in range(ITERACIONES_REAJUSTE):
        totals = _totales_desde_especificaciones(specs, quantities)
        for index, spec in enumerate(specs):
            food = spec["food"]
            densidad = _densidad_reajuste(food)
            baseline_quantity = max(float(spec["baseline_quantity"]), 1.0)
            penalizacion = float(spec["preservation_weight"]) / (baseline_quantity ** 2)

            numerator = penalizacion * spec["baseline_quantity"]
            denominator = penalizacion

            for field_name, weight in PESOS_REAJUSTE.items():
                densidad_i = densidad[field_name]
                total_sin_i = totals[field_name] - (densidad_i * quantities[index])
                numerator += weight * densidad_i * (targets[field_name] - total_sin_i)
                denominator += weight * (densidad_i ** 2)

            proposed_quantity = spec["baseline_quantity"] if denominator <= 1e-9 else numerator / denominator
            quantities[index] = _clamp_quantity(
                food,
                proposed_quantity,
                baseline_quantity=baseline_quantity,
                es_sustituto=bool(spec["is_replacement"]),
            )
            totals = _totales_desde_especificaciones(specs, quantities)

    return quantities


def _diferencias_comida(actuals: dict[str, float], meal) -> dict[str, float]:
    return calculate_difference_summary(
        target_calories=float(meal.target_calories),
        target_protein_grams=float(meal.target_protein_grams),
        target_fat_grams=float(meal.target_fat_grams),
        target_carb_grams=float(meal.target_carb_grams),
        actual_calories=float(actuals["actual_calories"]),
        actual_protein_grams=float(actuals["actual_protein_grams"]),
        actual_fat_grams=float(actuals["actual_fat_grams"]),
        actual_carb_grams=float(actuals["actual_carb_grams"]),
    )


def _cumple_umbral(differences: dict[str, float], thresholds: dict[str, float]) -> bool:
    return (
        abs(float(differences["calorie_difference"])) <= thresholds["calories"]
        and abs(float(differences["protein_difference"])) <= thresholds["protein_grams"]
        and abs(float(differences["fat_difference"])) <= thresholds["fat_grams"]
        and abs(float(differences["carb_difference"])) <= thresholds["carb_grams"]
    )


def reajustar_comida_manteniendo_alimentos(
    *,
    meal,
    current_food,
    current_food_entry: dict[str, Any],
    replacement_food: dict[str, Any],
    meal_food_lookup: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    macro_principal = determinar_macro_dominante(current_food_entry)
    specs = _build_reajuste_specs(
        meal=meal,
        current_food=current_food,
        current_food_entry=current_food_entry,
        replacement_food=replacement_food,
        meal_food_lookup=meal_food_lookup,
        macro_principal=macro_principal,
    )
    quantities = _reajustar_cantidades(specs, meal)
    foods = [
        build_food_portion(spec["food"], quantity)
        for spec, quantity in zip(specs, quantities, strict=True)
    ]
    actuals = calculate_meal_actuals_from_foods(foods)
    differences = _diferencias_comida(actuals, meal)

    if not _cumple_umbral(differences, UMBRALES_AJUSTE_RAZONABLE):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No se pudo integrar '{replacement_food['name']}' sin desajustar demasiado la comida actual."
            ),
        )

    strategy = "strict" if _cumple_umbral(differences, UMBRALES_AJUSTE_ESTRICTO) else "relaxed"
    return {
        "foods": foods,
        "actual_calories": actuals["actual_calories"],
        "actual_protein_grams": actuals["actual_protein_grams"],
        "actual_fat_grams": actuals["actual_fat_grams"],
        "actual_carb_grams": actuals["actual_carb_grams"],
        **differences,
    }, strategy


def _build_replacement_option(
    *,
    current_food,
    current_food_entry: dict[str, Any],
    replacement_food: dict[str, Any],
    meal_solution: dict[str, Any],
    strategy: str,
) -> FoodReplacementOption:
    replacement_portion = next(
        food
        for food in meal_solution["foods"]
        if str(food.get("food_code") or "").strip() == str(replacement_food.get("code") or "").strip()
    )
    equivalent_quantity = calcular_cantidad_equivalente(
        current_food_entry,
        float(current_food.quantity),
        replacement_food,
        macro_principal=determinar_macro_dominante(current_food_entry),
    )
    equivalent_grams = _grams_for_quantity(replacement_food, equivalent_quantity)

    note = (
        "Se mantuvieron los mismos alimentos del resto de la comida y solo se reajustaron cantidades."
        if strategy == "strict"
        else "La comida se mantuvo con los mismos alimentos, pero fue necesario un reajuste flexible de cantidades."
    )

    return FoodReplacementOption(
        food_code=str(replacement_food.get("code") or ""),
        name=str(replacement_food.get("name") or ""),
        category=str(replacement_food.get("category") or "otros"),
        functional_group=derive_functional_group(replacement_food),
        source=str(replacement_food.get("source") or "internal_catalog"),
        recommended_quantity=float(replacement_portion["quantity"]),
        recommended_unit=str(replacement_portion["unit"]),
        recommended_grams=float(replacement_portion["grams"]) if replacement_portion.get("grams") is not None else None,
        calories=float(replacement_portion["calories"]),
        protein_grams=float(replacement_portion["protein_grams"]),
        fat_grams=float(replacement_portion["fat_grams"]),
        carb_grams=float(replacement_portion["carb_grams"]),
        calorie_delta_vs_current=float(replacement_portion["calories"]) - float(current_food.calories),
        protein_delta_vs_current=float(replacement_portion["protein_grams"]) - float(current_food.protein_grams),
        fat_delta_vs_current=float(replacement_portion["fat_grams"]) - float(current_food.fat_grams),
        carb_delta_vs_current=float(replacement_portion["carb_grams"]) - float(current_food.carb_grams),
        meal_calorie_difference=float(meal_solution["calorie_difference"]),
        meal_protein_difference=float(meal_solution["protein_difference"]),
        meal_fat_difference=float(meal_solution["fat_difference"]),
        meal_carb_difference=float(meal_solution["carb_difference"]),
        strategy=strategy,
        note=note,
        macro_dominante=determinar_macro_dominante(replacement_food),
        equivalent_grams=equivalent_grams,
    )


def _score_replacement_option(option: FoodReplacementOption, candidate_rank_score: float) -> float:
    strategy_penalty = 6.0 if option.strategy == "relaxed" else 0.0
    return (
        candidate_rank_score
        + strategy_penalty
        + abs(option.meal_calorie_difference) * 0.06
        + abs(option.meal_protein_difference) * 1.3
        + abs(option.meal_fat_difference) * 1.2
        + abs(option.meal_carb_difference) * 1.0
    )


def _evaluate_candidate_for_context(
    candidate_food: dict[str, Any],
    *,
    context: dict[str, Any],
) -> tuple[float, FoodReplacementOption]:
    meal_food_lookup = {
        **context["meal_food_lookup"],
        str(candidate_food.get("code") or ""): candidate_food,
    }
    meal_solution, strategy = reajustar_comida_manteniendo_alimentos(
        meal=context["meal"],
        current_food=context["current_food"],
        current_food_entry=context["current_food_entry"],
        replacement_food=candidate_food,
        meal_food_lookup=meal_food_lookup,
    )
    candidate_rank_score = _score_equivalent_candidate(
        candidate_food,
        current_food_entry=context["current_food_entry"],
        current_macro=context["current_macro_dominante"],
        meal_slot=context["meal_slot"],
        meal_role=context["meal_role"],
        training_focus=context["training_focus"],
    )
    option = _build_replacement_option(
        current_food=context["current_food"],
        current_food_entry=context["current_food_entry"],
        replacement_food=candidate_food,
        meal_solution=meal_solution,
        strategy=strategy,
    )
    return _score_replacement_option(option, candidate_rank_score), option


def list_food_replacement_options(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
    limit: int = 6,
) -> FoodReplacementOptionsResponse:
    context = _build_food_replacement_context(
        database,
        user=user,
        diet_id=diet_id,
        meal_number=meal_number,
        current_food_name=payload.current_food_name,
        current_food_code=payload.current_food_code,
    )

    if payload.replacement_food_name or payload.replacement_food_code:
        requested_candidates = _resolve_requested_replacement_candidates(
            database,
            food_name=payload.replacement_food_name,
            food_code=payload.replacement_food_code,
            limit=MAX_CANDIDATOS_BUSQUEDA,
        )
        if not requested_candidates:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se pudo localizar el alimento '{payload.replacement_food_name or payload.replacement_food_code}'.",
            )
        candidate_foods, validation_error = _resolve_valid_requested_candidates(
            context=context,
            candidate_foods=requested_candidates,
        )
        if not candidate_foods:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=validation_error or "El alimento buscado no es compatible con esta comida.",
            )
    else:
        candidate_foods = _find_replacement_candidates_with_fallback(
            context=context,
            food_lookup=context["context_food_lookup"],
            limit=min(MAX_CANDIDATOS_SUGERIDOS, limit * 3),
        )

    if not candidate_foods:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No se encontraron sustitutos compatibles para '{context['current_food'].name}' "
                f"dentro del macro dominante {ETIQUETAS_MACRO[context['current_macro_dominante']]}."
            ),
        )

    evaluated_options: list[tuple[float, FoodReplacementOption]] = []
    last_error: Exception | None = None
    for candidate_food in candidate_foods:
        try:
            evaluated_options.append(_evaluate_candidate_for_context(candidate_food, context=context))
        except HTTPException as exc:
            last_error = _sanitize_substitution_exception(
                exc,
                candidate_name=str(candidate_food.get("name") or ""),
            )

    if not evaluated_options:
        if last_error is not None:
            raise last_error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo calcular una sustitucion valida con los candidatos disponibles.",
        )

    evaluated_options.sort(key=lambda item: (item[0], item[1].name.lower()))
    options = [option for _, option in evaluated_options[:limit]]
    return FoodReplacementOptionsResponse(
        meal_number=meal_number,
        current_food_name=context["current_food"].name,
        current_food_code=context["current_food"].food_code,
        current_food_quantity=float(context["current_food"].quantity),
        current_food_unit=context["current_food"].unit,
        current_food_grams=float(context["current_food"].grams) if context["current_food"].grams is not None else None,
        current_macro_dominante=context["current_macro_dominante"],
        options=options,
    )


def _build_updated_meal_payload(meal, meal_solution: dict[str, Any]) -> dict[str, Any]:
    return {
        "meal_number": meal.meal_number,
        "meal_slot": meal.meal_slot,
        "meal_role": meal.meal_role,
        "meal_label": meal.meal_label,
        "distribution_percentage": meal.distribution_percentage,
        "target_calories": meal.target_calories,
        "target_protein_grams": meal.target_protein_grams,
        "target_fat_grams": meal.target_fat_grams,
        "target_carb_grams": meal.target_carb_grams,
        "actual_calories": meal_solution["actual_calories"],
        "actual_protein_grams": meal_solution["actual_protein_grams"],
        "actual_fat_grams": meal_solution["actual_fat_grams"],
        "actual_carb_grams": meal_solution["actual_carb_grams"],
        "calorie_difference": meal_solution["calorie_difference"],
        "protein_difference": meal_solution["protein_difference"],
        "fat_difference": meal_solution["fat_difference"],
        "carb_difference": meal_solution["carb_difference"],
        "foods": meal_solution["foods"],
    }


def replace_food_in_meal(
    database,
    *,
    user: UserPublic,
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
) -> DietMutationResponse:
    context = _build_food_replacement_context(
        database,
        user=user,
        diet_id=diet_id,
        meal_number=meal_number,
        current_food_name=payload.current_food_name,
        current_food_code=payload.current_food_code,
    )

    if payload.replacement_food_name or payload.replacement_food_code:
        requested_candidates = _resolve_requested_replacement_candidates(
            database,
            food_name=payload.replacement_food_name,
            food_code=payload.replacement_food_code,
            limit=MAX_CANDIDATOS_BUSQUEDA,
        )
        if not requested_candidates:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se pudo localizar el alimento '{payload.replacement_food_name or payload.replacement_food_code}'.",
            )
        candidate_foods, validation_error = _resolve_valid_requested_candidates(
            context=context,
            candidate_foods=requested_candidates,
        )
        if not candidate_foods:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=validation_error or "El alimento buscado no es compatible con esta comida.",
            )
    else:
        candidate_foods = _find_replacement_candidates_with_fallback(
            context=context,
            food_lookup=context["context_food_lookup"],
            limit=MAX_CANDIDATOS_SUGERIDOS,
        )

    if not candidate_foods:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No hay sustitutos validos para este alimento en la comida actual.",
        )

    validated_candidates = candidate_foods if payload.replacement_food_name or payload.replacement_food_code else _find_replacement_candidates_with_fallback(
        context=context,
        food_lookup=context["meal_food_lookup"],
        candidate_foods=candidate_foods,
        limit=MAX_CANDIDATOS_BUSQUEDA,
    )
    if not validated_candidates:
        macro_objetivo = ETIQUETAS_MACRO[context["current_macro_dominante"]]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El alimento buscado no cumple el mismo macro dominante ({macro_objetivo}) o no encaja en esta comida.",
        )

    best_option_score: float | None = None
    best_option: FoodReplacementOption | None = None
    best_candidate: dict[str, Any] | None = None
    best_meal_solution: dict[str, Any] | None = None
    last_error: Exception | None = None

    for candidate_food in validated_candidates:
        try:
            option_score, option = _evaluate_candidate_for_context(candidate_food, context=context)
        except HTTPException as exc:
            last_error = _sanitize_substitution_exception(
                exc,
                candidate_name=str(candidate_food.get("name") or ""),
            )
            continue

        if best_option_score is None or option_score < best_option_score:
            best_option_score = option_score
            best_option = option
            best_candidate = candidate_food
            best_meal_solution, _ = reajustar_comida_manteniendo_alimentos(
                meal=context["meal"],
                current_food=context["current_food"],
                current_food_entry=context["current_food_entry"],
                replacement_food=candidate_food,
                meal_food_lookup={
                    **context["meal_food_lookup"],
                    str(candidate_food.get("code") or ""): candidate_food,
                },
            )

    if best_candidate is None or best_option is None or best_meal_solution is None:
        if last_error is not None:
            raise last_error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo completar la sustitucion con una solucion valida.",
        )

    updated_meal_payload = _build_updated_meal_payload(context["meal"], best_meal_solution)
    updated_diet = persist_updated_meal_in_diet(
        database,
        user=user,
        diet=context["diet"],
        diet_id=diet_id,
        meal_index=context["meal_index"],
        updated_meal=updated_meal_payload,
        preference_profile=context["preference_profile"],
        metadata_overrides={
            "food_catalog_version": context["diet"].food_catalog_version,
            "catalog_source_strategy": context["diet"].catalog_source_strategy,
        },
    )

    strategy_notes = [
        "La sustitucion se limito al mismo macro dominante del alimento original.",
        "Los demas alimentos de la comida se mantuvieron y solo se reajustaron sus cantidades.",
        "Las demas comidas del dia no se modificaron.",
    ]
    if best_option.strategy == "relaxed":
        strategy_notes.append("No habia un encaje perfecto y se devolvio la mejor aproximacion razonable para la comida.")

    return DietMutationResponse(
        diet=updated_diet,
        summary=DietMutationSummary(
            action="food_replaced",
            meal_number=meal_number,
            message=f"Se sustituyo '{context['current_food'].name}' por '{best_candidate['name']}' en la comida {meal_number}.",
            current_food_name=context["current_food"].name,
            replacement_food_name=str(best_candidate.get("name") or ""),
            preserved_meal_numbers=[
                current_meal.meal_number
                for index, current_meal in enumerate(context["diet"].meals)
                if index != context["meal_index"]
            ],
            changed_food_names=[food["name"] for food in updated_meal_payload["foods"]],
            strategy_notes=strategy_notes,
        ),
    )
