"""
Centralized application settings using pydantic-settings.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "tenderai_db"
    db_user: str = ""
    db_password: str = ""
    db_migration_user: str = ""
    db_migration_password: str = ""

    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    # Authentication / JWT
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


settings = Settings()


def validate_settings() -> None:
    """Validate critical application settings before startup."""

    # Database
    required_db_values = {
        "DB_HOST": settings.db_host,
        "DB_NAME": settings.db_name,
        "DB_USER": settings.db_user,
        "DB_PASSWORD": settings.db_password,
    }

    for name, value in required_db_values.items():
        if not value or not value.strip():
            raise RuntimeError(f"{name} must be configured.")

    if not 1 <= settings.db_port <= 65535:
        raise RuntimeError("DB_PORT must be between 1 and 65535.")

    # JWT
    secret = settings.secret_key

    if not secret or len(secret) < 32:
        raise RuntimeError(
            "SECRET_KEY must contain at least 32 characters."
        )

    forbidden_values = {
        "your_secret_key",
        "change_me",
        "changeme",
        "secret",
        "password",
    }

    if secret.strip().lower() in forbidden_values:
        raise RuntimeError("SECRET_KEY contains an insecure placeholder.")

    if settings.jwt_algorithm != "HS256":
        raise RuntimeError("Only HS256 is supported.")

    if not 1 <= settings.access_token_expire_minutes <= 60:
        raise RuntimeError(
            "ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 60."
        )

    # Gemini is optional, but its model must be configured when a key exists.
    if settings.gemini_api_key and not settings.gemini_model.strip():
        raise RuntimeError(
            "GEMINI_MODEL must be configured when GEMINI_API_KEY is set."
        )