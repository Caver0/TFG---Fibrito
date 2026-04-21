"""Authentication routes."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.security import create_access_token, get_password_hash, verify_password
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    ResetPasswordTokenRequest,
    TokenResponse,
)
from app.schemas.user import UserCreate, UserPublic, serialize_user
from app.services.email_service import (
    EmailConfigurationError,
    EmailDeliveryError,
    send_email,
    validate_email_delivery_settings,
)
from app.services.password_reset_service import (
    INVALID_PASSWORD_RESET_TOKEN_MESSAGE,
    build_valid_password_reset_query,
    build_password_reset_email,
    build_password_reset_url,
    create_password_reset_token,
    get_password_reset_expiration,
    hash_password_reset_token,
)
from app.utils.auth import (
    AUTH_PROVIDER_PASSWORD,
    build_password_reset_clear_fields,
    build_user_document_base,
    merge_auth_provider,
    normalize_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])

PASSWORD_RESET_REQUEST_MESSAGE = (
    "Si el email existe en Fibrito, hemos enviado un enlace de recuperacion."
)


def _create_session_response(user_document: dict) -> TokenResponse:
    public_user = serialize_user(user_document)
    access_token = create_access_token(public_user.id)
    return TokenResponse(access_token=access_token, user=public_user)


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate) -> UserPublic:
    database = get_database()
    normalized_email = normalize_email(payload.email)

    existing_user = database.users.find_one({"email": normalized_email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user_document = build_user_document_base(name=payload.name, email=normalized_email)
    user_document.update(
        {
            "password_hash": get_password_hash(payload.password),
            "auth_providers": [AUTH_PROVIDER_PASSWORD],
        }
    )

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
    normalized_email = normalize_email(payload.email)
    user = database.users.find_one({"email": normalized_email})

    if not user or not verify_password(payload.password, user.get("password_hash")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _create_session_response(user)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest) -> MessageResponse:
    try:
        validate_email_delivery_settings()
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    database = get_database()
    normalized_email = normalize_email(payload.email)
    user = database.users.find_one({"email": normalized_email})

    if not user:
        return MessageResponse(message=PASSWORD_RESET_REQUEST_MESSAGE)

    raw_token, token_hash = create_password_reset_token()
    expires_at = get_password_reset_expiration()
    reset_url = build_password_reset_url(raw_token)
    subject, text_body, html_body = build_password_reset_email(user["name"], reset_url)

    database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "reset_password_token_hash": token_hash,
                "reset_password_expires_at": expires_at,
                "reset_password_requested_at": datetime.now(timezone.utc),
            }
        },
    )

    try:
        send_email(
            to_email=user["email"],
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return MessageResponse(message=PASSWORD_RESET_REQUEST_MESSAGE)


@router.post("/reset-password/validate", response_model=MessageResponse)
def validate_reset_password_token(payload: ResetPasswordTokenRequest) -> MessageResponse:
    database = get_database()
    token_hash = hash_password_reset_token(payload.token)

    user = database.users.find_one(build_valid_password_reset_query(token_hash))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_PASSWORD_RESET_TOKEN_MESSAGE,
        )

    return MessageResponse(message="Token de recuperacion valido")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
    database = get_database()
    token_hash = hash_password_reset_token(payload.token)
    now = datetime.now(timezone.utc)
    valid_reset_query = build_valid_password_reset_query(token_hash, now=now)

    user = database.users.find_one(valid_reset_query)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_PASSWORD_RESET_TOKEN_MESSAGE,
        )

    updated_user = database.users.find_one_and_update(
        {
            "_id": user["_id"],
            **valid_reset_query,
        },
        {
            "$set": {
                "password_hash": get_password_hash(payload.new_password),
                "auth_providers": merge_auth_provider(user, AUTH_PROVIDER_PASSWORD),
                **build_password_reset_clear_fields(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_PASSWORD_RESET_TOKEN_MESSAGE,
        )

    return MessageResponse(message="Contrasena actualizada correctamente")
