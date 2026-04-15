"""Test y visualización del Auto-Tagger (KNN + sistema híbrido).

Muestra:
- Predicciones con nivel de confianza por alimento
- Métricas de cross-validation (precisión media)
- Plot 3D del espacio de features (protein%, fat%, carb%)
- Estado del clasificador híbrido
"""

import os
import sys

os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler

from app.core.database import get_database
from app.services.food_classifier_service import (
    _extract_features,
    get_classifier_status,
    load_or_train_classifier,
    predict_suitable_meals,
)


def test_predictions():
    print("=" * 60)
    print(" Auto-Tagger — Test del Sistema Híbrido (KNN + Reglas)")
    print("=" * 60)

    db = get_database()

    print("\n[1] Entrenando / cargando modelo KNN...")
    success = load_or_train_classifier(db)
    if not success:
        print("    [!] No hay suficientes alimentos etiquetados.")
        print("    Ejecuta populate_foods.py antes de este script.")
        return

    status = get_classifier_status()
    print(f"    Muestras de entrenamiento : {status['training_samples']}")
    print(f"    Dimensiones del vector    : {status['feature_dimensions']}D")
    print(f"    Clases conocidas          : {status['known_classes']}")
    print(f"    Umbral de confianza ML    : {status['confidence_threshold']}")
    print(f"    Modelo en caché (disco)   : {status['model_cached_on_disk']}")

    print("\n[2] Cross-validation (k-fold=5) del modelo KNN...")
    _run_cross_validation(db)

    print("\n[3] Predicciones sobre alimentos de prueba:")
    _test_mock_foods()

    print("\n[4] Predicciones sobre alimentos sin ML (reglas híbridas):")
    _test_hybrid_rules()

    print("\n[5] Generando plot 3D del espacio de features...")
    generate_plot(db)

    print("\nTest completado.")


def _run_cross_validation(db) -> None:
    """Evalúa la precisión del KNN con cross-validation y reporta por clase."""
    labeled_foods = list(
        db.foods_catalog.find({"suitable_meals": {"$exists": True, "$not": {"$size": 0}}})
    )
    if len(labeled_foods) < 10:
        print("    [!] Menos de 10 muestras — cross-validation omitida.")
        return

    X_raw = [_extract_features(f) for f in labeled_foods]
    y_raw = [f["suitable_meals"] for f in labeled_foods]

    X_np = np.array(X_raw)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_np)

    mlb = MultiLabelBinarizer()
    y_bin = mlb.fit_transform(y_raw)

    k = min(7, len(labeled_foods))
    knn = KNeighborsClassifier(n_neighbors=k, weights="distance", metric="euclidean")

    # cross_val_score con scoring='accuracy' mide exact match multilabel
    scores = cross_val_score(knn, X_scaled, y_bin, cv=min(5, len(labeled_foods)), scoring="accuracy")
    print(f"    Accuracy media (CV)  : {scores.mean():.2%} ± {scores.std():.2%}")
    print(f"    Scores individuales  : {[f'{s:.2%}' for s in scores]}")


def _test_mock_foods() -> None:
    """Prueba el clasificador con alimentos ficticios representativos."""
    mock_foods = [
        # (descripción, dict con macros)
        ("Avena con fruta [→ early]",
         {"calories": 350, "protein_grams": 12, "fat_grams": 6, "carb_grams": 58,
          "fiber_grams": 8, "sugar_grams": 10, "category": "cereales"}),
        ("Pechuga de pollo a la plancha [→ main/late]",
         {"calories": 165, "protein_grams": 31, "fat_grams": 3.6, "carb_grams": 0,
          "fiber_grams": 0, "sugar_grams": 0, "category": "proteinas"}),
        ("Salmón al horno [→ main/late]",
         {"calories": 208, "protein_grams": 20, "fat_grams": 13, "carb_grams": 0,
          "fiber_grams": 0, "sugar_grams": 0, "category": "proteinas"}),
        ("Arroz blanco [→ main]",
         {"calories": 130, "protein_grams": 2.7, "fat_grams": 0.3, "carb_grams": 28,
          "fiber_grams": 0.4, "sugar_grams": 0, "category": "carbohidratos"}),
        ("Yogur griego natural [→ early/snack]",
         {"calories": 97, "protein_grams": 9, "fat_grams": 5, "carb_grams": 4,
          "fiber_grams": 0, "sugar_grams": 4, "category": "lacteos"}),
        ("Batido caseína nocturno [→ late]",
         {"calories": 150, "protein_grams": 30, "fat_grams": 1, "carb_grams": 5,
          "fiber_grams": 0, "sugar_grams": 2, "category": "proteinas"}),
        ("Tortitas con nata [→ early/snack]",
         {"calories": 500, "protein_grams": 8, "fat_grams": 24, "carb_grams": 62,
          "fiber_grams": 1, "sugar_grams": 30, "category": "cereales"}),
        ("Aguacate [→ main/late]",
         {"calories": 160, "protein_grams": 2, "fat_grams": 15, "carb_grams": 9,
          "fiber_grams": 7, "sugar_grams": 0.7, "category": "grasas"}),
    ]

    for desc, food in mock_foods:
        prediction = predict_suitable_meals(food)
        print(f"    {desc}")
        print(f"      → Predicción: {prediction}")


def _test_hybrid_rules() -> None:
    """Verifica que el sistema de reglas funciona cuando no hay modelo ML."""
    print("    (simulando clasificador no entrenado para mostrar nivel 2 y 3)")
    rule_only_foods = [
        {"name": "Fruta sin macros", "category": "frutas",
         "calories": 0, "protein_grams": 0, "fat_grams": 0, "carb_grams": 0},
        {"name": "Verduras sin categoría", "category": "",
         "calories": 30, "protein_grams": 2, "fat_grams": 0.3, "carb_grams": 5},
        {"name": "Alimento desconocido sin nada", "category": "",
         "calories": 0, "protein_grams": 0, "fat_grams": 0, "carb_grams": 0},
    ]
    from app.services.food_classifier_service import (
        _classify_by_category_rules,
        _classify_by_dominant_macro,
    )
    for food in rule_only_foods:
        cat_result = _classify_by_category_rules(food)
        mac_result = _classify_by_dominant_macro(food)
        print(f"    '{food['name']}'")
        print(f"      Nivel 2 (categoría)  : {cat_result}")
        print(f"      Nivel 3 (macro dom.) : {mac_result}")


def generate_plot(db) -> None:
    """Genera un scatter 3D (protein%, fat%, carb%) coloreado por clase principal."""
    labeled_foods = list(
        db.foods_catalog.find({"suitable_meals": {"$exists": True, "$not": {"$size": 0}}})
    )
    if not labeled_foods:
        print("    [!] Sin datos para el plot.")
        return

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")

    COLOR_MAP = {
        "early": ("#E74C3C", "Desayuno (early)"),
        "main":  ("#2E86C1", "Comida (main)"),
        "late":  ("#27AE60", "Cena (late)"),
        "snack": ("#F39C12", "Snack"),
    }
    plotted_labels: set[str] = set()

    for food in labeled_foods:
        feats = _extract_features(food)
        meals = food.get("suitable_meals", [])

        # Prioridad de color: early > snack > main > late
        primary = next(
            (slot for slot in ("early", "snack", "main", "late") if slot in meals),
            None,
        )
        if primary is None:
            continue

        color, label = COLOR_MAP[primary]
        show_label = label if label not in plotted_labels else "_nolegend_"
        plotted_labels.add(label)

        ax.scatter(
            feats[0], feats[1], feats[2],
            c=color, s=75, marker="o", alpha=0.85,
            edgecolors="white", linewidths=0.5,
            label=show_label,
        )

    ax.set_xlabel("Ratio Proteico (%cal)")
    ax.set_ylabel("Ratio Graso (%cal)")
    ax.set_zlabel("Ratio Carbohidratos (%cal)")
    ax.set_title(
        f"KNN 6D — Espacio de Macros por Meal Slot\n"
        f"({len(labeled_foods)} alimentos etiquetados)",
        fontsize=12,
    )
    ax.legend(loc="upper left", fontsize=9)

    plot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cluster_plot.png")
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    print(f"    Plot guardado en: {plot_path}")


if __name__ == "__main__":
    test_predictions()
