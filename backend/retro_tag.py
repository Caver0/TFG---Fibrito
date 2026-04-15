"""Etiquetado retroactivo de alimentos sin suitable_meals en MongoDB.

Etiqueta todos los alimentos de Spoonacular que no tienen suitable_meals
usando el sistema hibrido (KNN + reglas de categoria + macro dominante).
Al finalizar, invalida el cache del modelo y lo reentrena con los nuevos datos.
"""

import os
import sys

os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
os.environ.setdefault("MONGO_DB_NAME", "fibrito")
os.environ.setdefault("JWT_SECRET_KEY", "dev-script-secret")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import get_database
from app.services.food_classifier_service import (
    CATEGORY_MEAL_RULES,
    invalidate_model_cache,
    load_or_train_classifier,
    predict_suitable_meals,
)


def retro_tag_all(db) -> int:
    """Etiqueta los alimentos sin suitable_meals. Devuelve el numero de alimentos actualizados."""
    cursor = db.foods_catalog.find(
        {
            "source": "spoonacular",
            "$or": [
                {"suitable_meals": {"$exists": False}},
                {"suitable_meals": {"$size": 0}},
            ],
        }
    )

    updated = 0
    for food in cursor:
        predicted = predict_suitable_meals(food)
        db.foods_catalog.update_one(
            {"_id": food["_id"]},
            {"$set": {"suitable_meals": predicted}},
        )
        print(f"  [{food.get('name', food['_id'])}]  ->  {predicted}")
        updated += 1

    return updated


def retro_fix_suspicious(db) -> int:
    """Corrige alimentos Spoonacular con clasificaciones claramente incorrectas.

    Solo actua sobre frutas y cereales etiquetados como 'main' sin 'early',
    lo cual es semanticamente imposible (una fruta o cereal de desayuno no es
    una comida principal). No modifica datos de entrenamiento (spoonacular_id < 0).
    """
    # Frutas y cereales son los unicas categorias donde "main sin early" es siempre un error
    target_categories = ["frutas", "cereales"]

    cursor = db.foods_catalog.find({
        "category": {"$in": target_categories},
        # Solo alimentos reales de Spoonacular (spoonacular_id >= 0), no datos de entrenamiento
        "$or": [
            {"spoonacular_id": {"$gte": 0}},
            {"spoonacular_id": {"$exists": False}},
        ],
    })

    fixed = 0
    for food in cursor:
        meals = food.get("suitable_meals", [])
        category = food.get("category", "")

        if "main" in meals and "early" not in meals:
            correct_slots = CATEGORY_MEAL_RULES.get(category, ["early", "snack"])
            db.foods_catalog.update_one(
                {"_id": food["_id"]},
                {"$set": {"suitable_meals": correct_slots}},
            )
            print(f"  FIXED [{food.get('name', food['_id'])}]  {meals}  ->  {correct_slots}")
            fixed += 1

    return fixed


if __name__ == "__main__":
    db = get_database()

    # Siempre invalidar cache para reentrenar con los datos actuales de MongoDB
    print("[Retro-Tagger] Invalidando cache del modelo para forzar reentrenamiento...")
    invalidate_model_cache()

    print("[Retro-Tagger] Entrenando modelo con datos actuales de MongoDB...")
    success = load_or_train_classifier(db)
    if success:
        print("[Retro-Tagger] Modelo entrenado correctamente.")
    else:
        print("[Retro-Tagger] Entrenamiento fallido: datos insuficientes.")

    print("\n[Retro-Tagger] Etiquetando alimentos sin clasificar...")
    count = retro_tag_all(db)

    if count == 0:
        print("  -> Ningun alimento sin etiquetar encontrado.")
    else:
        print(f"\n[Retro-Tagger] {count} alimentos etiquetados.")
        print("[Retro-Tagger] Reentrenando modelo con los nuevos datos etiquetados...")
        invalidate_model_cache()
        success = load_or_train_classifier(db)
        if success:
            print("[Retro-Tagger] Modelo reentrenado y persistido correctamente.")
        else:
            print("[Retro-Tagger] Reentrenamiento fallido: datos insuficientes.")

    print("\n[Retro-Tagger] Corrigiendo clasificaciones sospechosas (frutas/cereales/lacteos en main)...")
    fixed = retro_fix_suspicious(db)
    if fixed == 0:
        print("  -> Sin clasificaciones sospechosas encontradas.")
    else:
        print(f"  -> {fixed} alimentos corregidos.")
