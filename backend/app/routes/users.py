"""Routes for the authenticated user profile and nutrition targets."""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.nutrition import NutritionProfileUpdate, NutritionSummary
from app.schemas.user import UserPublic, serialize_user
from app.services.nutrition_service import (
    NutritionProfileIncompleteError,
    build_nutrition_summary,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user


@router.put("/me/profile", response_model=UserPublic)
def update_current_user_profile(
    payload: NutritionProfileUpdate,
    current_user: UserPublic = Depends(get_current_user),
) -> UserPublic:
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return current_user

    database = get_database()
    updated_user = database.users.find_one_and_update(
        {"_id": ObjectId(current_user.id)},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return serialize_user(updated_user)


@router.get("/me/nutrition", response_model=NutritionSummary)
def read_current_user_nutrition(
    current_user: UserPublic = Depends(get_current_user),
) -> NutritionSummary:
    try:
        return build_nutrition_summary(current_user)
    except NutritionProfileIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
