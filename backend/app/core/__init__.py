"""
app/core/config.py
------------------
Reads environment variables once at startup using pydantic-settings.
Import `settings` anywhere in the app — never read os.getenv() directly.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class _Settings:
    """Simple settings container. Values come from .env via load_dotenv()."""

    # --- Database ---
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "tenderai_db")
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "")

    # --- OpenRouter ---
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    openrouter_model: str = os.getenv(
        "OPENROUTER_MODEL", "qwen/qwen3-8b:free"
    )


settings = _Settings()
