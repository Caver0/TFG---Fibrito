"""Motor de Clasificación de Alimentos (Auto-Tagger) usando Machine Learning (ExtraTrees) + reglas híbridas."""

import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.preprocessing import MultiLabelBinarizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistencia del modelo
# ---------------------------------------------------------------------------
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models"
_MODEL_PATH = _MODEL_DIR / "food_classifier.pkl"

# ---------------------------------------------------------------------------
# Estado global en memoria (inferencia zero-latency)
# ---------------------------------------------------------------------------
_model: ExtraTreesClassifier | None = None
_mlb: MultiLabelBinarizer | None = None
_is_trained: bool = False
_training_samples: int = 0

# ---------------------------------------------------------------------------
# Conocimiento semántico de dominio (nivel 2 del sistema híbrido)
# ---------------------------------------------------------------------------

# Mapeo categoría → meal slots probables (reglas de negocio auditables)
CATEGORY_MEAL_RULES: dict[str, list[str]] = {
    "frutas":        ["early", "snack"],
    "lacteos":       ["early", "snack"],
    "cereales":      ["early"],          # Cornflakes, granola, muesli → solo desayuno
    "carbohidratos": ["main", "late"],   # Arroz, pasta, patata → comida y cena
    "proteinas":     ["main", "late"],
    "grasas":        ["main", "late"],
    "vegetales":     ["main", "late", "snack"],
    "otros":         ["main"],
}

# Puntuación ordinal de categoría: 0.0 = típicamente desayuno, 1.0 = típicamente cena.
# Usada como sexta feature del vector ML para inyectar conocimiento semántico.
CATEGORY_TO_SCORE: dict[str, float] = {
    "frutas":        0.1,
    "lacteos":       0.2,
    "cereales":      0.3,
    "carbohidratos": 0.5,
    "vegetales":     0.6,
    "proteinas":     0.7,
    "grasas":        0.8,
    "otros":         0.5,
}

# Umbral mínimo de confianza ML para preferir la predicción sobre las reglas.
# ExtraTrees da probabilidades continuas (0.01 granularidad con 100 estimadores),
# por lo que 0.45 es más adecuado que el 0.55 que usábamos con KNN.
ML_CONFIDENCE_THRESHOLD = 0.45


# ---------------------------------------------------------------------------
# Feature extraction (6D)
# ---------------------------------------------------------------------------

def _extract_features(food_data: dict) -> list[float]:
    """Vectoriza el alimento en 6 dimensiones:

    [protein_ratio, fat_ratio, carb_ratio, fiber_ratio, sugar_ratio, category_score]

    - Las proporciones calóricas (primeras 3) hacen el vector scale-invariant.
    - fiber_ratio discrimina cereales/frutas (alto) vs arroz/pasta (bajo).
    - sugar_ratio discrimina frutas (alto) vs cereales complejos (bajo).
    - category_score inyecta conocimiento semántico sin one-hot encoding.

    ExtraTreesClassifier no requiere normalización — los árboles de decisión son
    invariantes a la escala de las features.
    """
    cals = float(food_data.get("calories", 0))

    if cals <= 0:
        category = str(food_data.get("category", "otros")).strip().lower()
        return [0.0, 0.0, 0.0, 0.0, 0.0, CATEGORY_TO_SCORE.get(category, 0.5)]

    p = float(food_data.get("protein_grams", 0)) * 4.0
    f = float(food_data.get("fat_grams", 0)) * 9.0
    c = float(food_data.get("carb_grams", 0)) * 4.0

    protein_ratio = p / cals
    fat_ratio = f / cals
    carb_ratio = c / cals

    carb_grams = max(float(food_data.get("carb_grams", 0)), 1e-6)
    fiber_ratio = float(food_data.get("fiber_grams", 0)) / carb_grams
    sugar_ratio = float(food_data.get("sugar_grams", 0)) / carb_grams

    category = str(food_data.get("category", "otros")).strip().lower()
    category_score = CATEGORY_TO_SCORE.get(category, 0.5)

    return [protein_ratio, fat_ratio, carb_ratio, fiber_ratio, sugar_ratio, category_score]


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _save_model() -> None:
    """Persiste el modelo en disco para evitar reentrenamiento en cada startup."""
    try:
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": _model,
                "mlb": _mlb,
                "training_samples": _training_samples,
            },
            _MODEL_PATH,
        )
        logger.info("[Auto-Tagger] Modelo persistido en %s", _MODEL_PATH)
    except Exception as exc:
        logger.warning("[Auto-Tagger] No se pudo guardar el modelo: %s", exc)


def _load_model() -> bool:
    """Carga el modelo persistido desde disco. Devuelve True si tuvo éxito."""
    global _model, _mlb, _is_trained, _training_samples

    if not _MODEL_PATH.exists():
        return False

    try:
        state = joblib.load(_MODEL_PATH)
        # Compatibilidad con el formato antiguo (KNN + scaler)
        if "knn" in state:
            logger.info("[Auto-Tagger] Modelo antiguo (KNN) detectado — se reentrenará con ExtraTrees.")
            return False
        _model = state["model"]
        _mlb = state["mlb"]
        _training_samples = state.get("training_samples", 0)
        _is_trained = True
        logger.info(
            "[Auto-Tagger] Modelo cargado desde caché (%d muestras de entrenamiento)",
            _training_samples,
        )
        return True
    except Exception as exc:
        logger.warning("[Auto-Tagger] Modelo en caché corrupto o incompatible: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Entrenamiento
# ---------------------------------------------------------------------------

def train_classifier(database) -> bool:
    """Entrena ExtraTreesClassifier con todos los alimentos etiquetados de la BBDD.

    Ventajas sobre KNN:
    - class_weight='balanced' corrige el sesgo hacia la clase mayoritaria ('main').
    - Invariante a escala — no necesita StandardScaler.
    - Feature importance disponible para diagnóstico.
    - Inference O(log n) en lugar de O(n·d).
    """
    global _model, _mlb, _is_trained, _training_samples

    collection = database.foods_catalog
    cursor = collection.find({"suitable_meals": {"$exists": True, "$not": {"$size": 0}}})
    labeled_foods = list(cursor)

    if len(labeled_foods) < 5:
        _is_trained = False
        return False

    X = np.array([_extract_features(food) for food in labeled_foods])
    y_raw = [food["suitable_meals"] for food in labeled_foods]

    _mlb = MultiLabelBinarizer()
    y = _mlb.fit_transform(y_raw)

    _model = ExtraTreesClassifier(
        n_estimators=200,        # 200 árboles — mayor estabilidad con datasets pequeños
        class_weight="balanced", # Corrige el desequilibrio main >> early/late/snack
        max_features="sqrt",     # Subconjunto aleatorio de features por split
        min_samples_leaf=1,      # Permite splits muy finos con pocos datos
        random_state=42,
        n_jobs=-1,               # Paralelismo completo
    )
    _model.fit(X, y)

    _training_samples = len(labeled_foods)
    _is_trained = True

    _save_model()

    # Log de importancia de features para diagnóstico
    feature_names = ["protein_ratio", "fat_ratio", "carb_ratio", "fiber_ratio", "sugar_ratio", "category_score"]
    importances = _model.feature_importances_
    ranked = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
    logger.info("[Auto-Tagger] Feature importances: %s", ranked)

    return True


def load_or_train_classifier(database) -> bool:
    """Estrategia de inicio: carga desde disco antes de reentrenar."""
    if _load_model():
        return True
    return train_classifier(database)


def invalidate_model_cache() -> None:
    """Elimina el modelo persistido en disco para forzar reentrenamiento."""
    global _is_trained
    try:
        if _MODEL_PATH.exists():
            _MODEL_PATH.unlink()
            logger.info("[Auto-Tagger] Caché de modelo eliminada.")
    except Exception as exc:
        logger.warning("[Auto-Tagger] No se pudo eliminar la caché del modelo: %s", exc)
    _is_trained = False


# ---------------------------------------------------------------------------
# Sistema de clasificación híbrido (3 niveles)
# ---------------------------------------------------------------------------

def _classify_by_category_rules(food_data: dict) -> list[str] | None:
    """Nivel 2: Reglas deterministas por categoría. Alta precisión, sin ML."""
    category = str(food_data.get("category", "")).strip().lower()
    return CATEGORY_MEAL_RULES.get(category)


def _classify_by_dominant_macro(food_data: dict) -> list[str]:
    """Nivel 3: Infiere el slot desde el macro dominante en calorías (último recurso)."""
    cals_p = float(food_data.get("protein_grams", 0)) * 4.0
    cals_c = float(food_data.get("carb_grams", 0)) * 4.0
    cals_f = float(food_data.get("fat_grams", 0)) * 9.0

    if max(cals_p, cals_c, cals_f) == 0:
        return ["main"]

    dominant = max(
        [("protein", cals_p), ("carb", cals_c), ("fat", cals_f)],
        key=lambda x: x[1],
    )[0]
    return {"protein": ["main", "late"], "carb": ["main"], "fat": ["main", "late"]}[dominant]


def predict_suitable_meals(food_data: dict) -> list[str]:
    """Sistema de clasificación híbrido en 3 niveles (orden decreciente de confianza):

    1. ML (ExtraTrees) — si la confianza máxima supera ML_CONFIDENCE_THRESHOLD.
    2. Reglas por categoría — deterministas y auditables.
    3. Macro dominante — inferencia numérica pura como último recurso.
    """
    # Nivel 1: predicción ML con control de confianza
    if _is_trained and _model is not None and _mlb is not None:
        try:
            x = np.array([_extract_features(food_data)])

            # predict_proba devuelve lista de arrays (uno por label binarizado).
            # Cada array tiene forma (n_samples, 2): [prob_clase_0, prob_clase_1].
            proba_list = _model.predict_proba(x)
            max_confidence = max(p[0][1] for p in proba_list) if proba_list else 0.0

            if max_confidence >= ML_CONFIDENCE_THRESHOLD:
                prediction_bin = _model.predict(x)
                predicted_labels = _mlb.inverse_transform(prediction_bin)
                if predicted_labels and predicted_labels[0]:
                    return list(predicted_labels[0])

        except Exception as exc:
            logger.warning("[Auto-Tagger] Error en predicción ML, usando fallback: %s", exc)

    # Nivel 2: reglas de negocio por categoría
    category_result = _classify_by_category_rules(food_data)
    if category_result:
        return category_result

    # Nivel 3: macro dominante
    return _classify_by_dominant_macro(food_data)


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------

def get_classifier_status() -> dict:
    """Estado del clasificador para health-checks y diagnóstico."""
    feature_importances = {}
    if _model is not None:
        feature_names = ["protein_ratio", "fat_ratio", "carb_ratio", "fiber_ratio", "sugar_ratio", "category_score"]
        feature_importances = dict(zip(feature_names, _model.feature_importances_.tolist()))

    return {
        "is_trained": _is_trained,
        "model_type": "ExtraTreesClassifier",
        "training_samples": _training_samples,
        "model_cached_on_disk": _MODEL_PATH.exists(),
        "confidence_threshold": ML_CONFIDENCE_THRESHOLD,
        "feature_dimensions": 6,
        "known_classes": list(_mlb.classes_) if _mlb else [],
        "feature_importances": feature_importances,
    }
