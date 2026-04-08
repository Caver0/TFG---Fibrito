"""Business logic for generating and retrieving daily diets."""
from decimal import ROUND_HALF_UP, Decimal
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import HTTPException, status

from app.schemas.diet import DailyDiet, DietListItem, DietMeal, serialize_daily_diet, serialize_diet_list_item
from app.schemas.user import UserPublic
from app.services.nutrition_service import build_nutrition_summary

DIET_PRECISION = Decimal("0.1")


def round_diet_value(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(DIET_PRECISION, rounding=ROUND_HALF_UP))


def distribute_total(total: float, parts: int) -> list[float]:
    total_decimal = Decimal(str(total))
    remaining = total_decimal
    distribution: list[float] = []

    for index in range(parts):
        remaining_slots = parts - index
        if remaining_slots == 1:
            portion = remaining
        else:
            portion = (remaining / Decimal(remaining_slots)).quantize(
                DIET_PRECISION,
                rounding=ROUND_HALF_UP,
            )

        distribution.append(float(portion))
        remaining -= portion

    return distribution


def build_meal_distribution(
    *,
    meals_count: int,
    target_calories: float,
    protein_grams: float,
    fat_grams: float,
    carb_grams: float,
) -> list[DietMeal]:
    calories_per_meal = distribute_total(target_calories, meals_count)
    protein_per_meal = distribute_total(protein_grams, meals_count)
    fat_per_meal = distribute_total(fat_grams, meals_count)
    carbs_per_meal = distribute_total(carb_grams, meals_count)

    meals: list[DietMeal] = []
    for meal_index in range(meals_count):
        meals.append(
            DietMeal(
                meal_number=meal_index + 1,
                target_calories=calories_per_meal[meal_index],
                target_protein_grams=protein_per_meal[meal_index],
                target_fat_grams=fat_per_meal[meal_index],
                target_carb_grams=carbs_per_meal[meal_index],
            )
        )

    return meals


def generate_daily_diet(user: UserPublic, meals_count: int) -> dict:
    nutrition = build_nutrition_summary(
        user,
        target_calories_override=user.target_calories,
    )
    meals = build_meal_distribution(
        meals_count=meals_count,
        target_calories=nutrition.target_calories,
        protein_grams=nutrition.protein_grams,
        fat_grams=nutrition.fat_grams,
        carb_grams=nutrition.carb_grams,
    )

    return {
        "meals_count": meals_count,
        "target_calories": nutrition.target_calories,
        "protein_grams": nutrition.protein_grams,
        "fat_grams": nutrition.fat_grams,
        "carb_grams": nutrition.carb_grams,
        "meals": [meal.model_dump() for meal in meals],
    }


def save_diet(database, user_id: str, diet_payload: dict) -> DailyDiet:
    diet_document = {
        "user_id": ObjectId(user_id),
        "created_at": datetime.now(UTC),
        "meals_count": diet_payload["meals_count"],
        "target_calories": round_diet_value(diet_payload["target_calories"]),
        "protein_grams": round_diet_value(diet_payload["protein_grams"]),
        "fat_grams": round_diet_value(diet_payload["fat_grams"]),
        "carb_grams": round_diet_value(diet_payload["carb_grams"]),
        "meals": diet_payload["meals"],
    }
    inserted = database.diets.insert_one(diet_document)
    created_diet = database.diets.find_one({"_id": inserted.inserted_id})
    return serialize_daily_diet(created_diet)


def list_user_diets(database, user_id: str) -> list[DietListItem]:
    documents = database.diets.find({"user_id": ObjectId(user_id)}).sort([("created_at", -1)])
    return [serialize_diet_list_item(document) for document in documents]


def get_user_diet_by_id(database, user_id: str, diet_id: str) -> DailyDiet:
    if not ObjectId.is_valid(diet_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet not found",
        )

    document = database.diets.find_one(
        {
            "_id": ObjectId(diet_id),
            "user_id": ObjectId(user_id),
        }
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet not found",
        )

    return serialize_daily_diet(document)


def get_latest_user_diet(database, user_id: str) -> DailyDiet | None:
    document = database.diets.find_one(
        {"user_id": ObjectId(user_id)},
        sort=[("created_at", -1)],
    )
    if not document:
        return None

    return serialize_daily_diet(document)
