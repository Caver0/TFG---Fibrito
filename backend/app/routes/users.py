"""Routes for the authenticated user profile and nutrition targets."""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.nutrition import NutritionProfileUpdate, NutritionSummary
from app.schemas.user import FoodPreferencesProfile, FoodPreferencesUpdate, UserPublic, serialize_user
from app.services.food_preferences_service import sanitize_user_food_preferences
from app.services.nutrition_service import (
    NutritionProfileIncompleteError,
    build_nutrition_summary,
    get_default_target_calories,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user


@router.get("/me/preferences", response_model=FoodPreferencesProfile)
def read_current_user_food_preferences(
    current_user: UserPublic = Depends(get_current_user),
) -> FoodPreferencesProfile:
    return current_user.food_preferences


@router.put("/me/preferences", response_model=FoodPreferencesProfile)
def update_current_user_food_preferences(
    payload: FoodPreferencesUpdate,
    current_user: UserPublic = Depends(get_current_user),
) -> FoodPreferencesProfile:
    database = get_database()
    current_user_id = ObjectId(current_user.id)
    serialized_preferences = sanitize_user_food_preferences(payload)
    updated_user = database.users.find_one_and_update(
        {"_id": current_user_id},
        {"$set": {"food_preferences": serialized_preferences}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return serialize_user(updated_user).food_preferences


@router.put("/me/profile", response_model=UserPublic)
def update_current_user_profile(
    payload: NutritionProfileUpdate,
    current_user: UserPublic = Depends(get_current_user),
) -> UserPublic:
    database = get_database()
    update_data = payload.model_dump(exclude_unset=True)
    current_user_id = ObjectId(current_user.id)

    if update_data:
        updated_user = database.users.find_one_and_update(
            {"_id": current_user_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
    else:
        updated_user = database.users.find_one({"_id": current_user_id})

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        next_target_calories = get_default_target_calories(updated_user)
    except NutritionProfileIncompleteError:
        next_target_calories = None

    updated_user = database.users.find_one_and_update(
        {"_id": current_user_id},
        {"$set": {"target_calories": next_target_calories}},
        return_document=ReturnDocument.AFTER,
    )
    return serialize_user(updated_user)


@router.get("/me/nutrition", response_model=NutritionSummary)
def read_current_user_nutrition(
    current_user: UserPublic = Depends(get_current_user),
) -> NutritionSummary:
    try:
        return build_nutrition_summary(
            current_user,
            target_calories_override=current_user.target_calories,
        )
    except NutritionProfileIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
