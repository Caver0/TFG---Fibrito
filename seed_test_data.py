"""
Script de seed de datos de prueba para el usuario 69e0b677614cd669c879c8dc.
Objetivo: ganar_masa | Calorías objetivo: ~2612 kcal
Peso: 72 kg | Proteína: 144g | Grasa: 57.6g | Carbos: 379.5g
"""
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from pymongo import MongoClient

USER_ID = ObjectId("69e0b677614cd669c879c8dc")
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "fibrito"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

def d(days_ago: int) -> datetime:
    return TODAY - timedelta(days=days_ago)

def ds(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).strftime("%Y-%m-%d")

def iso_week(days_ago: int) -> str:
    dt = TODAY - timedelta(days=days_ago)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

# ─────────────────────────────────────────────
# Limpiar datos anteriores del usuario de prueba
# ─────────────────────────────────────────────
print("Limpiando datos anteriores del usuario de prueba...")
db.diets.delete_many({"user_id": USER_ID})
db.diet_adherence.delete_many({"user_id": USER_ID})
db.weight_logs.delete_many({"user_id": USER_ID})
db.calorie_adjustments.delete_many({"user_id": USER_ID})
print("Limpieza completada.")

# ─────────────────────────────────────────────
# DIETAS (3 dietas realistas para ganar_masa)
# ─────────────────────────────────────────────
# Macro objetivo: 2612 kcal | P:144g | F:57.6g | C:379.5g
# 4 comidas: 25% / 30% / 30% / 15%

def build_meal(meal_num: int, pct: float, total_cal: float, total_p: float, total_f: float, total_c: float, foods: list):
    t_cal = round(total_cal * pct, 1)
    t_p   = round(total_p * pct, 1)
    t_f   = round(total_f * pct, 1)
    t_c   = round(total_c * pct, 1)

    a_cal = round(sum(fo["calories"] for fo in foods), 1)
    a_p   = round(sum(fo["protein_grams"] for fo in foods), 1)
    a_f   = round(sum(fo["fat_grams"] for fo in foods), 1)
    a_c   = round(sum(fo["carb_grams"] for fo in foods), 1)

    return {
        "meal_number": meal_num,
        "distribution_percentage": round(pct * 100, 1),
        "target_calories": t_cal,
        "target_protein_grams": t_p,
        "target_fat_grams": t_f,
        "target_carb_grams": t_c,
        "actual_calories": a_cal,
        "actual_protein_grams": a_p,
        "actual_fat_grams": a_f,
        "actual_carb_grams": a_c,
        "calorie_difference": round(a_cal - t_cal, 1),
        "protein_difference": round(a_p - t_p, 1),
        "fat_difference": round(a_f - t_f, 1),
        "carb_difference": round(a_c - t_c, 1),
        "foods": foods,
    }

def make_food(name, category, quantity, unit, grams, cal, p, f, c, code=None):
    return {
        "food_code": code,
        "source": "internal",
        "origin_source": "internal",
        "spoonacular_id": None,
        "name": name,
        "category": category,
        "quantity": quantity,
        "unit": unit,
        "grams": grams,
        "calories": cal,
        "protein_grams": p,
        "fat_grams": f,
        "carb_grams": c,
    }

def build_diet(created_days_ago: int, diet_num: int) -> dict:
    # Ligeras variaciones entre dietas para realismo
    offset = (diet_num - 1) * 12  # pequeña variación calórica por dieta

    total_cal = round(2612.2 + offset, 1)
    total_p   = 144.0
    total_f   = 57.6
    total_c   = round((total_cal - total_p * 4 - total_f * 9) / 4, 1)

    # Comida 1 (desayuno 25%)
    meal1_foods = [
        make_food("Avena",           "cereales",   80,  "g",   80,  304.0, 12.4,  5.6, 52.0, "AV001"),
        make_food("Leche semidesnat","lácteos",   250, "ml",  258,  115.0,  8.5,  4.0, 12.0, "LE002"),
        make_food("Plátano",         "fruta",       1,  "unidad", 120,  107.0,  1.3,  0.4, 27.0, "FR005"),
    ]
    # Comida 2 (almuerzo 30%)
    meal2_foods = [
        make_food("Pechuga de pollo","carne",     200,  "g",  200,  330.0, 62.0,  7.2,  0.0, "CA001"),
        make_food("Arroz blanco coc.","cereales", 200,  "g",  200,  260.0,  4.8,  0.6, 56.4, "AR001"),
        make_food("Aceite de oliva", "grasas",     10,  "ml",   9,   90.0,  0.0, 10.0,  0.0, "GR001"),
        make_food("Brócoli hervido", "verdura",   150,  "g",  150,   51.0,  5.4,  0.6,  6.6, "VE003"),
    ]
    # Comida 3 (merienda/post-entreno 30%)
    meal3_foods = [
        make_food("Salmón al horno", "pescado",   180,  "g",  180,  374.4, 38.0, 24.0,  0.0, "PE001"),
        make_food("Patata cocida",   "verdura",   250,  "g",  250,  213.0,  5.0,  0.3, 48.5, "VE010"),
        make_food("Espinacas crudas","verdura",    80,  "g",   80,   18.4,  2.3,  0.3,  2.9, "VE008"),
    ]
    # Comida 4 (cena 15%)
    meal4_foods = [
        make_food("Huevos enteros",  "lácteos",    3, "unidad", 180,  225.0, 18.9, 15.6,  1.5, "HU001"),
        make_food("Pan integral",    "cereales",   60,  "g",   60,  159.0,  6.0,  1.8, 30.0, "PA002"),
        make_food("Queso fresco",    "lácteos",    50,  "g",   50,   60.0,  7.5,  2.5,  2.5, "LA005"),
    ]

    meals = [
        build_meal(1, 0.25, total_cal, total_p, total_f, total_c, meal1_foods),
        build_meal(2, 0.30, total_cal, total_p, total_f, total_c, meal2_foods),
        build_meal(3, 0.30, total_cal, total_p, total_f, total_c, meal3_foods),
        build_meal(4, 0.15, total_cal, total_p, total_f, total_c, meal4_foods),
    ]

    a_cal = round(sum(m["actual_calories"] for m in meals), 1)
    a_p   = round(sum(m["actual_protein_grams"] for m in meals), 1)
    a_f   = round(sum(m["actual_fat_grams"] for m in meals), 1)
    a_c   = round(sum(m["actual_carb_grams"] for m in meals), 1)

    fu_summary = {}
    for m in meals:
        for fo in m["foods"]:
            fu_summary[fo["name"]] = fu_summary.get(fo["name"], 0) + 1

    return {
        "user_id": USER_ID,
        "created_at": d(created_days_ago),
        "meals_count": 4,
        "target_calories": total_cal,
        "protein_grams": total_p,
        "fat_grams": total_f,
        "carb_grams": total_c,
        "actual_calories": a_cal,
        "actual_protein_grams": a_p,
        "actual_fat_grams": a_f,
        "actual_carb_grams": a_c,
        "calorie_difference": round(a_cal - total_cal, 1),
        "protein_difference": round(a_p - total_p, 1),
        "fat_difference": round(a_f - total_f, 1),
        "carb_difference": round(a_c - total_c, 1),
        "distribution_percentages": [25.0, 30.0, 30.0, 15.0],
        "training_time_of_day": "tarde",
        "training_optimization_applied": True,
        "food_data_source": "internal",
        "food_data_sources": ["internal"],
        "food_catalog_version": "1.0",
        "food_preferences_applied": False,
        "applied_dietary_restrictions": [],
        "applied_allergies": [],
        "preferred_food_matches": 0,
        "diversity_strategy_applied": True,
        "food_usage_summary": fu_summary,
        "food_filter_warnings": [],
        "catalog_source_strategy": "internal_catalog_with_optional_spoonacular_enrichment",
        "spoonacular_attempted": False,
        "spoonacular_attempts": 0,
        "spoonacular_hits": 0,
        "cache_hits": 0,
        "internal_fallbacks": 0,
        "resolved_foods_count": sum(len(m["foods"]) for m in meals),
        "meals": meals,
    }

# Insertar 3 dietas: hace 14 días, hace 7 días, ayer
diet_docs = [
    build_diet(14, 1),
    build_diet(7,  2),
    build_diet(1,  3),
]

diet_ids = db.diets.insert_many(diet_docs).inserted_ids
print(f"Dietas insertadas: {[str(i) for i in diet_ids]}")

# ─────────────────────────────────────────────
# WEIGHT LOGS (pesos en ayunas — tendencia alcista coherente con ganar_masa)
# 72.0 kg base → ligero aumento hasta ~72.6 kg en 2 semanas
# ─────────────────────────────────────────────
weight_series = [
    # Semana 1 (hace 14-8 días)
    (14, 71.8), (13, 71.9), (12, 72.0), (11, 72.1), (10, 72.0), (9, 72.2), (8, 72.1),
    # Semana 2 (hace 7-1 días)
    (7,  72.2), (6,  72.3), (5,  72.2), (4,  72.4), (3,  72.3), (2,  72.5), (1, 72.4),
]

weight_docs = [
    {
        "user_id": USER_ID,
        "weight": w,
        "date": ds(days_ago),
        "created_at": d(days_ago),
    }
    for days_ago, w in weight_series
]

db.weight_logs.insert_many(weight_docs)
print(f"Weight logs insertados: {len(weight_docs)}")

# ─────────────────────────────────────────────
# DIET ADHERENCE
# Dieta 1 (hace 14 días): 7 días, buena adherencia
# Dieta 2 (hace 7 días): 7 días, adherencia mixta
# Dieta 3 (ayer): solo 1 día registrado
# ─────────────────────────────────────────────
adherence_docs = []
now_utc = datetime.now(timezone.utc)

def adh(diet_id, days_ago, meal_num, status, score, note=None):
    return {
        "user_id": USER_ID,
        "diet_id": diet_id,
        "meal_number": meal_num,
        "date": ds(days_ago),
        "status": status,
        "note": note,
        "adherence_score": score,
        "created_at": now_utc,
        "updated_at": now_utc,
    }

# Dieta 1 (diet_ids[0]) — semana hace 14-8 días, 4 comidas/día
for days_back, (s1, s2, s3, s4) in [
    (14, ("completed", "completed", "completed", "completed")),
    (13, ("completed", "completed", "completed", "omitted")),
    (12, ("completed", "completed", "modified", "completed")),
    (11, ("completed", "completed", "completed", "completed")),
    (10, ("completed", "omitted",   "completed", "completed")),
    (9,  ("completed", "completed", "completed", "completed")),
    (8,  ("completed", "completed", "completed", "completed")),
]:
    scores = {"completed": 1.0, "omitted": 0.0, "modified": 0.7, "pending": None}
    for i, (st, sc) in enumerate([(s1, scores[s1]), (s2, scores[s2]), (s3, scores[s3]), (s4, scores[s4])], 1):
        note = "Sustituí el salmón por atún en conserva" if (st == "modified" and i == 3) else None
        adherence_docs.append(adh(diet_ids[0], days_back, i, st, sc, note))

# Dieta 2 (diet_ids[1]) — semana hace 7-1 días, adherencia más baja en mitad de semana
for days_back, (s1, s2, s3, s4) in [
    (7, ("completed", "completed", "completed", "completed")),
    (6, ("completed", "modified",  "completed", "omitted")),
    (5, ("completed", "completed", "omitted",   "completed")),
    (4, ("completed", "completed", "completed", "completed")),
    (3, ("omitted",   "completed", "completed", "completed")),
    (2, ("completed", "completed", "completed", "modified")),
    (1, ("completed", "completed", "completed", "completed")),
]:
    scores = {"completed": 1.0, "omitted": 0.0, "modified": 0.7, "pending": None}
    for i, (st, sc) in enumerate([(s1, scores[s1]), (s2, scores[s2]), (s3, scores[s3]), (s4, scores[s4])], 1):
        note = "Cené fuera, elegí opción saludable" if (st == "modified" and days_back == 2 and i == 4) else None
        adherence_docs.append(adh(diet_ids[1], days_back, i, st, sc, note))

# Dieta 3 (diet_ids[2]) — solo ayer (día 1)
for i, (st, sc) in enumerate([("completed", 1.0), ("completed", 1.0), ("completed", 1.0), ("completed", 1.0)], 1):
    adherence_docs.append(adh(diet_ids[2], 1, i, st, sc))

db.diet_adherence.insert_many(adherence_docs)
print(f"Registros de adherencia insertados: {len(adherence_docs)}")

# ─────────────────────────────────────────────
# CALORIE ADJUSTMENTS (2 análisis semanales del sistema)
# ─────────────────────────────────────────────
# Semana 1 → análisis: ganancia 0.3 kg, en rango para ganar_masa → sin ajuste
# Semana 2 → análisis: ganancia 0.25 kg, ligeramente lenta → +50 kcal
adj_docs = [
    {
        "user_id": USER_ID,
        "created_at": d(7),
        "previous_week_label": iso_week(14),
        "current_week_label": iso_week(7),
        "previous_week_avg": round(sum(w for _, w in weight_series[:7]) / 7, 2),   # ~72.01
        "current_week_avg":  round(sum(w for _, w in weight_series[7:]) / 7, 2),    # ~72.33
        "weekly_change": round(
            sum(w for _, w in weight_series[7:]) / 7 -
            sum(w for _, w in weight_series[:7]) / 7, 2
        ),
        "goal": "ganar_masa",
        "progress_status": "on_track",
        "progress_direction_ok": True,
        "progress_rate_ok": True,
        "adjustment_applied": False,
        "max_weekly_loss": None,
        "calorie_change": 0,
        "previous_target_calories": 2612.2,
        "new_target_calories": 2612.2,
        "adjustment_reason": "Ganancia semanal de 0.32 kg dentro del rango objetivo (0.25–0.50 kg/sem). Sin ajuste necesario.",
        "reason": "Ganancia semanal de 0.32 kg dentro del rango objetivo (0.25–0.50 kg/sem). Sin ajuste necesario.",
    },
    {
        "user_id": USER_ID,
        "created_at": d(0),
        "previous_week_label": iso_week(7),
        "current_week_label": iso_week(0),
        "previous_week_avg": round(sum(w for _, w in weight_series[7:]) / 7, 2),
        "current_week_avg":  round(sum(w for _, w in weight_series[7:]) / 7 + 0.25, 2),
        "weekly_change": 0.25,
        "goal": "ganar_masa",
        "progress_status": "needs_adjustment",
        "progress_direction_ok": True,
        "progress_rate_ok": False,
        "adjustment_applied": True,
        "max_weekly_loss": None,
        "calorie_change": 50,
        "previous_target_calories": 2612.2,
        "new_target_calories": 2662.2,
        "adjustment_reason": "Ganancia semanal de 0.25 kg por debajo del objetivo. Se incrementan 50 kcal para acelerar progreso.",
        "reason": "Ganancia semanal de 0.25 kg por debajo del objetivo. Se incrementan 50 kcal para acelerar progreso.",
    },
]

db.calorie_adjustments.insert_many(adj_docs)
print(f"Ajustes de calorías insertados: {len(adj_docs)}")

# ─────────────────────────────────────────────
# Actualizar target_calories del usuario tras el ajuste
# ─────────────────────────────────────────────
db.users.update_one(
    {"_id": USER_ID},
    {"$set": {"target_calories": 2662.2}}
)
print("target_calories del usuario actualizado a 2662.2 kcal")

print("\n✓ Seed completado con éxito.")
print(f"  Dieta 1 (_id): {diet_ids[0]}")
print(f"  Dieta 2 (_id): {diet_ids[1]}")
print(f"  Dieta 3 (_id): {diet_ids[2]}")
client.close()
