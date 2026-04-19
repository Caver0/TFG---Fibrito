"""Routes for generating and retrieving user food-based diets."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.diet import (
    BuscarAlimentoSustitutoRequest,
    BuscarAlimentoSustitutoResponse,
    DailyDiet,
    DietGenerateRequest,
    DietListResponse,
    DietMutationResponse,
    FoodReplacementOptionsResponse,
    ReplaceFoodRequest,
)
from app.schemas.user import UserPublic
from app.services.diet_service import (
    generate_food_based_diet,
    get_active_user_diet,
    get_user_diet_by_id,
    list_user_diets,
    save_diet,
)
from app.services.food_substitution_service import (
    list_food_replacement_options,
    replace_food_in_meal,
    search_replacement_food,
)
from app.services.food_preferences_service import FoodPreferenceConflictError
from app.services.meal_regeneration_service import regenerate_meal
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
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    return get_active_user_diet(database, current_user.id)


@router.get("/{diet_id}", response_model=DailyDiet)
def read_user_diet_by_id(
    diet_id: str,
    current_user: UserPublic = Depends(get_current_user),
) -> DailyDiet:
    database = get_database()
    return get_user_diet_by_id(database, current_user.id, diet_id)


@router.post("/{diet_id}/meals/{meal_number}/regenerate", response_model=DietMutationResponse)
def regenerate_user_meal(
    diet_id: str,
    meal_number: int,
    current_user: UserPublic = Depends(get_current_user),
) -> DietMutationResponse:
    database = get_database()

    try:
        return regenerate_meal(
            database,
            user=current_user,
            diet_id=diet_id,
            meal_number=meal_number,
        )
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/{diet_id}/meals/{meal_number}/replace-food", response_model=DietMutationResponse)
def replace_user_food_in_meal(
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> DietMutationResponse:
    database = get_database()

    try:
        return replace_food_in_meal(
            database,
            user=current_user,
            diet_id=diet_id,
            meal_number=meal_number,
            payload=payload,
        )
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/{diet_id}/meals/{meal_number}/replacement-options", response_model=FoodReplacementOptionsResponse)
def list_user_food_replacement_options(
    diet_id: str,
    meal_number: int,
    payload: ReplaceFoodRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> FoodReplacementOptionsResponse:
    database = get_database()

    try:
        return list_food_replacement_options(
            database,
            user=current_user,
            diet_id=diet_id,
            meal_number=meal_number,
            payload=payload,
        )
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/{diet_id}/meals/{meal_number}/search-replacement-food",
    response_model=BuscarAlimentoSustitutoResponse,
)
def search_user_replacement_food(
    diet_id: str,
    meal_number: int,
    payload: BuscarAlimentoSustitutoRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> BuscarAlimentoSustitutoResponse:
    database = get_database()

    try:
        return search_replacement_food(
            database,
            user=current_user,
            diet_id=diet_id,
            meal_number=meal_number,
            payload=payload,
        )
    except FoodPreferenceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
