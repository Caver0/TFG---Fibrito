"""
Seed script de datos de prueba completos para Fibrito.

IMPORTANTE: Este script usa los servicios del backend directamente para generar
dietas reales, lo que permite verificar que el backend funciona correctamente:
  - Los macros de las dietas coinciden con los targets del backend
  - Los alimentos preferidos aparecen en las dietas generadas
  - Los ajustes semanales siguen la lógica real del servicio de ajuste

Uso:
    python seed_test_data.py [ObjectId_del_usuario]
    python seed_test_data.py          # usa DEFAULT_USER_ID
"""
import sys
import os
from datetime import datetime, timezone, timedelta

# ── Entorno ANTES de importar el backend ──────────────────────────────────────
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "fibrito")
os.environ.setdefault("JWT_SECRET_KEY", "dev-script-secret")
os.environ.setdefault("SPOONACULAR_API_KEY", "43d0574fa7424afd861f12bbcb9159b6")
os.environ.setdefault("SPOONACULAR_BASE_URL", "https://api.spoonacular.com")
os.environ.setdefault("SPOONACULAR_TIMEOUT_SECONDS", "15")

# ── Path al backend ────────────────────────────────────────────────────────────
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, BACKEND_DIR)

try:
    from bson import ObjectId
    from pymongo import MongoClient
except ImportError:
    print("ERROR: Instala pymongo: pip install pymongo")
    sys.exit(1)

from app.services.diet_service import (
    generate_daily_diet,
    _build_persistable_diet_fields,
)
from app.services.goal_adjustment_service import calculate_calorie_adjustment
from app.schemas.user import UserPublic, FoodPreferencesProfile

# ── Configuración ──────────────────────────────────────────────────────────────
MONGO_URL = "mongodb://localhost:27017"
DB_NAME   = "fibrito"

DEFAULT_USER_ID = "69e21966e1880adf53eee270"

# ── Perfil del usuario de prueba ───────────────────────────────────────────────
# Hombre, 27 años, 178 cm, 78 kg, objetivo: perder_grasa, 4 días/semana
# BMR  ≈ 10*78 + 6.25*178 - 5*27 + 5 = 1762.5
# TDEE ≈ 1762.5 * 1.55 = 2731.9 → déficit ~15% → 2322 kcal objetivo
PROFILE = {
    "name":                   "Test Fibrito",
    "email":                  "test@example.com",
    "age":                    27,
    "sex":                    "Masculino",
    "height":                 178.0,
    "current_weight":         78.0,
    "training_days_per_week": 4,
    "goal":                   "perder_grasa",
    "target_calories":        2322.0,
    "food_preferences": {
        "preferred_foods":       ["salmon", "avocado", "quinoa", "greek yogurt", "almonds"],
        "disliked_foods":        ["tofu", "kale"],
        "dietary_restrictions":  [],
        "allergies":             [],
    },
}

INITIAL_WEIGHT = 80.2   # kg hace 42 días
NUM_DAYS       = 42     # 6 semanas completas
TODAY = datetime.now(timezone.utc).replace(hour=7, minute=0, second=0, microsecond=0)

# ── Ruido diario para la serie de pesos ───────────────────────────────────────
# La semana 3 (índices 14-20) tiene ruido positivo alto para simular una semana
# de estancamiento (pérdida < 0.3 kg/sem), lo que debería disparar un ajuste -100 kcal.
NOISE = [
    # Semana 1 (i=0-6): normal
     0.00,  0.10, -0.08,  0.12, -0.04,  0.06, -0.10,
    # Semana 2 (i=7-13): normal
     0.08, -0.06,  0.14, -0.03,  0.09, -0.12,  0.05,
    # Semana 3 (i=14-20): estancamiento (ruido positivo = peso más alto = menos pérdida aparente)
     0.25,  0.30,  0.28,  0.32,  0.27,  0.29,  0.26,
    # Semana 4 (i=21-27): vuelta a normal
     0.04, -0.11,  0.07, -0.06,  0.10, -0.04,  0.08,
    # Semana 5 (i=28-34): normal
    -0.13,  0.06, -0.07,  0.11, -0.03,  0.09, -0.05,
    # Semana 6 (i=35-41): normal
     0.07, -0.08,  0.12, -0.04,  0.05, -0.09,  0.03,
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def dt(days_ago: int) -> datetime:
    return TODAY - timedelta(days=days_ago)

def ds(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).date().isoformat()

def iso_week_label(days_ago: int) -> str:
    d = (TODAY - timedelta(days=days_ago)).date()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Serie de pesos
# ─────────────────────────────────────────────────────────────────────────────
def generate_weight_series():
    """
    42 días de tendencia descendente 80.2 → 78.0 kg con ruido controlado.
    La semana 3 tiene ruido positivo para simular un estancamiento.
    """
    final_weight  = INITIAL_WEIGHT - 2.2  # objetivo final
    daily_trend   = (final_weight - INITIAL_WEIGHT) / NUM_DAYS
    entries = []
    for i in range(NUM_DAYS):
        days_ago = NUM_DAYS - i   # de más antiguo (42) a más reciente (1)
        weight   = round(INITIAL_WEIGHT + daily_trend * i + NOISE[i], 2)
        entries.append((days_ago, weight))
    return entries


def build_weekly_averages(weight_series):
    """Agrupa la serie en semanas de 7 días. Retorna lista de medias."""
    weeks = []
    for week_idx in range(NUM_DAYS // 7):
        start = week_idx * 7
        week_weights = [w for _, w in weight_series[start : start + 7]]
        weeks.append(round(sum(week_weights) / len(week_weights), 2))
    return weeks


# ─────────────────────────────────────────────────────────────────────────────
# Ajustes semanales — usa el servicio real del backend
# ─────────────────────────────────────────────────────────────────────────────
def build_adjustments(user_id, weight_series):
    """
    Genera ajustes semanales usando calculate_calorie_adjustment del backend.
    Garantiza que los datos del seed son 100% coherentes con la lógica real.

    Devuelve (adjustments_list, cal_checkpoints) donde cal_checkpoints[i] es
    el target calórico TRAS haber aplicado los i primeros ajustes.
    """
    weeks = build_weekly_averages(weight_series)
    adjustments    = []
    running_cal    = PROFILE["target_calories"]
    cal_checkpoints = [running_cal]   # índice 0 = valor inicial antes de cualquier ajuste

    for i in range(1, len(weeks)):
        weekly_change = round(weeks[i] - weeks[i - 1], 2)

        decision = calculate_calorie_adjustment(
            goal           = "perder_grasa",
            weekly_change  = weekly_change,
            current_weight = weeks[i],
        )

        prev_cal    = running_cal
        running_cal = round(running_cal + decision["calorie_change"], 1)
        cal_checkpoints.append(running_cal)

        adj = {
            "user_id":               user_id,
            "created_at":            dt(NUM_DAYS - i * 7),
            "previous_week_label":   iso_week_label(NUM_DAYS - (i - 1) * 7),
            "current_week_label":    iso_week_label(NUM_DAYS - i * 7),
            "previous_week_avg":     weeks[i - 1],
            "current_week_avg":      weeks[i],
            "weekly_change":         weekly_change,
            "goal":                  "perder_grasa",
            "progress_status":       decision["progress_status"],
            "progress_direction_ok": decision["progress_direction_ok"],
            "progress_rate_ok":      decision["progress_rate_ok"],
            "adjustment_applied":    decision["adjustment_needed"],
            "max_weekly_loss":       decision.get("max_weekly_loss"),
            "calorie_change":        decision["calorie_change"],
            "previous_target_calories": prev_cal,
            "new_target_calories":      running_cal,
            "adjustment_reason":     decision["adjustment_reason"],
            "reason":                decision["adjustment_reason"],
            "current_weight":        weeks[i],
        }
        adjustments.append(adj)

    return adjustments, cal_checkpoints


# ─────────────────────────────────────────────────────────────────────────────
# Generación de dietas — usa el servicio real del backend
# ─────────────────────────────────────────────────────────────────────────────
def make_user_public(db, user_id_str: str, target_calories: float) -> UserPublic:
    """
    Construye un objeto UserPublic para el servicio de generación de dietas.
    Lee los campos nutricionales desde la BD pero usa siempre un email válido
    para evitar fallos de validación Pydantic con emails de cuentas reales.
    """
    doc = db.users.find_one({"_id": ObjectId(user_id_str)}) or {}

    # Leer food_preferences desde la BD (ya actualizadas por el seed)
    fp_raw = doc.get("food_preferences", {})
    food_prefs = FoodPreferencesProfile(
        preferred_foods      = fp_raw.get("preferred_foods",      PROFILE["food_preferences"]["preferred_foods"]),
        disliked_foods       = fp_raw.get("disliked_foods",       PROFILE["food_preferences"]["disliked_foods"]),
        dietary_restrictions = fp_raw.get("dietary_restrictions", []),
        allergies            = fp_raw.get("allergies",            []),
    )

    return UserPublic(
        id           = user_id_str,
        # Usar nombre y email del PROFILE (válido); generate_daily_diet no los necesita
        name         = PROFILE["name"],
        email        = PROFILE["email"],
        created_at   = doc.get("created_at", datetime.now(timezone.utc)),
        age          = doc.get("age",                    PROFILE["age"]),
        sex          = doc.get("sex",                    PROFILE["sex"]),
        height       = doc.get("height",                 PROFILE["height"]),
        current_weight         = doc.get("current_weight",         PROFILE["current_weight"]),
        training_days_per_week = doc.get("training_days_per_week", PROFILE["training_days_per_week"]),
        goal             = doc.get("goal",    PROFILE["goal"]),
        target_calories  = target_calories,
        food_preferences = food_prefs,
    )


def generate_and_insert_diet(
    db,
    user_id: ObjectId,
    user_id_str: str,
    target_calories: float,
    days_ago: int,
) -> ObjectId:
    """
    Genera una dieta real usando el backend y la inserta backdateada en MongoDB.
    Esto permite verificar que el backend:
      1. Produce macros correctos para el target calórico dado
      2. Incluye los alimentos preferidos del usuario
      3. Excluye los alimentos no deseados
    """
    user = make_user_public(db, user_id_str, target_calories)
    print(f"  Generando dieta ({target_calories:.0f} kcal, hace {days_ago} días)...", end=" ", flush=True)

    diet_payload = generate_daily_diet(db, user, meals_count=4)

    diet_document = {
        "user_id":    user_id,
        "created_at": dt(days_ago),
        **_build_persistable_diet_fields(diet_payload),
    }
    result = db.diets.insert_one(diet_document)

    a_cal  = diet_payload.get("actual_calories", 0)
    t_cal  = diet_payload.get("target_calories", 0)
    a_p    = diet_payload.get("actual_protein_grams", 0)
    a_f    = diet_payload.get("actual_fat_grams", 0)
    a_c    = diet_payload.get("actual_carb_grams", 0)
    pref   = diet_payload.get("preferred_food_matches", 0)
    print(
        f"OK → actual {a_cal:.0f}/{t_cal:.0f} kcal | "
        f"P:{a_p:.1f}g G:{a_f:.1f}g H:{a_c:.1f}g | "
        f"alim.preferidos={pref}"
    )
    return result.inserted_id


# ─────────────────────────────────────────────────────────────────────────────
# Adherencia
# ─────────────────────────────────────────────────────────────────────────────
def build_adherence(user_id, diet_id_map: dict) -> list:
    """
    Genera registros de adherencia diaria por comida (~85% global).
    Patrón: L-J completados, V modificado, S omitido, D completado.
    """
    docs = []
    now  = datetime.now(timezone.utc)

    # Patrón por día de la semana (weekday 0=Lun…6=Dom)
    weekday_pattern = {
        0: ("completed", 1.00),
        1: ("completed", 1.00),
        2: ("completed", 1.00),
        3: ("completed", 1.00),
        4: ("modified",  0.75),
        5: ("omitted",   0.00),
        6: ("completed", 1.00),
    }

    for diet_days_ago, diet_id in sorted(diet_id_map.items(), reverse=True):
        for day_offset in range(14):
            record_days_ago = diet_days_ago - 1 - day_offset
            if record_days_ago < 0:
                break
            record_date = (TODAY - timedelta(days=record_days_ago)).date()
            weekday     = record_date.weekday()

            for meal_num in range(1, 5):
                base_status, base_score = weekday_pattern[weekday]
                # La comida 3 se omite también en sábado y viernes tarde
                if meal_num == 3 and weekday in (4, 5):
                    status, score = "omitted", 0.0
                elif meal_num == 2 and weekday == 6:
                    status, score = "modified", 0.65
                else:
                    status, score = base_status, base_score

                docs.append({
                    "user_id":        user_id,
                    "diet_id":        diet_id,
                    "meal_number":    meal_num,
                    "date":           record_date.isoformat(),
                    "status":         status,
                    "adherence_score": score,
                    "note":           None,
                    "created_at":     now,
                    "updated_at":     now,
                })
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# SEED PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
def seed(db, user_id_str: str):
    user_id = ObjectId(user_id_str)
    print(f"\nUsuario objetivo: {user_id}")

    # ── Verificar / crear usuario ─────────────────────────────────────────────
    existing = db.users.find_one({"_id": user_id})
    if not existing:
        print("  AVISO: usuario no encontrado. Creando perfil de prueba...")
        db.users.insert_one({
            "_id":             user_id,
            "hashed_password": "SEED_ONLY_NO_AUTH",
            **PROFILE,
        })
    else:
        print(f"  Usuario encontrado: {existing.get('email', '—')}")

    # ── Limpiar datos anteriores ──────────────────────────────────────────────
    print("\nLimpiando datos anteriores...")
    for col in ("diets", "diet_adherence", "weight_logs", "calorie_adjustments"):
        n = db[col].delete_many({"user_id": user_id}).deleted_count
        print(f"  {col}: {n} documentos eliminados")

    # ── Actualizar perfil ─────────────────────────────────────────────────────
    # No sobreescribir name/email si el usuario ya existe
    profile_update = {k: v for k, v in PROFILE.items() if k not in ("name", "email")}
    db.users.update_one({"_id": user_id}, {"$set": profile_update}, upsert=True)
    print("\nPerfil actualizado con preferencias alimentarias.")

    # ── Pesos en ayunas ────────────────────────────────────────────────────────
    print(f"\nInsertando {NUM_DAYS} registros de peso en ayunas...")
    weight_series = generate_weight_series()
    db.weight_logs.insert_many([
        {
            "user_id":    user_id,
            "weight":     w,
            "date":       ds(days_ago),
            "created_at": dt(days_ago),
        }
        for days_ago, w in weight_series
    ])
    print(f"  {weight_series[0][1]} kg (hace {NUM_DAYS}d) → {weight_series[-1][1]} kg (ayer)")

    # ── Ajustes calóricos (backend real) ──────────────────────────────────────
    print("\nCalculando ajustes semanales con el servicio del backend...")
    adjustments, cal_checkpoints = build_adjustments(user_id, weight_series)

    if adjustments:
        db.calorie_adjustments.insert_many(adjustments)

    print(f"  {'Semana':<14} {'Cambio':>8}  {'Estado':<20} {'Δ kcal':>8}  {'Nuevo target':>12}")
    print(f"  {'-'*14} {'-'*8}  {'-'*20} {'-'*8}  {'-'*12}")
    for adj in adjustments:
        sign = "+" if adj["weekly_change"] >= 0 else ""
        print(
            f"  {adj['current_week_label']:<14} "
            f"{sign}{adj['weekly_change']:.2f} kg  "
            f"{adj['progress_status']:<20} "
            f"{adj['calorie_change']:>+8.0f}  "
            f"{adj['new_target_calories']:>11.0f} kcal"
        )

    final_cal = cal_checkpoints[-1]
    db.users.update_one({"_id": user_id}, {"$set": {"target_calories": final_cal}})
    print(f"\n  target_calories actualizado a {final_cal:.0f} kcal")

    # ── Dietas (generadas por el backend) ─────────────────────────────────────
    # Se usan 3 puntos temporales con el target calórico vigente en ese momento.
    # Esto permite verificar que las macros y los alimentos preferidos son correctos.
    print("\nGenerando dietas con el backend real...")

    # cal_checkpoints[0] = target inicial (antes de cualquier ajuste)
    # cal_checkpoints[2] = target tras 2 ajustes (semana 3 ajustada)
    # cal_checkpoints[-1] = target más reciente
    n_check = len(cal_checkpoints)
    diet_configs = [
        (42, cal_checkpoints[0]),
        (28, cal_checkpoints[min(2, n_check - 1)]),
        (14, cal_checkpoints[min(4, n_check - 1)]),
    ]

    diet_id_map = {}
    for days_ago, kcal in diet_configs:
        diet_id = generate_and_insert_diet(db, user_id, user_id_str, kcal, days_ago)
        diet_id_map[days_ago] = diet_id

    # ── Adherencia ─────────────────────────────────────────────────────────────
    print("\nInsertando registros de adherencia...")
    adherence_docs = build_adherence(user_id, diet_id_map)
    if adherence_docs:
        db.diet_adherence.insert_many(adherence_docs)
    completed = sum(1 for a in adherence_docs if a["status"] == "completed")
    modified  = sum(1 for a in adherence_docs if a["status"] == "modified")
    omitted   = sum(1 for a in adherence_docs if a["status"] == "omitted")
    print(f"  {len(adherence_docs)} registros: completados={completed} modificados={modified} omitidos={omitted}")

    # ── Resumen final ──────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("RESUMEN FINAL")
    print(f"  Pesos:      {db.weight_logs.count_documents({'user_id': user_id})}")
    print(f"  Dietas:     {db.diets.count_documents({'user_id': user_id})}")
    print(f"  Ajustes:    {db.calorie_adjustments.count_documents({'user_id': user_id})}")
    print(f"  Adherencia: {db.diet_adherence.count_documents({'user_id': user_id})}")
    print("\nAlimentos preferidos:")
    for f in PROFILE["food_preferences"]["preferred_foods"]:
        print(f"  + {f}")
    print("Alimentos no deseados:")
    for f in PROFILE["food_preferences"]["disliked_foods"]:
        print(f"  - {f}")
    print("\nQué verificar en la UI:")
    print("  • Gráfica de peso: tendencia descendente, estancamiento en semana 3")
    print("  • Historial de ajustes: semana 3 debe mostrar -100 kcal por pérdida lenta")
    print("  • Dietas: macros generados por el backend (comparar G real vs target ~62g)")
    print("  • Dietas: alimentos preferidos (salmón, aguacate, quinoa, yogur, almendras)")
    print("  • Dietas: sin tofu ni kale (alimentos no deseados)")
    print("  • Adherencia: ~85% semanal, caídas en fin de semana")


if __name__ == "__main__":
    user_id_arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USER_ID

    print("Conectando a MongoDB...")
    client = MongoClient(MONGO_URL)
    db     = client[DB_NAME]
    db.command("ping")
    print("Conexion OK.")

    seed(db, user_id_arg)
    client.close()
    print("\nSeed completado.")
