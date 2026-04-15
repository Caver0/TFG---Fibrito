"""Etiquetado retroactivo de alimentos sin suitable_meals en MongoDB.

Etiqueta todos los alimentos de Spoonacular que no tienen suitable_meals
usando el sistema híbrido (KNN + reglas de categoría + macro dominante).
Al finalizar, invalida el caché del modelo y lo reentrena con los nuevos datos.
"""

import os
import sys

os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import get_database
from app.services.food_classifier_service import (
    invalidate_model_cache,
    load_or_train_classifier,
    predict_suitable_meals,
)


def retro_tag_all(db) -> int:
    """Etiqueta los alimentos sin suitable_meals. Devuelve el número de alimentos actualizados."""
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
        print(f"  [{food.get('name', food['_id'])}]  →  {predicted}")
        updated += 1

    return updated


if __name__ == "__main__":
    db = get_database()

    print("[Retro-Tagger] Cargando / entrenando modelo antes del etiquetado...")
    load_or_train_classifier(db)

    print("\n[Retro-Tagger] Etiquetando alimentos sin clasificar...")
    count = retro_tag_all(db)

    if count == 0:
        print("  → Ningún alimento sin etiquetar encontrado.")
    else:
        print(f"\n[Retro-Tagger] {count} alimentos etiquetados.")
        print("[Retro-Tagger] Invalidando caché del modelo y reentrenando con nuevos datos...")
        invalidate_model_cache()
        success = load_or_train_classifier(db)
        if success:
            print("[Retro-Tagger] Modelo reentrenado y persistido correctamente.")
        else:
            print("[Retro-Tagger] Reentrenamiento fallido: datos insuficientes.")
