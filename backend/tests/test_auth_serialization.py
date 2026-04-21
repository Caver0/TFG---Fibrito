from datetime import UTC, datetime

from bson import ObjectId

from app.schemas.user import serialize_user


def _build_user_document(**overrides) -> dict:
    base_document = {
        "_id": ObjectId(),
        "name": "Test User",
        "email": "test@example.com",
        "created_at": datetime(2026, 4, 21, tzinfo=UTC),
        "password_hash": None,
        "food_preferences": {
            "preferred_foods": [],
            "disliked_foods": [],
            "dietary_restrictions": [],
            "allergies": [],
        },
    }
    base_document.update(overrides)
    return base_document


def test_serialize_user_infers_password_provider_for_legacy_users():
    document = _build_user_document(password_hash="hashed-password")

    serialized_user = serialize_user(document)

    assert serialized_user.auth_providers == ["password"]


def test_serialize_user_ignores_unsupported_provider_metadata():
    document = _build_user_document(
        password_hash="hashed-password",
        legacy_provider_id="legacy-provider-id",
        auth_providers=["external", "password"],
    )

    serialized_user = serialize_user(document)

    assert serialized_user.auth_providers == ["password"]
