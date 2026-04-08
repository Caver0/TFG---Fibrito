"""Authentication routes."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.security import create_access_token, get_password_hash, verify_password
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserPublic, serialize_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate) -> UserPublic:
    database = get_database()
    normalized_email = payload.email.strip().lower()

    existing_user = database.users.find_one({"email": normalized_email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user_document = {
        "name": payload.name.strip(),
        "email": normalized_email,
        "password_hash": get_password_hash(payload.password),
        "created_at": datetime.now(timezone.utc),
        "age": None,
        "sex": None,
        "height": None,
        "current_weight": None,
        "training_days_per_week": None,
        "goal": None,
        "target_calories": None,
        "preferences": [],
        "restrictions": [],
    }

    try:
        inserted = database.users.insert_one(user_document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from exc

    created_user = database.users.find_one({"_id": inserted.inserted_id})
    return serialize_user(created_user)


@router.post("/login", response_model=TokenResponse)
def login_user(payload: LoginRequest) -> TokenResponse:
    database = get_database()
    normalized_email = payload.email.strip().lower()
    user = database.users.find_one({"email": normalized_email})

    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    public_user = serialize_user(user)
    access_token = create_access_token(public_user.id)
    return TokenResponse(access_token=access_token, user=public_user)
