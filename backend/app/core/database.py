"""Centralizamos un cliente de Mongodb reutilizable"""
from pymongo import MongoClient
from app.core.config import get_settings

_client: MongoClient | None = None


def connect_to_mongo() -> MongoClient:
    global _client

    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongodb_url)

    return _client


def get_database():
    settings = get_settings()
    client = connect_to_mongo()
    return client[settings.mongo_db_name]