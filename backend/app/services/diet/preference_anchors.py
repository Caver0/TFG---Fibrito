"""Resolución de alimentos preferidos a anclas y soportes por comida.

Responsabilidad:
  Para cada alimento que el usuario quiere que aparezca en su dieta, este módulo
  determina cómo y dónde colocarlo:

    1. Como ANCLA PRINCIPAL: el alimento cubre un rol estructural (protein/carb/fat)
       en una comida concreta → se pasa al solver como forced_role_codes.

    2. Como SOPORTE COMPLEMENTARIO: el alimento no puede ser rol principal (conflicto
       o no tiene densidad macro suficiente), pero puede acompañar la comida como fruta,
       lácteo o verdura fuera del sistema lineal → se inyecta en las opciones de soporte
       del solver.

    3. DESCARTADO: el alimento no encaja en ningún hueco disponible. El motivo queda
       registrado en los diagnósticos para depuración.

Ejemplos:
  - cornflakes → carb principal (ancla) en desayuno
  - dátiles → no puede ser carb del desayuno si ya está cornflakes,
               pero sí puede ser soporte de fruta en el mismo desayuno
  - pollo + arroz → anclas protein + carb en comida principal
  - yogur + avena → anclas protein + carb en desayuno
"""
from __future__ import annotations

from app.services.diet.candidates import (
    construir_cantidad_soporte_razonable,
    es_soporte_significativo,
    get_candidate_role_for_food,
    get_food_role_fit_score,
    get_support_food_fit_score,
    is_food_allowed_for_role_and_slot,
    is_support_food_allowed,
)
from app.services.food_group_service import derive_functional_group
from app.services.food_preferences_service import buscar_alimentos_por_nombre

# Grupos funcionales que pueden actuar como soporte complementario fuera del sistema lineal
_GRUPOS_SOPORTE = {"fruit", "dairy", "vegetable"}


def resolver_anclas_preferidas(
    *,
    preferred_foods: list[str],
    food_lookup: dict[str, dict],
    meal_slots: list[str],
    meal_roles: list[str],
    training_focus_flags: list[bool],
) -> dict:
    """Asigna alimentos preferidos a roles principales o de soporte dentro del plan diario.

    Para cada alimento preferido:
      - Intenta primero como ANCLA PRINCIPAL (protein/carb/fat) buscando la comida
        donde mejor encaje según puntuación de afinidad. Si lo consigue, queda reservado
        como forced_role_codes para esa comida.
      - Si no hay hueco como ancla (rol ocupado, slot incompatible, sin grupo funcional
        principal), intenta como SOPORTE COMPLEMENTARIO (fruta/lácteo/verdura). Si lo
        consigue, se inyecta en las opciones de soporte del solver de esa comida.
      - Si tampoco hay hueco de soporte, queda DESCARTADO con el motivo registrado.

    Returns:
        {
            "anclas":      {meal_index: {"protein": code, "carb": code, ...}},
            "soporte":     {meal_index: [{"role": grupo, "food_code": code, "quantity": qty}]},
            "diagnosticos": [{"preferido": str, "estado": str, ...}, ...]
        }
    """
    n_comidas = len(meal_slots)
    diagnosticos: list[dict] = []
    anclas: dict[int, dict[str, str]] = {}
    soporte: dict[int, list[dict]] = {}
    # Roles principales ya ocupados en cada comida (evita dos anclas en el mismo rol)
    roles_ocupados: dict[int, set[str]] = {i: set() for i in range(n_comidas)}
    # Grupos de soporte ya asignados en cada comida (evita dos frutas o dos lácteos)
    grupos_soporte_ocupados: dict[int, set[str]] = {i: set() for i in range(n_comidas)}

    for texto_preferido in preferred_foods:
        codigos = buscar_alimentos_por_nombre(texto_preferido, food_lookup)

        if not codigos:
            diagnosticos.append({
                "preferido": texto_preferido,
                "estado": "no_encontrado",
                "razon": "ningún alimento del catálogo coincide con este nombre; "
                         "si es un alimento externo, verifica que esté en Spoonacular o en el catálogo local",
            })
            continue

        # ── Intento 1: ancla principal (protein / carb / fat) ───────────────────────────────
        mejor_ancla: tuple[int, str, str, float] | None = None

        for code in codigos:
            food = food_lookup.get(code)
            if not food:
                continue
            for meal_index in range(n_comidas):
                meal_slot = meal_slots[meal_index]
                meal_role = meal_roles[meal_index]
                training_focus = training_focus_flags[meal_index]

                role = get_candidate_role_for_food(food, meal_slot)
                if role is None:
                    continue
                if not is_food_allowed_for_role_and_slot(food, role=role, meal_slot=meal_slot):
                    continue
                if role in roles_ocupados[meal_index]:
                    continue

                score = get_food_role_fit_score(
                    food,
                    role=role,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                    training_focus=training_focus,
                )
                if mejor_ancla is None or score > mejor_ancla[3]:
                    mejor_ancla = (meal_index, role, code, score)

        if mejor_ancla is not None:
            meal_index, role, code, _ = mejor_ancla
            anclas.setdefault(meal_index, {})[role] = code
            roles_ocupados[meal_index].add(role)
            diagnosticos.append({
                "preferido": texto_preferido,
                "estado": "anclado",
                "comida_indice": meal_index,
                "slot": meal_slots[meal_index],
                "rol": role,
                "codigo": code,
            })
            continue

        # ── Intento 2: soporte complementario (fruit / dairy / vegetable) ───────────────────
        # El alimento no cabe como rol estructural principal, pero puede acompañar la comida
        # fuera del sistema lineal (ej: dátiles como fruta en el desayuno donde cornflakes
        # ya es el carb principal).
        mejor_soporte: tuple[int, str, str, float, float] | None = None

        for code in codigos:
            food = food_lookup.get(code)
            if not food:
                continue
            grupo = derive_functional_group(food)
            if grupo not in _GRUPOS_SOPORTE:
                # Solo pueden ser soporte alimentos de grupos no estructurales
                continue
            support_role = grupo

            for meal_index in range(n_comidas):
                meal_slot = meal_slots[meal_index]
                meal_role = meal_roles[meal_index]
                training_focus = training_focus_flags[meal_index]

                if support_role in grupos_soporte_ocupados[meal_index]:
                    continue
                if not is_support_food_allowed(
                    food,
                    support_role=support_role,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                ):
                    continue
                cantidad = construir_cantidad_soporte_razonable(
                    food,
                    support_role=support_role,
                )
                if not es_soporte_significativo(
                    food,
                    support_role=support_role,
                    quantity=cantidad,
                ):
                    continue

                score = get_support_food_fit_score(
                    food,
                    support_role=support_role,
                    meal_slot=meal_slot,
                    meal_role=meal_role,
                    training_focus=training_focus,
                )
                if mejor_soporte is None or score > mejor_soporte[3]:
                    mejor_soporte = (meal_index, support_role, code, score, cantidad)

        if mejor_soporte is not None:
            meal_index, support_role, code, _, cantidad = mejor_soporte
            soporte.setdefault(meal_index, []).append({
                "role": support_role,
                "food_code": code,
                "quantity": cantidad,
            })
            grupos_soporte_ocupados[meal_index].add(support_role)
            diagnosticos.append({
                "preferido": texto_preferido,
                "estado": "usado_como_soporte",
                "comida_indice": meal_index,
                "slot": meal_slots[meal_index],
                "rol_soporte": support_role,
                "codigo": code,
            })
            continue

        # ── Sin hueco disponible ─────────────────────────────────────────────────────────────
        diagnosticos.append({
            "preferido": texto_preferido,
            "estado": "descartado_sin_hueco_compatible",
            "razon": "todos los roles principales y de soporte compatibles ya están ocupados, "
                     "o el alimento no es válido en ningún contexto de comida disponible",
            "codigos_encontrados": codigos,
        })

    return {"anclas": anclas, "soporte": soporte, "diagnosticos": diagnosticos}
