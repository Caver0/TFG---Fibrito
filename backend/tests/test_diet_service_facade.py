"""Tests de regresion para la fachada publica de diet_service."""

from app.services import diet_service


def test_diet_service_reexporta_api_esperada():
    """diet_service actua como fachada compatible para otros servicios del backend."""
    nombres_esperados = [
        "activate_user_diet",
        "generate_food_based_diet",
        "get_active_user_diet",
        "get_user_diet_by_id",
        "get_user_diet_document_by_id",
        "list_user_diets",
        "save_diet",
        "build_exact_meal_solution",
        "build_food_portion",
        "build_updated_diet_payload",
        "calculate_difference_summary",
        "calculate_meal_actuals_from_foods",
        "collect_selected_food_codes",
        "create_daily_food_usage_tracker",
        "find_exact_solution_for_meal",
        "generate_food_based_meal",
        "get_role_candidate_codes",
        "get_support_option_specs",
        "resolve_meal_context",
        "track_food_usage_across_day",
    ]

    for nombre in nombres_esperados:
        assert hasattr(diet_service, nombre), f"Falta reexportar {nombre} en diet_service"
