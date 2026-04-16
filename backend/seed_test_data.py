"""
Inserta datos de prueba realistas para el usuario 69e0c0acbeb12727983b9127.
Escenario: volumen limpio (ganar_masa), 75 kg, 180 cm, 25 años, hombre,
4 días/semana entrenamiento, 21 días de registros.

Uso:
    python seed_test_data.py
"""
import os
import sys
from datetime import UTC, date, datetime, timedelta

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "fibrito")
os.environ.setdefault("JWT_SECRET_KEY", "dev-script-secret")
os.environ.setdefault("SPOONACULAR_API_KEY", "dummy")
os.environ.setdefault("SPOONACULAR_BASE_URL", "https://api.spoonacular.com")
os.environ.setdefault("SPOONACULAR_TIMEOUT_SECONDS", "15")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bson import ObjectId

from app.core.database import get_database

USER_ID = ObjectId("69e0c0acbeb12727983b9127")
TODAY = date.today()

# Perfil nutricional: 75 kg, 180 cm, 25 años, hombre, ganar_masa, 4 dias/semana
# BMR = 10*75 + 6.25*180 - 5*25 + 5 = 750 + 1125 - 125 + 5 = 1755
# TDEE = 1755 * 1.55 (4 dias) = 2720.25
# Target calories (ganar_masa, factor 1.12) = 2720.25 * 1.12 = 3046.7
TARGET_CALORIES = 3047.0
CURRENT_WEIGHT = 75.0
PROTEIN_G = round(CURRENT_WEIGHT * 2, 1)      # 150 g
FAT_G = round(CURRENT_WEIGHT * 0.8, 1)         # 60 g
CARBS_G = round((TARGET_CALORIES - PROTEIN_G * 4 - FAT_G * 9) / 4, 1)  # ~537 g

MEAL_DISTRIBUTIONS = [
    (1, 0.30),  # Desayuno 30%
    (2, 0.35),  # Comida 35%
    (3, 0.20),  # Merienda 20%
    (4, 0.15),  # Cena 15%
]

def _food(food_code, name, category, grams, calories, protein_grams, fat_grams, carb_grams):
    """Helper que construye un documento de alimento con el formato exacto del sistema."""
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


# Alimentos por comida (realistas para ganar_masa)
DIET_MEALS_TEMPLATE = [
    {
        "meal_number": 1,
        "meal_slot": "early",
        "foods": [
            _food("oatmeal_cooked",      "Avena cocida",           "carbohidratos", 120,  83,  3.0,  1.7, 14.4),
            _food("greek_yogurt_plain",  "Yogur griego natural",   "lacteos",       200, 118, 10.0,  3.6,  9.2),
            _food("banana",              "Plátano",                 "frutas",        120, 107,  1.3,  0.4, 27.0),
            _food("almonds",             "Almendras",               "grasas",         30, 173,  6.3, 15.0,  5.7),
            _food("whole_wheat_bread",   "Pan integral",            "carbohidratos",  80, 212,  7.6,  2.4, 40.4),
        ],
    },
    {
        "meal_number": 2,
        "meal_slot": "main",
        "foods": [
            _food("chicken_breast_cooked", "Pechuga de pollo cocida", "proteinas",    200, 330, 62.0,  7.2,  0.0),
            _food("white_rice_cooked",     "Arroz blanco cocido",     "carbohidratos",250, 325,  6.0,  0.5, 71.8),
            _food("broccoli_cooked",       "Brócoli cocido",          "vegetales",    150,  55,  4.7,  0.5, 10.0),
            _food("olive_oil",             "Aceite de oliva",          "grasas",       10,  88,  0.0, 10.0,  0.0),
        ],
    },
    {
        "meal_number": 3,
        "meal_slot": "snack",
        "foods": [
            _food("cottage_cheese", "Queso cottage",  "lacteos",  200, 206, 25.0,  9.0,  6.2),
            _food("apple",          "Manzana",         "frutas",   150,  78,  0.4,  0.2, 20.6),
            _food("walnuts",        "Nueces",          "grasas",    25, 164,  3.8, 16.4,  3.5),
        ],
    },
    {
        "meal_number": 4,
        "meal_slot": "late",
        "foods": [
            _food("salmon_fillet_baked",  "Salmón al horno",       "proteinas",    150, 265, 37.5, 13.0,  0.0),
            _food("sweet_potato_cooked",  "Boniato cocido",        "carbohidratos",180, 162,  3.6,  0.2, 37.6),
            _food("spinach_cooked",       "Espinacas cocidas",     "vegetales",    100,  29,  3.0,  0.4,  3.7),
        ],
    },
]


def _meal_totals(foods):
    return (
        round(sum(f.get("calories") or 0 for f in foods), 1),
        round(sum(f.get("protein_grams") or 0 for f in foods), 1),
        round(sum(f.get("fat_grams") or 0 for f in foods), 1),
        round(sum(f.get("carb_grams") or 0 for f in foods), 1),
    )


def _build_meal(template, target_cal, target_p, target_f, target_c):
    actual_cal, actual_p, actual_f, actual_c = _meal_totals(template["foods"])
    return {
        "meal_number": template["meal_number"],
        "meal_slot": template["meal_slot"],
        "distribution_percentage": None,
        "target_calories": round(target_cal, 1),
        "actual_calories": actual_cal,
        "calorie_difference": round(actual_cal - target_cal, 1),
        "target_protein_grams": round(target_p, 1),
        "actual_protein_grams": actual_p,
        "protein_difference": round(actual_p - target_p, 1),
        "target_fat_grams": round(target_f, 1),
        "actual_fat_grams": actual_f,
        "fat_difference": round(actual_f - target_f, 1),
        "target_carb_grams": round(target_c, 1),
        "actual_carb_grams": actual_c,
        "carb_difference": round(actual_c - target_c, 1),
        "foods": template["foods"],
        "suitable_meal_types": [template["meal_slot"]],
    }


def _build_diet(created_days_ago, target_cal, weight_at_creation):
    meals = []
    for template, (_, pct) in zip(DIET_MEALS_TEMPLATE, MEAL_DISTRIBUTIONS):
        pct_val = pct
        t_cal = target_cal * pct_val
        local_p = weight_at_creation * 2
        local_f = weight_at_creation * 0.8
        local_c = (target_cal - local_p * 4 - local_f * 9) / 4
        meals.append(_build_meal(template, t_cal, local_p * pct_val, local_f * pct_val, local_c * pct_val))

    created_at = datetime.now(UTC) - timedelta(days=created_days_ago)
    local_p = round(weight_at_creation * 2, 1)
    local_f = round(weight_at_creation * 0.8, 1)
    local_c = round((target_cal - local_p * 4 - local_f * 9) / 4, 1)
    return {
        "user_id": USER_ID,
        "created_at": created_at,
        "target_calories": round(target_cal, 1),
        "protein_grams": local_p,
        "fat_grams": local_f,
        "carb_grams": local_c,
        "meals_count": len(meals),
        "meals": meals,
    }


def seed(db):
    print("Limpiando datos anteriores del usuario...")
    db.diets.delete_many({"user_id": USER_ID})
    db.diet_adherence.delete_many({"user_id": USER_ID})
    db.weight_logs.delete_many({"user_id": USER_ID})
    db.calorie_adjustments.delete_many({"user_id": USER_ID})

    # ── Actualizar perfil del usuario ──────────────────────────────────────────
    print("Actualizando perfil del usuario...")
    db.users.update_one(
        {"_id": USER_ID},
        {"$set": {
            "age": 25,
            "sex": "Masculino",
            "height": 180.0,
            "current_weight": CURRENT_WEIGHT,
            "training_days_per_week": 4,
            "goal": "ganar_masa",
            "target_calories": TARGET_CALORIES,
        }},
        upsert=False,
    )

    # ── Dietas ─────────────────────────────────────────────────────────────────
    print("Insertando dietas...")
    diet1 = _build_diet(21, TARGET_CALORIES, 75.0)
    diet2 = _build_diet(14, TARGET_CALORIES + 50, 75.3)
    diet3 = _build_diet(7, TARGET_CALORIES + 100, 75.6)

    res1 = db.diets.insert_one(diet1)
    res2 = db.diets.insert_one(diet2)
    res3 = db.diets.insert_one(diet3)
    diet_ids = [res1.inserted_id, res2.inserted_id, res3.inserted_id]
    print(f"  Dietas insertadas: {[str(d) for d in diet_ids]}")

    # ── Pesos en ayunas (21 días, tendencia +0.08 kg/sem ≈ +0.011 kg/día) ──────
    print("Insertando registros de peso...")
    weight_logs = []
    base_weight = 74.8
    for day_offset in range(21, -1, -1):
        entry_date = TODAY - timedelta(days=day_offset)
        # Tendencia base + ruido aleatorio determinista
        trend = base_weight + (21 - day_offset) * 0.012
        # Ruido pseudo-aleatorio usando paridad de día
        noise_vals = [0.0, 0.08, -0.05, 0.12, -0.03, 0.07, -0.08, 0.04,
                      0.10, -0.06, 0.05, -0.04, 0.09, -0.02, 0.06, -0.07,
                      0.11, 0.03, -0.05, 0.08, -0.01, 0.06]
        noise = noise_vals[21 - day_offset]
        weight = round(trend + noise, 2)
        weight_logs.append({
            "user_id": USER_ID,
            "weight": weight,
            "date": entry_date.isoformat(),
            "created_at": datetime.combine(entry_date, datetime.min.time()).replace(tzinfo=UTC),
        })
    db.weight_logs.insert_many(weight_logs)
    print(f"  {len(weight_logs)} registros de peso ({weight_logs[0]['weight']} -> {weight_logs[-1]['weight']} kg)")

    # ── Adherencia ─────────────────────────────────────────────────────────────
    print("Insertando adherencia...")
    adherence_docs = []
    diet_id_by_range = [
        (21, 14, diet_ids[0]),
        (14, 7, diet_ids[1]),
        (7, 0, diet_ids[2]),
    ]

    for start_days_ago, end_days_ago, diet_id in diet_id_by_range:
        for day_offset in range(start_days_ago - 1, end_days_ago - 1, -1):
            entry_date = TODAY - timedelta(days=day_offset)
            for meal_template, (_, pct) in zip(DIET_MEALS_TEMPLATE, MEAL_DISTRIBUTIONS):
                # Omit snacks occasionally (slot 3), otherwise complete
                if meal_template["meal_number"] == 3 and day_offset % 7 == 0:
                    status = "omitted"
                    adherence_score = 0.0
                elif meal_template["meal_number"] == 2 and day_offset % 11 == 0:
                    status = "modified"
                    adherence_score = 0.6
                else:
                    status = "completed"
                    adherence_score = 1.0

                adherence_docs.append({
                    "user_id": USER_ID,
                    "diet_id": diet_id,
                    "date": entry_date.isoformat(),
                    "meal_number": meal_template["meal_number"],
                    "meal_slot": meal_template["meal_slot"],
                    "status": status,
                    "adherence_score": adherence_score,
                    "created_at": datetime.combine(entry_date, datetime.min.time()).replace(tzinfo=UTC),
                })

    db.diet_adherence.insert_many(adherence_docs)
    completed = sum(1 for a in adherence_docs if a["status"] == "completed")
    print(f"  {len(adherence_docs)} registros de adherencia ({completed} completados)")

    # ── Ajustes calóricos ──────────────────────────────────────────────────────
    print("Insertando ajustes calóricos...")

    # Semana 1: en ruta (0 kcal de cambio)
    week1_start = TODAY - timedelta(days=21)
    iso1 = week1_start.isocalendar()
    week1_label = f"{iso1.year}-W{iso1.week:02d}"

    week2_start = TODAY - timedelta(days=14)
    iso2 = week2_start.isocalendar()
    week2_label = f"{iso2.year}-W{iso2.week:02d}"

    week3_start = TODAY - timedelta(days=7)
    iso3 = week3_start.isocalendar()
    week3_label = f"{iso3.year}-W{iso3.week:02d}"

    week4_iso = TODAY.isocalendar()
    week4_label = f"{week4_iso.year}-W{week4_iso.week:02d}"

    adj1 = {
        "user_id": USER_ID,
        "previous_week_label": week1_label,
        "current_week_label": week2_label,
        "previous_week_avg": 74.95,
        "current_week_avg": 75.06,
        "weekly_change": 0.11,
        "goal": "ganar_masa",
        "progress_status": "on_track",
        "adjustment_needed": False,
        "adjustment_applied": True,
        "calorie_change": 0,
        "previous_target_calories": TARGET_CALORIES,
        "new_target_calories": TARGET_CALORIES,
        "current_weight": 75.0,
        "adjustment_reason": "Progreso dentro del rango objetivo.",
        "reason": "Ganando 0.11 kg/semana (objetivo: ~0.10). Plan en ruta.",
        "created_at": datetime.now(UTC) - timedelta(days=14),
    }

    adj2 = {
        "user_id": USER_ID,
        "previous_week_label": week2_label,
        "current_week_label": week3_label,
        "previous_week_avg": 75.06,
        "current_week_avg": 75.14,
        "weekly_change": 0.08,
        "goal": "ganar_masa",
        "progress_status": "on_track",
        "adjustment_needed": False,
        "adjustment_applied": True,
        "calorie_change": 50,
        "previous_target_calories": TARGET_CALORIES,
        "new_target_calories": TARGET_CALORIES + 50,
        "current_weight": 75.2,
        "adjustment_reason": "Ganancia ligeramente por debajo del objetivo. Incremento moderado.",
        "reason": "Ganando 0.08 kg/semana (objetivo: ~0.10). Ajuste +50 kcal.",
        "created_at": datetime.now(UTC) - timedelta(days=7),
    }

    adj3 = {
        "user_id": USER_ID,
        "previous_week_label": week3_label,
        "current_week_label": week4_label,
        "previous_week_avg": 75.14,
        "current_week_avg": 75.28,
        "weekly_change": 0.14,
        "goal": "ganar_masa",
        "progress_status": "on_track",
        "adjustment_needed": False,
        "adjustment_applied": True,
        "calorie_change": 0,
        "previous_target_calories": TARGET_CALORIES + 50,
        "new_target_calories": TARGET_CALORIES + 50,
        "current_weight": 75.4,
        "adjustment_reason": "Progreso dentro del rango objetivo.",
        "reason": "Ganando 0.14 kg/semana (objetivo: ~0.10). Ligero exceso, pero dentro del margen.",
        "created_at": datetime.now(UTC) - timedelta(days=1),
    }

    db.calorie_adjustments.insert_many([adj1, adj2, adj3])
    print("  3 ajustes calóricos insertados")

    # Actualizar target_calories al valor más reciente
    db.users.update_one(
        {"_id": USER_ID},
        {"$set": {"target_calories": TARGET_CALORIES + 50}},
    )
    print(f"  target_calories actualizado a {TARGET_CALORIES + 50} kcal")

    print("\nResumen final:")
    print(f"  Dietas:     {db.diets.count_documents({'user_id': USER_ID})}")
    print(f"  Adherencia: {db.diet_adherence.count_documents({'user_id': USER_ID})}")
    print(f"  Pesos:      {db.weight_logs.count_documents({'user_id': USER_ID})}")
    print(f"  Ajustes:    {db.calorie_adjustments.count_documents({'user_id': USER_ID})}")


if __name__ == "__main__":
    print("Conectando a MongoDB...")
    db = get_database()
    db.command("ping")
    print("Conexion OK.\n")
    seed(db)
    print("\nSeed completado.")
