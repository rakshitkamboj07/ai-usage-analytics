from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
    )

    # Application
    APP_NAME: str = "AI Usage Analytics"

    # Database
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # Security
    SECRET_KEY: str

    # Microsoft Graph
    GRAPH_TENANT_ID: str | None = None
    GRAPH_CLIENT_ID: str | None = None
    GRAPH_CLIENT_SECRET: str | None = None

    GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"

    # Future Settings
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = Settings()