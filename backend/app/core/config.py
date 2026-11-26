"""
Centralized application settings using pydantic-settings.
"""

from pathlib import Path
import re
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlsplit

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
    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Browser frontend origins allowed to call the API.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Shared rate-limit storage (leave empty for single-process local development).
    redis_url: str = ""
    # Local OCR fallback for scanned or image-heavy PDF pages.
    ocr_languages: str = "fra+ara+eng"
    ocr_dpi: int = 250
    ocr_min_text_chars: int = 80
    ocr_tessdata: str = ""
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

    if not 150 <= settings.ocr_dpi <= 400:
        raise RuntimeError("OCR_DPI must be between 150 and 400.")
    if not 0 <= settings.ocr_min_text_chars <= 1000:
        raise RuntimeError("OCR_MIN_TEXT_CHARS must be between 0 and 1000.")
    if not re.fullmatch(r"[a-z]{3}(?:\+[a-z]{3})*", settings.ocr_languages):
        raise RuntimeError("OCR_LANGUAGES must be Tesseract language codes separated by +.")

    redis_url = settings.redis_url.strip()
    if redis_url:
        try:
            redis = urlsplit(redis_url)
            redis_port = redis.port
        except ValueError as exc:
            raise RuntimeError(
                "REDIS_URL must be a valid redis:// or rediss:// URL."
            ) from exc

        if (
            redis.scheme not in {"redis", "rediss"}
            or not redis.hostname
            or redis.fragment
            or (redis_port is not None and not 1 <= redis_port <= 65535)
        ):
            raise RuntimeError(
                "REDIS_URL must be a valid redis:// or rediss:// URL."
            )

    if settings.openrouter_api_key and not settings.openrouter_api_key.strip():
        raise RuntimeError("OPENROUTER_API_KEY cannot contain only whitespace.")

    if settings.openrouter_api_key.strip():
        if not settings.openrouter_model.strip():
            raise RuntimeError(
                "OPENROUTER_MODEL must be configured when OPENROUTER_API_KEY is set."
            )
    base_url = urlsplit(settings.openrouter_base_url.strip())
    if (
        base_url.scheme != "https"
        or not base_url.hostname
        or base_url.username
        or base_url.password
    ):
        raise RuntimeError(
            "OPENROUTER_BASE_URL must be a valid HTTPS URL."
        )
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
        "replace_with_a_random_secret_of_at_least_32_characters",
    }

    if secret.strip().lower() in forbidden_values:
        raise RuntimeError("SECRET_KEY contains an insecure placeholder.")

    if settings.jwt_algorithm != "HS256":
        raise RuntimeError("Only HS256 is supported.")

    if not 1 <= settings.access_token_expire_minutes <= 60:
        raise RuntimeError(
            "ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 60."
        )
