"""Centralizamos un cliente de MongoDB reutilizable."""
from pymongo import ASCENDING, MongoClient

from app.core.config import get_settings

_client: MongoClient | None = None


def connect_to_mongo() -> MongoClient:
    global _client

    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongodb_url)
        database = _client[settings.mongo_db_name]
        database.users.create_index([("email", ASCENDING)], unique=True)
        database.weight_logs.create_index(
            [("user_id", ASCENDING), ("date", ASCENDING), ("created_at", ASCENDING)]
        )
        database.calorie_adjustments.create_index(
            [("user_id", ASCENDING), ("created_at", ASCENDING)]
        )

    return _client


def get_database():
    settings = get_settings()
    client = connect_to_mongo()
    return client[settings.mongo_db_name]
