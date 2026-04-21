"""Centralizamos un cliente de MongoDB reutilizable."""
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core.config import get_settings

_client: MongoClient | None = None


def connect_to_mongo() -> MongoClient:
    global _client

    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongodb_url)
        database = _client[settings.mongo_db_name]
        database.users.create_index([("email", ASCENDING)], unique=True)
        database.users.create_index([("reset_password_token_hash", ASCENDING)], sparse=True)
        # Legacy duplicated days should not block startup; the service layer also validates this rule.
        try:
            database.weight_logs.create_index(
                [("user_id", ASCENDING), ("date", ASCENDING)],
                unique=True,
            )
        except (DuplicateKeyError, OperationFailure) as exc:
            if "duplicate key error" not in str(exc).lower():
                raise
        database.weight_logs.create_index(
            [("user_id", ASCENDING), ("date", ASCENDING), ("created_at", ASCENDING)]
        )
        database.calorie_adjustments.create_index(
            [("user_id", ASCENDING), ("created_at", ASCENDING)]
        )
        database.diets.create_index(
            [("user_id", ASCENDING), ("created_at", ASCENDING)]
        )
        database.diets.create_index(
            [("user_id", ASCENDING), ("is_active", ASCENDING), ("valid_from", ASCENDING)]
        )
        database.diets.create_index(
            [("user_id", ASCENDING), ("valid_from", ASCENDING), ("valid_to", ASCENDING)]
        )
        try:
            database.diets.create_index(
                [("user_id", ASCENDING), ("is_active", ASCENDING)],
                unique=True,
                partialFilterExpression={"is_active": True},
            )
        except (DuplicateKeyError, OperationFailure) as exc:
            if "duplicate key error" not in str(exc).lower():
                raise
        database.diet_adherence.create_index(
            [
                ("user_id", ASCENDING),
                ("diet_id", ASCENDING),
                ("date", ASCENDING),
                ("meal_number", ASCENDING),
            ],
            unique=True,
        )
        database.diet_adherence.create_index(
            [("user_id", ASCENDING), ("date", ASCENDING)]
        )
        database.diet_adherence.create_index(
            [("diet_id", ASCENDING), ("date", ASCENDING)]
        )
        database.foods_catalog.create_index([("normalized_name", ASCENDING)])
        database.foods_catalog.create_index([("aliases", ASCENDING)])
        database.foods_catalog.create_index([("internal_code", ASCENDING)])
        database.foods_catalog.create_index([("updated_at", ASCENDING)])
        database.foods_catalog.create_index(
            [("spoonacular_id", ASCENDING)],
            unique=True,
            sparse=True,
        )

    return _client


def get_database():
    settings = get_settings()
    client = connect_to_mongo()
    return client[settings.mongo_db_name]
