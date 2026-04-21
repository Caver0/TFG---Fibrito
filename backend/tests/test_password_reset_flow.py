from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.routes import auth as auth_routes
from app.schemas.auth import ResetPasswordRequest, ResetPasswordTokenRequest
from app.services.password_reset_service import hash_password_reset_token


def _matches_query(document: dict, query: dict) -> bool:
    for key, expected_value in query.items():
        actual_value = document.get(key)
        if isinstance(expected_value, dict):
            if "$gt" in expected_value and not (actual_value and actual_value > expected_value["$gt"]):
                return False
            continue

        if actual_value != expected_value:
            return False

    return True


class FakeUsersCollection:
    def __init__(self, documents: list[dict]):
        self.documents = documents

    def find_one(self, query: dict) -> dict | None:
        for document in self.documents:
            if _matches_query(document, query):
                return document
        return None

    def find_one_and_update(self, query: dict, update: dict, return_document=None) -> dict | None:
        document = self.find_one(query)
        if not document:
            return None

        for key, value in update.get("$set", {}).items():
            document[key] = value

        return document


class FakeDatabase:
    def __init__(self, user_document: dict):
        self.users = FakeUsersCollection([user_document])


def test_reset_password_token_is_invalid_after_first_use(monkeypatch):
    raw_token = "reset-token-used-once-1234567890"
    user_document = {
        "_id": ObjectId(),
        "name": "Reset User",
        "email": "reset@example.com",
        "created_at": datetime(2026, 4, 21, tzinfo=UTC),
        "password_hash": "old-password-hash",
        "auth_providers": [],
        "reset_password_token_hash": hash_password_reset_token(raw_token),
        "reset_password_expires_at": datetime.now(UTC) + timedelta(minutes=15),
        "reset_password_requested_at": datetime.now(UTC),
        "food_preferences": {
            "preferred_foods": [],
            "disliked_foods": [],
            "dietary_restrictions": [],
            "allergies": [],
        },
    }
    fake_database = FakeDatabase(user_document)

    monkeypatch.setattr(auth_routes, "get_database", lambda: fake_database)
    monkeypatch.setattr(auth_routes, "get_password_hash", lambda password: f"hashed::{password}")

    validation_response = auth_routes.validate_reset_password_token(
        ResetPasswordTokenRequest(token=raw_token)
    )
    assert validation_response.message == "Token de recuperacion valido"

    reset_response = auth_routes.reset_password(
        ResetPasswordRequest(
            token=raw_token,
            new_password="new-password-123",
            confirm_password="new-password-123",
        )
    )
    assert reset_response.message == "Contrasena actualizada correctamente"
    assert user_document["reset_password_token_hash"] is None
    assert user_document["reset_password_expires_at"] is None
    assert user_document["reset_password_requested_at"] is None
    assert user_document["password_hash"] == "hashed::new-password-123"

    with pytest.raises(HTTPException) as validation_exc:
        auth_routes.validate_reset_password_token(ResetPasswordTokenRequest(token=raw_token))

    assert validation_exc.value.status_code == 400
    assert validation_exc.value.detail == "Enlace invalido o expirado."

    with pytest.raises(HTTPException) as reset_exc:
        auth_routes.reset_password(
            ResetPasswordRequest(
                token=raw_token,
                new_password="another-password-123",
                confirm_password="another-password-123",
            )
        )

    assert reset_exc.value.status_code == 400
    assert reset_exc.value.detail == "Enlace invalido o expirado."
