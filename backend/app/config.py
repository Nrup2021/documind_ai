from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DocuMind API"
    environment: str = "development"
    debug: bool = False

    model_config = SettingsConfigDict(env_prefix="DOCUMIND_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
