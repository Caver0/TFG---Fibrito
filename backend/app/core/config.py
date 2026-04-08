"""Centralizamos la configuración del proyecto"""


from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fibrito"

    mongodb_url: str = Field(validation_alias="MONGODB_URL")
    mongo_db_name: str = Field(validation_alias="MONGO_DB_NAME")

    jwt_secret_key: str = Field(validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=120, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    spoonacular_api_key: str = Field(default="", validation_alias="SPOONACULAR_API_KEY")
    frontend_url: str = Field(default="http://localhost:5173", validation_alias="FRONTEND_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            self.frontend_url,
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
