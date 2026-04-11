"""Routes for generating and retrieving user food-based diets."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.diet import DailyDiet, DietGenerateRequest, DietListResponse
from app.schemas.user import UserPublic
from app.services.diet_service import (
    generate_food_based_diet,
    get_latest_user_diet,
    get_user_diet_by_id,
    list_user_diets,
    save_diet,
)
from app.services.nutrition_service import NutritionProfileIncompleteError

router = APIRouter(prefix="/diets", tags=["diets"])


@router.post("/generate", response_model=DailyDiet, status_code=status.HTTP_201_CREATED)
def create_daily_diet(
    payload: DietGenerateRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet:
    database = get_database()

    try:
        diet_payload = generate_food_based_diet(
            database,
            current_user,
            payload.meals_count,
            custom_percentages=payload.custom_percentages,
            training_time_of_day=payload.training_time_of_day,
        )
    except NutritionProfileIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return save_diet(database, current_user.id, diet_payload)


@router.get("", response_model=DietListResponse)
def read_user_diet_history(
    current_user: UserPublic = Depends(get_current_user),
) -> DietListResponse:
    database = get_database()
    diets = list_user_diets(database, current_user.id)
    return DietListResponse(diets=diets)


@router.get("/latest", response_model=DailyDiet | None)
def read_latest_user_diet(
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet | None:
    database = get_database()
    return get_latest_user_diet(database, current_user.id)


@router.get("/{diet_id}", response_model=DailyDiet)
def read_user_diet_by_id(
    diet_id: str,
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet:
    database = get_database()
    return get_user_diet_by_id(database, current_user.id, diet_id)
