"""Rutas HTTP de usuario autenticado."""
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.user import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user
