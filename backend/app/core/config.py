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
    spoonacular_base_url: str = Field(default="https://api.spoonacular.com", validation_alias="SPOONACULAR_BASE_URL")
    spoonacular_timeout_seconds: int = Field(default=10, validation_alias="SPOONACULAR_TIMEOUT_SECONDS")
    spoonacular_rate_limit_cooldown_seconds: int = Field(default=90, validation_alias="SPOONACULAR_RATE_LIMIT_COOLDOWN_SECONDS")
    spoonacular_user_agent: str = Field(
        default="Fibrito/0.1 (backend integration; contact=local)",
        validation_alias="SPOONACULAR_USER_AGENT",
    )
    spoonacular_generation_enrichment_enabled: bool = Field(default=True, validation_alias="SPOONACULAR_GENERATION_ENRICHMENT_ENABLED")
    prefer_spoonacular_foods: bool = Field(default=False, validation_alias="PREFER_SPOONACULAR_FOODS")
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

    @property
    def spoonacular_enabled(self) -> bool:
        return bool(self.spoonacular_api_key.strip())

    @property
    def food_resolution_strategy(self) -> str:
        if self.prefer_spoonacular_foods:
            return "spoonacular_first_with_cache_fallback"

        return "internal_catalog_with_optional_spoonacular_enrichment"


@lru_cache
def get_settings() -> Settings:
    return Settings()
