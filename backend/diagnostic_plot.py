"""Plot diagnóstico del clasificador KNN de alimentos.

Genera 4 subplots que explican visualmente:
  1. Espacio 2D (carb% vs protein%) — zona de confusión entre cereales y almidones
  2. Espacio 2D mejorado (sugar_ratio vs fiber_ratio) — cómo las features 6D los separan
  3. Distribución de alimentos por meal slot en el catálogo actual de MongoDB
  4. "Alertas": alimentos que pueden estar mal clasificados (cereales en main, etc.)
"""

import os
import sys

os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
os.environ.setdefault("MONGO_DB_NAME", "fibrito")
os.environ.setdefault("JWT_SECRET_KEY", "dev-script-secret")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from app.core.database import get_database
from app.services.food_classifier_service import (
    _extract_features,
    load_or_train_classifier,
    predict_suitable_meals,
)

# ---------------------------------------------------------------------------
# Paleta de colores por slot
# ---------------------------------------------------------------------------
SLOT_COLORS = {
    "early":  "#E74C3C",   # Rojo
    "main":   "#2980B9",   # Azul
    "late":   "#27AE60",   # Verde
    "snack":  "#F39C12",   # Naranja
}
SLOT_LABELS = {
    "early": "Desayuno (early)",
    "main":  "Comida (main)",
    "late":  "Cena (late)",
    "snack": "Snack",
}


def _primary_slot(meals: list[str]) -> str:
    """Slot principal para colorear (orden de prioridad visual)."""
    for slot in ("early", "snack", "late", "main"):
        if slot in meals:
            return slot
    return "main"


def _load_all_foods(db) -> list[dict]:
    """Carga todos los alimentos etiquetados de MongoDB."""
    return list(db.foods_catalog.find(
        {"suitable_meals": {"$exists": True, "$not": {"$size": 0}}}
    ))


def plot_macro_confusion_zone(ax, foods: list[dict]) -> None:
    """Plot 1: carb% vs protein% — zona de confusión entre cereales y almidones."""
    ax.set_title("Zona de confusión\ncarb% vs protein%", fontsize=11, fontweight="bold")

    # Fondo con anotación de la zona problemática
    ax.axvspan(0.0, 0.25, color="#FFF3CD", alpha=0.4, label="_zona proteína")
    ax.axvspan(0.6, 1.0, color="#D6EAF8", alpha=0.3, label="_zona carbos")

    legend_slots: set[str] = set()
    problem_foods: list[dict] = []

    for food in foods:
        feats = _extract_features(food)
        protein_ratio, _, carb_ratio = feats[0], feats[1], feats[2]
        meals = food.get("suitable_meals", [])
        slot = _primary_slot(meals)
        category = food.get("category", "otros")

        color = SLOT_COLORS.get(slot, "gray")
        label = SLOT_LABELS.get(slot, slot) if slot not in legend_slots else "_nolegend_"
        legend_slots.add(slot)

        # Detectar alimentos problemáticos: cereal/fruta etiquetado como "main"
        is_problem = (
            category in ("cereales", "frutas", "lacteos")
            and "main" in meals
            and "early" not in meals
        )

        if is_problem:
            problem_foods.append(food)
            ax.scatter(carb_ratio, protein_ratio, c="black", s=120,
                       marker="X", zorder=5, edgecolors="red", linewidths=1.5)
        else:
            ax.scatter(carb_ratio, protein_ratio, c=color, s=60,
                       alpha=0.75, edgecolors="white", linewidths=0.4, label=label)

    # Anotación de la zona de confusión
    ax.annotate(
        "⚠ Zona de confusión\nCereales ≈ Almidones\n(mismo carb%)",
        xy=(0.82, 0.06), fontsize=7.5, color="#C0392B",
        bbox=dict(boxstyle="round,pad=0.3", fc="#FADBD8", ec="#C0392B", alpha=0.8),
    )

    ax.set_xlabel("Ratio Carbohidratos (%cal)")
    ax.set_ylabel("Ratio Proteínas (%cal)")

    for slot in ("early", "main", "late", "snack"):
        ax.scatter([], [], c=SLOT_COLORS[slot], s=50,
                   label=SLOT_LABELS[slot], edgecolors="white")
    ax.scatter([], [], c="black", marker="X", s=80,
               label="Cereal/fruta en slot incorrecto", edgecolors="red")
    ax.legend(fontsize=7, loc="upper right")


def plot_6d_separation(ax, foods: list[dict]) -> None:
    """Plot 2: sugar_ratio vs fiber_ratio — cómo las features 6D separan cereales de almidones."""
    ax.set_title("Features 6D: separación\nfiber_ratio vs sugar_ratio", fontsize=11, fontweight="bold")

    # Regiones esperadas
    ax.axvspan(0.15, 1.5, color="#FDEBD0", alpha=0.35)
    ax.text(0.16, 0.78, "Zona Desayuno\n(alta fibra, algo de azúcar)",
            fontsize=7, color="#E67E22", va="top")
    ax.axvspan(0.0, 0.12, color="#D6EAF8", alpha=0.35)
    ax.text(0.01, 0.78, "Zona Main\n(baja fibra,\nbajo azúcar)",
            fontsize=7, color="#2980B9", va="top")

    legend_slots: set[str] = set()
    for food in foods:
        feats = _extract_features(food)
        fiber_ratio = feats[3]
        sugar_ratio = feats[4]
        meals = food.get("suitable_meals", [])
        slot = _primary_slot(meals)
        name = food.get("name", "")[:18]

        color = SLOT_COLORS.get(slot, "gray")
        label = SLOT_LABELS.get(slot, slot) if slot not in legend_slots else "_nolegend_"
        legend_slots.add(slot)

        ax.scatter(fiber_ratio, sugar_ratio, c=color, s=65,
                   alpha=0.8, edgecolors="white", linewidths=0.4, label=label)

        # Anotar cereales y frutas (los que tienen estos datos)
        category = food.get("category", "")
        if category in ("cereales", "frutas") and (fiber_ratio > 0.05 or sugar_ratio > 0.05):
            ax.annotate(name, (fiber_ratio, sugar_ratio),
                        textcoords="offset points", xytext=(4, 3),
                        fontsize=6, color="gray")

    ax.set_xlabel("fiber_ratio (fibra / carbos)")
    ax.set_ylabel("sugar_ratio (azúcar / carbos)")
    ax.set_xlim(-0.05, 1.0)
    ax.set_ylim(-0.05, 1.0)

    for slot in ("early", "main", "late", "snack"):
        ax.scatter([], [], c=SLOT_COLORS[slot], s=50, label=SLOT_LABELS[slot])
    ax.legend(fontsize=7, loc="lower right")


def plot_slot_distribution(ax, foods: list[dict]) -> None:
    """Plot 3: Barras de cuántos alimentos hay por slot y categoría."""
    ax.set_title("Distribución de alimentos\npor meal slot y categoría", fontsize=11, fontweight="bold")

    slots = ["early", "main", "late", "snack"]
    categories = ["proteinas", "carbohidratos", "grasas", "lacteos", "frutas", "vegetales", "cereales", "otros"]
    cat_colors = {
        "proteinas":     "#3498DB",
        "carbohidratos": "#E67E22",
        "grasas":        "#F1C40F",
        "lacteos":       "#1ABC9C",
        "frutas":        "#E74C3C",
        "vegetales":     "#2ECC71",
        "cereales":      "#9B59B6",
        "otros":         "#95A5A6",
    }

    # Contar alimentos por slot × categoría
    counts: dict[str, dict[str, int]] = {slot: {cat: 0 for cat in categories} for slot in slots}
    for food in foods:
        cat = food.get("category", "otros")
        if cat not in categories:
            cat = "otros"
        for slot in food.get("suitable_meals", []):
            if slot in counts:
                counts[slot][cat] = counts[slot].get(cat, 0) + 1

    x = np.arange(len(slots))
    bar_width = 0.08
    offsets = np.linspace(-(len(categories) - 1) * bar_width / 2,
                          (len(categories) - 1) * bar_width / 2, len(categories))

    for i, cat in enumerate(categories):
        vals = [counts[slot][cat] for slot in slots]
        ax.bar(x + offsets[i], vals, width=bar_width,
               color=cat_colors[cat], label=cat, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([SLOT_LABELS[s] for s in slots], fontsize=8)
    ax.set_ylabel("Nº de alimentos")
    ax.legend(fontsize=6, ncol=2, loc="upper right")


def plot_problem_table(ax, foods: list[dict]) -> None:
    """Plot 4: Tabla de alimentos potencialmente mal clasificados."""
    ax.set_title("Alimentos con clasificación\npotencialmente incorrecta", fontsize=11, fontweight="bold")
    ax.axis("off")

    SUSPICIOUS_COMBOS = [
        # (categoría, slot problemático, mensaje)
        ("cereales", "main", "Cereal de desayuno etiquetado como comida"),
        ("frutas",   "main", "Fruta etiquetada como comida principal"),
        ("lacteos",  "main", "Lácteo etiquetado solo como comida (sin early)"),
        ("proteinas","early","Proteína pesada solo en desayuno (sin main/late)"),
    ]

    problems: list[tuple[str, str, str]] = []
    for food in foods:
        name = food.get("name", "")[:30]
        cat = food.get("category", "otros")
        meals = food.get("suitable_meals", [])
        for check_cat, check_slot, msg in SUSPICIOUS_COMBOS:
            if cat == check_cat and check_slot in meals:
                if check_slot == "main" and "early" not in meals:
                    problems.append((name, str(meals), msg))
                elif check_slot == "early" and "main" not in meals and "late" not in meals:
                    problems.append((name, str(meals), msg))

    if not problems:
        ax.text(0.5, 0.5, "Sin clasificaciones sospechosas detectadas\nen el catálogo actual.",
                ha="center", va="center", fontsize=10, color="green",
                transform=ax.transAxes)
        return

    col_labels = ["Alimento", "Slots asignados", "Problema detectado"]
    table_data = problems[:12]  # Máximo 12 filas

    table = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    table.scale(1, 1.4)

    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#2C3E50")
            cell.set_text_props(color="white", fontweight="bold")
        elif row % 2 == 0:
            cell.set_facecolor("#F8F9FA")

    if len(problems) > 12:
        ax.text(0.5, 0.02, f"... y {len(problems) - 12} más",
                ha="center", fontsize=7, color="gray", transform=ax.transAxes)


def generate_diagnostic_plots(db) -> str:
    print("[Diagnóstico] Cargando alimentos de MongoDB...")
    foods = _load_all_foods(db)
    print(f"[Diagnóstico] {len(foods)} alimentos etiquetados encontrados.")

    if not foods:
        print("[Diagnóstico] Sin datos — ejecuta populate_foods.py primero.")
        return ""

    fig, axes = plt.subplots(2, 2, figsize=(14, 11))
    fig.suptitle(
        "Diagnóstico del Clasificador KNN — Fibrito Auto-Tagger",
        fontsize=14, fontweight="bold", y=1.01,
    )

    plot_macro_confusion_zone(axes[0, 0], foods)
    plot_6d_separation(axes[0, 1], foods)
    plot_slot_distribution(axes[1, 0], foods)
    plot_problem_table(axes[1, 1], foods)

    plt.tight_layout()
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostic_plot.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"[Diagnóstico] Plot guardado en: {out_path}")
    return out_path


if __name__ == "__main__":
    db = get_database()

    print("[Diagnóstico] Entrenando / cargando clasificador...")
    load_or_train_classifier(db)

    path = generate_diagnostic_plots(db)

    # Resumen de texto también
    print("\n--- Resumen rápido de clasificaciones ---")
    foods = _load_all_foods(db)
    slot_counts: dict[str, int] = {}
    for food in foods:
        for slot in food.get("suitable_meals", []):
            slot_counts[slot] = slot_counts.get(slot, 0) + 1

    for slot, count in sorted(slot_counts.items()):
        label = SLOT_LABELS.get(slot, slot)
        print(f"  {label:25s}: {count:3d} alimentos")
