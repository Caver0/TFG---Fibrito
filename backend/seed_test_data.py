"""
Seed de datos realistas para validar todo el ciclo backend -> frontend:
- perfil nutricional
- pesos diarios y medias semanales
- dietas activas e historicas
- adherencia diaria y semanal sobre la dieta valida en cada fecha
- fiabilidad / cobertura
- historial de ajustes caloricos calculado con la logica real

Uso:
    python seed_test_data.py
"""

from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "fibrito")
os.environ.setdefault("JWT_SECRET_KEY", "dev-script-secret")
os.environ.setdefault("SPOONACULAR_API_KEY", "dummy")
os.environ.setdefault("SPOONACULAR_BASE_URL", "https://api.spoonacular.com")
os.environ.setdefault("SPOONACULAR_TIMEOUT_SECONDS", "15")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bson import ObjectId

from app.core.database import get_database
from app.schemas.user import serialize_user
from app.services.adherence_service import build_week_label, calculate_weekly_adherence_summary, get_week_bounds
from app.services.dashboard_service import build_dashboard_overview
from app.services.goal_adjustment_service import analyze_weekly_progress
from app.services.nutrition_service import build_nutrition_summary, calculate_macros
from app.services.progress_service import calculate_weekly_averages, list_weight_entries

DEFAULT_USER_ID = "69e6892ef2ed33587160796d"
USER_ID = ObjectId(os.getenv("FIBRITO_SEED_USER_ID", DEFAULT_USER_ID))
TODAY = date.today()
CURRENT_WEEK_START, _ = get_week_bounds(TODAY)
CURRENT_WEEK_DAYS = min(TODAY.weekday() + 1, 7)
RNG_SEED = 20260421
MEALS_PER_DAY = 4

MEAL_TIME_BY_NUMBER = {
    1: time(8, 15),
    2: time(14, 0),
    3: time(18, 0),
    4: time(21, 15),
}

FULL_WEEK_WEIGHT_OFFSETS = (-0.18, -0.10, 0.03, -0.07, 0.00, 0.12, 0.20)
PARTIAL_WEEK_WEIGHT_OFFSETS = (0.10, 0.00, -0.04, 0.02, 0.00, 0.08, 0.12)

ADHERENCE_SCORE_BY_STATUS = {
    "completed": 1.0,
    "modified": 0.5,
    "omitted": 0.0,
}

USER_PROFILE = {
    "name": "Demo Frontend Fibrito",
    "email": "demo.frontend.seed@fibrito.local",
    "password_hash": "seed-demo-user-not-for-login",
    "age": 31,
    "sex": "Masculino",
    "height": 178.0,
    "training_days_per_week": 4,
    "goal": "perder_grasa",
    "food_preferences": {
        "preferred_foods": ["avena", "pollo", "arroz", "salmon", "patata"],
        "disliked_foods": ["refrescos azucarados"],
        "dietary_restrictions": [],
        "allergies": [],
    },
}


@dataclass(frozen=True)
class WeekBlueprint:
    average_weight: float
    adherence_counts: dict[str, int]
    narrative: str
    days_count: int = 7

    @property
    def total_planned_meals(self) -> int:
        return self.days_count * MEALS_PER_DAY


COMPLETE_WEEK_BLUEPRINTS: list[WeekBlueprint] = [
    WeekBlueprint(
        average_weight=84.60,
        adherence_counts={"completed": 24, "modified": 2, "omitted": 1, "pending": 1},
        narrative="Arranque ordenado, con buena estructura y un par de ajustes menores.",
    ),
    WeekBlueprint(
        average_weight=84.05,
        adherence_counts={"completed": 23, "modified": 2, "omitted": 2, "pending": 1},
        narrative="Semana bastante solida, aunque con un par de comidas sociales.",
    ),
    WeekBlueprint(
        average_weight=83.84,
        adherence_counts={"completed": 21, "modified": 3, "omitted": 2, "pending": 2},
        narrative="Cumple bastante, pero el ritmo de bajada ya se queda corto.",
    ),
    WeekBlueprint(
        average_weight=83.34,
        adherence_counts={"completed": 24, "modified": 2, "omitted": 1, "pending": 1},
        narrative="Tras el ajuste, vuelve a una semana estable y consistente.",
    ),
    WeekBlueprint(
        average_weight=83.38,
        adherence_counts={"completed": 10, "modified": 4, "omitted": 9, "pending": 5},
        narrative="Semana muy desordenada: viajes, comidas fuera y muchos huecos sin registrar.",
    ),
    WeekBlueprint(
        average_weight=82.95,
        adherence_counts={"completed": 23, "modified": 3, "omitted": 1, "pending": 1},
        narrative="Retoma el plan y vuelve a ver una bajada clara.",
    ),
    WeekBlueprint(
        average_weight=82.56,
        adherence_counts={"completed": 22, "modified": 4, "omitted": 1, "pending": 1},
        narrative="Semana buena con algun intercambio de alimentos, pero bien trazada.",
    ),
    WeekBlueprint(
        average_weight=81.68,
        adherence_counts={"completed": 25, "modified": 2, "omitted": 0, "pending": 1},
        narrative="Semana muy estricta y con una bajada demasiado rapida para el objetivo.",
    ),
    WeekBlueprint(
        average_weight=81.28,
        adherence_counts={"completed": 24, "modified": 2, "omitted": 1, "pending": 1},
        narrative="Tras subir calorias, la tendencia vuelve a la zona razonable.",
    ),
]

CURRENT_WEEK_BLUEPRINT = WeekBlueprint(
    average_weight=81.10,
    adherence_counts={"completed": 6, "modified": 1, "omitted": 0, "pending": 1},
    narrative="Semana actual parcial: dos dias ya registrados con buen cumplimiento general.",
    days_count=CURRENT_WEEK_DAYS,
)


def round_value(value: float | Decimal, precision: str = "0.01") -> float:
    return float(Decimal(str(value)).quantize(Decimal(precision), rounding=ROUND_HALF_UP))


def day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min).replace(tzinfo=UTC)
    end = datetime.combine(target_date, time.max).replace(tzinfo=UTC)
    return start, end


def shift_datetime(target_date: date, target_time: time) -> datetime:
    return datetime.combine(target_date, target_time).replace(tzinfo=UTC)


def sum_food_totals(foods: list[dict]) -> dict[str, float]:
    return {
        "calories": round_value(sum(food["calories"] for food in foods), "0.01"),
        "protein_grams": round_value(sum(food["protein_grams"] for food in foods), "0.01"),
        "fat_grams": round_value(sum(food["fat_grams"] for food in foods), "0.01"),
        "carb_grams": round_value(sum(food["carb_grams"] for food in foods), "0.01"),
    }


def scale_food(food: dict, scale_ratio: float) -> dict:
    return {
        **food,
        "quantity": round_value(food["quantity"] * scale_ratio, "0.01"),
        "grams": round_value(food["grams"] * scale_ratio, "0.01"),
        "calories": round_value(food["calories"] * scale_ratio, "0.01"),
        "protein_grams": round_value(food["protein_grams"] * scale_ratio, "0.01"),
        "fat_grams": round_value(food["fat_grams"] * scale_ratio, "0.01"),
        "carb_grams": round_value(food["carb_grams"] * scale_ratio, "0.01"),
    }


def build_food(
    food_code: str,
    name: str,
    category: str,
    grams: float,
    calories: float,
    protein_grams: float,
    fat_grams: float,
    carb_grams: float,
) -> dict:
    return {
        "food_code": food_code,
        "source": "internal_catalog",
        "origin_source": "internal_catalog",
        "name": name,
        "category": category,
        "quantity": grams,
        "unit": "g",
        "grams": grams,
        "calories": calories,
        "protein_grams": protein_grams,
        "fat_grams": fat_grams,
        "carb_grams": carb_grams,
    }


MEAL_TEMPLATES = [
    {
        "meal_number": 1,
        "meal_slot": "early",
        "meal_role": "breakfast",
        "meal_label": "Desayuno",
        "distribution_percentage": 25.0,
        "foods": [
            build_food("oats", "Avena", "carbohidratos", 70, 272, 11.8, 4.8, 46.4),
            build_food("greek_yogurt_plain", "Yogur griego natural", "lacteos", 220, 130, 11.0, 4.0, 10.1),
            build_food("banana", "Platano", "frutas", 120, 107, 1.3, 0.4, 27.0),
            build_food("almonds", "Almendras", "grasas", 20, 115, 4.2, 10.0, 3.8),
        ],
    },
    {
        "meal_number": 2,
        "meal_slot": "main",
        "meal_role": "meal",
        "meal_label": "Comida principal",
        "distribution_percentage": 35.0,
        "foods": [
            build_food("chicken_breast", "Pechuga de pollo", "proteinas", 190, 228, 43.7, 3.8, 0.0),
            build_food("rice", "Arroz", "carbohidratos", 100, 364, 7.1, 0.8, 80.0),
            build_food("broccoli", "Brocoli", "vegetales", 180, 61, 5.0, 0.7, 11.9),
            build_food("olive_oil", "Aceite de oliva", "grasas", 10, 88, 0.0, 10.0, 0.0),
        ],
    },
    {
        "meal_number": 3,
        "meal_slot": "main",
        "meal_role": "training_focus",
        "meal_label": "Comida de entreno",
        "distribution_percentage": 15.0,
        "foods": [
            build_food("cottage_cheese", "Queso cottage", "lacteos", 180, 185, 22.5, 8.1, 5.6),
            build_food("apple", "Manzana", "frutas", 150, 78, 0.4, 0.2, 20.6),
            build_food("walnuts", "Nueces", "grasas", 20, 131, 3.0, 13.1, 2.8),
        ],
    },
    {
        "meal_number": 4,
        "meal_slot": "late",
        "meal_role": "dinner",
        "meal_label": "Cena",
        "distribution_percentage": 25.0,
        "foods": [
            build_food("salmon", "Salmon", "proteinas", 160, 320, 31.7, 21.4, 0.0),
            build_food("sweet_potato", "Boniato", "carbohidratos", 200, 173, 3.2, 0.2, 40.2),
            build_food("spinach", "Espinacas", "vegetales", 120, 35, 3.5, 0.5, 4.3),
        ],
    },
]

BASE_MEAL_CALORIES = {
    template["meal_number"]: sum(food["calories"] for food in template["foods"])
    for template in MEAL_TEMPLATES
}


def build_meal_payload(template: dict, target_calories: float, target_macros: dict[str, float]) -> dict:
    distribution_ratio = template["distribution_percentage"] / 100.0
    meal_target_calories = round_value(target_calories * distribution_ratio, "0.1")
    base_calories = BASE_MEAL_CALORIES[template["meal_number"]]
    scale_ratio = meal_target_calories / base_calories if base_calories else 1.0
    foods = [scale_food(food, scale_ratio) for food in template["foods"]]
    actuals = sum_food_totals(foods)

    meal_target_protein = round_value(target_macros["protein_grams"] * distribution_ratio, "0.1")
    meal_target_fat = round_value(target_macros["fat_grams"] * distribution_ratio, "0.1")
    meal_target_carb = round_value(target_macros["carb_grams"] * distribution_ratio, "0.1")

    return {
        "meal_number": template["meal_number"],
        "meal_slot": template["meal_slot"],
        "meal_role": template["meal_role"],
        "meal_label": template["meal_label"],
        "distribution_percentage": template["distribution_percentage"],
        "target_calories": meal_target_calories,
        "target_protein_grams": meal_target_protein,
        "target_fat_grams": meal_target_fat,
        "target_carb_grams": meal_target_carb,
        "actual_calories": round_value(actuals["calories"], "0.1"),
        "actual_protein_grams": round_value(actuals["protein_grams"], "0.1"),
        "actual_fat_grams": round_value(actuals["fat_grams"], "0.1"),
        "actual_carb_grams": round_value(actuals["carb_grams"], "0.1"),
        "calorie_difference": round_value(actuals["calories"] - meal_target_calories, "0.1"),
        "protein_difference": round_value(actuals["protein_grams"] - meal_target_protein, "0.1"),
        "fat_difference": round_value(actuals["fat_grams"] - meal_target_fat, "0.1"),
        "carb_difference": round_value(actuals["carb_grams"] - meal_target_carb, "0.1"),
        "foods": foods,
    }


def build_diet_document(
    *,
    target_calories: float,
    reference_weight: float,
    valid_from_date: date,
    adjusted_from_diet_id: ObjectId | None = None,
    is_active: bool = True,
) -> dict:
    macros = calculate_macros(reference_weight, target_calories)
    meals = [
        build_meal_payload(template, target_calories, macros)
        for template in MEAL_TEMPLATES
    ]
    actual_calories = round_value(sum(meal["actual_calories"] for meal in meals), "0.1")
    actual_protein = round_value(sum(meal["actual_protein_grams"] for meal in meals), "0.1")
    actual_fat = round_value(sum(meal["actual_fat_grams"] for meal in meals), "0.1")
    actual_carb = round_value(sum(meal["actual_carb_grams"] for meal in meals), "0.1")
    created_at = shift_datetime(valid_from_date, time(6, 30))
    valid_from = shift_datetime(valid_from_date, time.min)

    return {
        "user_id": USER_ID,
        "created_at": created_at,
        "is_active": is_active,
        "valid_from": valid_from,
        "valid_to": None,
        "adjusted_from_diet_id": adjusted_from_diet_id,
        "meals_count": len(meals),
        "target_calories": round_value(target_calories, "0.1"),
        "protein_grams": round_value(macros["protein_grams"], "0.1"),
        "fat_grams": round_value(macros["fat_grams"], "0.1"),
        "carb_grams": round_value(macros["carb_grams"], "0.1"),
        "actual_calories": actual_calories,
        "actual_protein_grams": actual_protein,
        "actual_fat_grams": actual_fat,
        "actual_carb_grams": actual_carb,
        "calorie_difference": round_value(actual_calories - target_calories, "0.1"),
        "protein_difference": round_value(actual_protein - macros["protein_grams"], "0.1"),
        "fat_difference": round_value(actual_fat - macros["fat_grams"], "0.1"),
        "carb_difference": round_value(actual_carb - macros["carb_grams"], "0.1"),
        "distribution_percentages": [template["distribution_percentage"] for template in MEAL_TEMPLATES],
        "training_time_of_day": "tarde",
        "training_optimization_applied": True,
        "food_data_source": "internal",
        "food_data_sources": ["internal"],
        "food_catalog_version": "seed-demo",
        "food_preferences_applied": False,
        "applied_dietary_restrictions": [],
        "applied_allergies": [],
        "preferred_food_matches": 0,
        "diversity_strategy_applied": False,
        "food_usage_summary": {},
        "food_filter_warnings": [],
        "catalog_source_strategy": "seed_realistic_timeline",
        "spoonacular_attempted": False,
        "spoonacular_attempts": 0,
        "spoonacular_hits": 0,
        "cache_hits": 0,
        "internal_fallbacks": sum(len(meal["foods"]) for meal in meals),
        "resolved_foods_count": sum(len(meal["foods"]) for meal in meals),
        "meals": meals,
    }


def build_macro_snapshot(reference_weight: float | None, target_calories: float | None) -> dict | None:
    if reference_weight is None or target_calories is None:
        return None

    macros = calculate_macros(reference_weight, target_calories)
    return {
        "protein_grams": round_value(macros["protein_grams"], "0.1"),
        "fat_grams": round_value(macros["fat_grams"], "0.1"),
        "carb_grams": round_value(macros["carb_grams"], "0.1"),
    }


def ensure_demo_user(database, initial_weight: float, initial_target_calories: float) -> None:
    existing_user = database.users.find_one({"_id": USER_ID})
    profile_updates = {
        "age": USER_PROFILE["age"],
        "sex": USER_PROFILE["sex"],
        "height": USER_PROFILE["height"],
        "current_weight": round_value(initial_weight, "0.1"),
        "training_days_per_week": USER_PROFILE["training_days_per_week"],
        "goal": USER_PROFILE["goal"],
        "target_calories": round_value(initial_target_calories, "0.1"),
        "food_preferences": USER_PROFILE["food_preferences"],
    }

    if existing_user is None:
        database.users.insert_one({
            "_id": USER_ID,
            "name": USER_PROFILE["name"],
            "email": USER_PROFILE["email"],
            "password_hash": USER_PROFILE["password_hash"],
            "created_at": datetime.now(UTC),
            **profile_updates,
        })
        return

    database.users.update_one(
        {"_id": USER_ID},
        {"$set": profile_updates},
    )


def reset_user_timeline(database) -> None:
    database.diets.delete_many({"user_id": USER_ID})
    database.diet_adherence.delete_many({"user_id": USER_ID})
    database.weight_logs.delete_many({"user_id": USER_ID})
    database.calorie_adjustments.delete_many({"user_id": USER_ID})


def validate_blueprints() -> None:
    for blueprint in [*COMPLETE_WEEK_BLUEPRINTS, CURRENT_WEEK_BLUEPRINT]:
        total_assigned = sum(blueprint.adherence_counts.values())
        if total_assigned != blueprint.total_planned_meals:
            raise ValueError(
                f"Blueprint invalido: {blueprint.narrative}. "
                f"Asignadas {total_assigned} comidas y esperadas {blueprint.total_planned_meals}."
            )


def choose_slots(
    available_slots: set[tuple[int, int]],
    count: int,
    *,
    meal_priority: tuple[int, ...],
    day_priority: tuple[int, ...],
    rng: random.Random,
) -> set[tuple[int, int]]:
    if count <= 0:
        return set()

    meal_rank = {meal_number: index for index, meal_number in enumerate(meal_priority)}
    day_rank = {day_index: index for index, day_index in enumerate(day_priority)}

    decorated = []
    for slot in available_slots:
        day_index, meal_number = slot
        decorated.append((
            (
                meal_rank.get(meal_number, 99),
                day_rank.get(day_index, 99),
                rng.random(),
            ),
            slot,
        ))

    decorated.sort(key=lambda item: item[0])
    return {slot for _, slot in decorated[:count]}


def build_status_schedule(week_start: date, blueprint: WeekBlueprint) -> dict[tuple[int, int], str | None]:
    rng = random.Random(f"{RNG_SEED}-{week_start.isoformat()}-{blueprint.narrative}")
    all_slots = {
        (day_index, meal_number)
        for day_index in range(blueprint.days_count)
        for meal_number in range(1, MEALS_PER_DAY + 1)
    }
    status_by_slot: dict[tuple[int, int], str | None] = {
        slot: "completed"
        for slot in all_slots
    }

    pending_slots = choose_slots(
        all_slots,
        blueprint.adherence_counts.get("pending", 0),
        meal_priority=(3, 4, 1, 2),
        day_priority=(4, 5, 6, 0, 1, 2, 3),
        rng=rng,
    )
    for slot in pending_slots:
        status_by_slot[slot] = None

    remaining_slots = {slot for slot in all_slots if slot not in pending_slots}
    omitted_slots = choose_slots(
        remaining_slots,
        blueprint.adherence_counts.get("omitted", 0),
        meal_priority=(3, 4, 1, 2),
        day_priority=(5, 6, 4, 2, 3, 1, 0),
        rng=rng,
    )
    for slot in omitted_slots:
        status_by_slot[slot] = "omitted"

    remaining_slots = {
        slot
        for slot in remaining_slots
        if slot not in omitted_slots
    }
    modified_slots = choose_slots(
        remaining_slots,
        blueprint.adherence_counts.get("modified", 0),
        meal_priority=(2, 4, 1, 3),
        day_priority=(4, 5, 2, 1, 3, 0, 6),
        rng=rng,
    )
    for slot in modified_slots:
        status_by_slot[slot] = "modified"

    return status_by_slot


def build_status_note(status: str, meal_number: int, day_index: int) -> str | None:
    if status == "completed":
        return None

    if status == "modified":
        options = {
            1: [
                "Cambio el desayuno por una opcion equivalente y mas rapida.",
                "Ajusto cantidades del desayuno para cuadrarlo con el dia.",
            ],
            2: [
                "Comio fuera y ajusto la racion de hidratos.",
                "Modifico la comida principal manteniendo una estructura similar.",
            ],
            3: [
                "Cambio la comida de entreno por una alternativa similar.",
                "Ajusto la merienda preentreno por horarios.",
            ],
            4: [
                "La cena se adapto a una opcion casera similar.",
                "Hizo una cena mas flexible pero intentando respetar el plan.",
            ],
        }
        pool = options.get(meal_number, ["Modifico la comida respetando aproximadamente el objetivo."])
        return pool[day_index % len(pool)]

    omitted_options = {
        1: "Se salto el desayuno por falta de tiempo.",
        2: "No pudo hacer la comida principal segun lo previsto.",
        3: "Se salto la merienda por horario o falta de hambre.",
        4: "La cena quedo fuera del plan ese dia.",
    }
    return omitted_options.get(meal_number, "Comida omitida.")


def generate_adherence_documents(
    *,
    diet_id: ObjectId,
    week_start: date,
    blueprint: WeekBlueprint,
) -> list[dict]:
    schedule = build_status_schedule(week_start, blueprint)
    adherence_documents: list[dict] = []

    for day_index in range(blueprint.days_count):
        target_date = week_start + timedelta(days=day_index)
        for meal_number in range(1, MEALS_PER_DAY + 1):
            status = schedule[(day_index, meal_number)]
            if status is None:
                continue

            created_at = shift_datetime(target_date, MEAL_TIME_BY_NUMBER[meal_number])
            adherence_documents.append({
                "user_id": USER_ID,
                "diet_id": diet_id,
                "meal_number": meal_number,
                "date": target_date.isoformat(),
                "status": status,
                "note": build_status_note(status, meal_number, day_index),
                "adherence_score": ADHERENCE_SCORE_BY_STATUS[status],
                "created_at": created_at,
                "updated_at": created_at + timedelta(minutes=25),
            })

    return adherence_documents


def generate_weight_logs(
    *,
    week_start: date,
    blueprint: WeekBlueprint,
) -> list[dict]:
    offsets = (
        FULL_WEEK_WEIGHT_OFFSETS
        if blueprint.days_count == 7
        else PARTIAL_WEEK_WEIGHT_OFFSETS
    )
    weight_logs: list[dict] = []

    for day_index in range(blueprint.days_count):
        target_date = week_start + timedelta(days=day_index)
        weight = round_value(blueprint.average_weight + offsets[day_index], "0.01")
        weight_logs.append({
            "user_id": USER_ID,
            "weight": weight,
            "date": target_date.isoformat(),
            "created_at": shift_datetime(target_date, time(7, 10)),
        })

    return weight_logs


def update_user_state(database, *, current_weight: float, target_calories: float | None = None) -> None:
    updates = {
        "current_weight": round_value(current_weight, "0.1"),
    }
    if target_calories is not None:
        updates["target_calories"] = round_value(target_calories, "0.1")

    database.users.update_one(
        {"_id": USER_ID},
        {"$set": updates},
    )


def close_diet_version(database, diet_id: ObjectId, valid_to_date: date) -> None:
    _, valid_to = day_bounds(valid_to_date)
    database.diets.update_one(
        {"_id": diet_id, "user_id": USER_ID},
        {
            "$set": {
                "is_active": False,
                "valid_to": valid_to,
            }
        },
    )


def create_diet_version(
    database,
    *,
    target_calories: float,
    reference_weight: float,
    valid_from_date: date,
    previous_diet_id: ObjectId | None = None,
) -> ObjectId:
    if previous_diet_id is not None:
        close_diet_version(database, previous_diet_id, valid_from_date - timedelta(days=1))

    diet_document = build_diet_document(
        target_calories=target_calories,
        reference_weight=reference_weight,
        valid_from_date=valid_from_date,
        adjusted_from_diet_id=previous_diet_id,
        is_active=True,
    )
    inserted = database.diets.insert_one(diet_document)
    return inserted.inserted_id


def fetch_current_user(database):
    document = database.users.find_one({"_id": USER_ID})
    if document is None:
        raise RuntimeError("No se pudo cargar el usuario demo despues del seed.")

    return serialize_user(document)


def persist_adjustment_history_entry(
    database,
    *,
    analysis,
    created_at: datetime,
    adjustment_applied: bool,
    note_lines: list[str],
    macro_reference_weight: float | None,
) -> None:
    adjustment_document = {
        "user_id": USER_ID,
        "created_at": created_at,
        "previous_week_label": analysis.previous_week_label,
        "current_week_label": analysis.current_week_label,
        "previous_week_avg": analysis.previous_week_avg,
        "current_week_avg": analysis.current_week_avg,
        "weekly_change": analysis.weekly_change,
        "goal": analysis.goal,
        "progress_status": analysis.progress_status,
        "progress_direction_ok": analysis.progress_direction_ok,
        "progress_rate_ok": analysis.progress_rate_ok,
        "adjustment_applied": adjustment_applied,
        "max_weekly_loss": analysis.max_weekly_loss,
        "calorie_change": analysis.calorie_change,
        "previous_target_calories": analysis.previous_target_calories,
        "new_target_calories": analysis.new_target_calories,
        "macro_reference_weight": macro_reference_weight,
        "previous_target_macros": build_macro_snapshot(
            macro_reference_weight,
            analysis.previous_target_calories,
        ),
        "new_target_macros": build_macro_snapshot(
            macro_reference_weight,
            analysis.new_target_calories,
        ),
        "diet_adjustment_notes": note_lines,
        "adjustment_reason": analysis.adjustment_reason,
        "reason": analysis.adjustment_reason,
    }
    database.calorie_adjustments.insert_one(adjustment_document)


def seed_timeline(database) -> None:
    validate_blueprints()

    first_complete_week_start = CURRENT_WEEK_START - timedelta(days=7 * len(COMPLETE_WEEK_BLUEPRINTS))
    first_weight = COMPLETE_WEEK_BLUEPRINTS[0].average_weight

    initial_summary = build_nutrition_summary({
        "age": USER_PROFILE["age"],
        "sex": USER_PROFILE["sex"],
        "height": USER_PROFILE["height"],
        "current_weight": first_weight,
        "training_days_per_week": USER_PROFILE["training_days_per_week"],
        "goal": USER_PROFILE["goal"],
    })
    initial_target_calories = round_value(initial_summary.target_calories, "0.1")

    reset_user_timeline(database)
    ensure_demo_user(database, first_weight, initial_target_calories)

    active_target_calories = initial_target_calories
    active_diet_id = create_diet_version(
        database,
        target_calories=active_target_calories,
        reference_weight=first_weight,
        valid_from_date=first_complete_week_start,
    )

    complete_week_starts = [
        CURRENT_WEEK_START - timedelta(days=7 * weeks_ago)
        for weeks_ago in range(len(COMPLETE_WEEK_BLUEPRINTS), 0, -1)
    ]

    for week_start, blueprint in zip(complete_week_starts, COMPLETE_WEEK_BLUEPRINTS, strict=True):
        weight_logs = generate_weight_logs(
            week_start=week_start,
            blueprint=blueprint,
        )
        adherence_documents = generate_adherence_documents(
            diet_id=active_diet_id,
            week_start=week_start,
            blueprint=blueprint,
        )

        database.weight_logs.insert_many(weight_logs)
        database.diet_adherence.insert_many(adherence_documents)

        latest_week_weight = weight_logs[-1]["weight"]
        update_user_state(
            database,
            current_weight=latest_week_weight,
            target_calories=active_target_calories,
        )

        weekly_weights = list_weight_entries(database, str(USER_ID))
        weekly_averages = calculate_weekly_averages(
            weekly_weights,
            reference_date=week_start + timedelta(days=7),
        )
        weekly_summary = calculate_weekly_adherence_summary(
            database,
            str(USER_ID),
            week_label=build_week_label(week_start),
        )
        analysis = analyze_weekly_progress(
            fetch_current_user(database),
            weekly_averages,
            adherence_level=weekly_summary.adherence_level,
            confidence_factor=weekly_summary.confidence_factor,
            tracking_coverage_percentage=weekly_summary.tracking_coverage_percentage,
        )

        if not analysis.can_analyze:
            continue

        adjustment_created_at = shift_datetime(week_start + timedelta(days=6), time(21, 30))
        notes: list[str] = []
        adjustment_applied = bool(analysis.adjustment_needed)

        if adjustment_applied:
            next_week_start = week_start + timedelta(days=7)
            notes = [
                "Se genero una nueva version historica de la dieta para la semana siguiente.",
                "Las comidas se reescalaron manteniendo la misma estructura y los mismos alimentos base.",
            ]
            active_diet_id = create_diet_version(
                database,
                target_calories=analysis.new_target_calories,
                reference_weight=analysis.current_week_avg or latest_week_weight,
                valid_from_date=next_week_start,
                previous_diet_id=active_diet_id,
            )
            active_target_calories = round_value(analysis.new_target_calories, "0.1")
            update_user_state(
                database,
                current_weight=latest_week_weight,
                target_calories=active_target_calories,
            )
        elif analysis.progress_status == "needs_attention":
            notes = [
                "No se aplico ajuste automatico porque la adherencia de la semana no permite interpretar el peso con suficiente confianza.",
                "Se mantiene la dieta activa hasta recuperar una semana mas representativa.",
            ]
        else:
            notes = [
                "Se mantiene la misma dieta porque el progreso semanal esta dentro del rango esperado.",
            ]

        persist_adjustment_history_entry(
            database,
            analysis=analysis,
            created_at=adjustment_created_at,
            adjustment_applied=adjustment_applied,
            note_lines=notes,
            macro_reference_weight=analysis.current_week_avg or latest_week_weight,
        )

    current_week_weights = generate_weight_logs(
        week_start=CURRENT_WEEK_START,
        blueprint=CURRENT_WEEK_BLUEPRINT,
    )
    current_week_adherence = generate_adherence_documents(
        diet_id=active_diet_id,
        week_start=CURRENT_WEEK_START,
        blueprint=CURRENT_WEEK_BLUEPRINT,
    )
    database.weight_logs.insert_many(current_week_weights)
    database.diet_adherence.insert_many(current_week_adherence)

    update_user_state(
        database,
        current_weight=current_week_weights[-1]["weight"],
        target_calories=active_target_calories,
    )


def print_summary(database) -> None:
    current_user = fetch_current_user(database)
    dashboard = build_dashboard_overview(database, current_user)
    current_week_summary = calculate_weekly_adherence_summary(
        database,
        str(USER_ID),
        reference_date=TODAY,
    )
    reference_week_label = dashboard.weight_progress.latest_analysis.current_week_label
    reference_week_summary = calculate_weekly_adherence_summary(
        database,
        str(USER_ID),
        week_label=reference_week_label,
    ) if reference_week_label else None
    reference_registered_adherence = (
        round_value(reference_week_summary.weekly_adherence_factor * 100, "0.01")
        if reference_week_summary is not None
        else None
    )
    current_registered_adherence = round_value(
        current_week_summary.weekly_adherence_factor * 100,
        "0.01",
    )

    print(
        "Seed completado para "
        f"{str(USER_ID)} | "
        f"dietas={database.diets.count_documents({'user_id': USER_ID})} | "
        f"pesos={database.weight_logs.count_documents({'user_id': USER_ID})} | "
        f"adherencia={database.diet_adherence.count_documents({'user_id': USER_ID})} | "
        f"ajustes={database.calorie_adjustments.count_documents({'user_id': USER_ID})}"
    )
    print(
        "Analisis vigente: "
        f"{dashboard.weight_progress.latest_analysis.previous_week_label} -> "
        f"{dashboard.weight_progress.latest_analysis.current_week_label} | "
        f"estado={dashboard.weight_progress.latest_analysis.progress_status} | "
        f"cambio={dashboard.weight_progress.latest_analysis.weekly_change} kg/sem | "
        f"kcal objetivo={dashboard.summary.current_target_calories}"
    )
    if reference_week_summary is not None:
        print(
            "Semana de referencia dashboard/progreso: "
            f"{reference_week_summary.week_label} | "
            f"adherencia_registrada={reference_registered_adherence}% | "
            f"cobertura={reference_week_summary.tracking_coverage_percentage}% | "
            f"fiabilidad={reference_week_summary.confidence_percentage}%"
        )
    print(
        "Semana actual parcial dietas: "
        f"{current_week_summary.week_label} | "
        f"adherencia_registrada={current_registered_adherence}% | "
        f"cobertura={current_week_summary.tracking_coverage_percentage}% | "
        f"fiabilidad={current_week_summary.confidence_percentage}%"
    )


def main() -> None:
    database = get_database()
    database.command("ping")
    seed_timeline(database)
    print_summary(database)


if __name__ == "__main__":
    main()
