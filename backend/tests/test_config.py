
import pytest

from app.core import config


def set_valid_settings(monkeypatch):
    valid_values = {
        "db_host": "127.0.0.1",
        "db_port": 3306,
        "db_name": "tenderai_test",
        "db_user": "test_user",
        "db_password": "test_password",
        "secret_key": "A" * 64,
        "jwt_algorithm": "HS256",
        "access_token_expire_minutes": 30,
        "openrouter_api_key": "",
        "openrouter_model": "",
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "redis_url": "",
    }

    for name, value in valid_values.items():
        monkeypatch.setattr(config.settings, name, value)


def test_validate_settings_accepts_valid_configuration(monkeypatch):
    set_valid_settings(monkeypatch)

    config.validate_settings()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("db_host", "", "DB_HOST"),
        ("db_host", "   ", "DB_HOST"),
        ("db_name", "", "DB_NAME"),
        ("db_user", "", "DB_USER"),
        ("db_user", "   ", "DB_USER"),
        ("db_password", "", "DB_PASSWORD"),
        ("db_password", "   ", "DB_PASSWORD"),
    ],
)
def test_validate_settings_rejects_missing_database_values(
    monkeypatch, field, value, message
):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, field, value)

    with pytest.raises(RuntimeError, match=message):
        config.validate_settings()


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_validate_settings_rejects_invalid_database_port(monkeypatch, port):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "db_port", port)

    with pytest.raises(RuntimeError, match="DB_PORT"):
        config.validate_settings()


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "short",
        "your_secret_key",
        "CHANGE_ME",
        "password",
        "replace_with_a_random_secret_of_at_least_32_characters",
    ],
)
def test_validate_settings_rejects_weak_secret(monkeypatch, secret):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "secret_key", secret)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.validate_settings()


def test_validate_settings_rejects_unsupported_algorithm(monkeypatch):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "jwt_algorithm", "HS512")

    with pytest.raises(RuntimeError, match="Only HS256"):
        config.validate_settings()


@pytest.mark.parametrize("minutes", [0, -1, 61])
def test_validate_settings_rejects_invalid_token_expiration(monkeypatch, minutes):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(
        config.settings, "access_token_expire_minutes", minutes
    )

    with pytest.raises(RuntimeError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        config.validate_settings()


def test_validate_settings_accepts_expiration_boundaries(monkeypatch):
    set_valid_settings(monkeypatch)

    for minutes in (1, 60):
        monkeypatch.setattr(
            config.settings, "access_token_expire_minutes", minutes
        )
        config.validate_settings()

def test_validate_settings_rejects_empty_openrouter_model_when_key_exists(
    monkeypatch,
):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(
        config.settings, "openrouter_api_key", "test-api-key"
    )
    monkeypatch.setattr(config.settings, "openrouter_model", "   ")

    with pytest.raises(RuntimeError, match="OPENROUTER_MODEL"):
        config.validate_settings()


def test_validate_settings_allows_optional_openrouter_configuration(
    monkeypatch,
):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "openrouter_api_key", "")
    monkeypatch.setattr(config.settings, "openrouter_model", "")

    config.validate_settings()

def test_validate_settings_rejects_placeholder_secret_with_spaces(monkeypatch):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(
        config.settings,
        "secret_key",
        " " * 20 + "password" + " " * 20,
    )

    with pytest.raises(RuntimeError, match="insecure placeholder"):
        config.validate_settings()
@pytest.mark.parametrize(
    "base_url",
    [
        "http://openrouter.ai/api/v1",
        "not-a-url",
        "https://user:password@openrouter.ai/api/v1",
    ],
)
def test_validate_settings_rejects_unsafe_openrouter_base_url(
    monkeypatch, base_url
):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(
        config.settings, "openrouter_api_key", "test-api-key"
    )
    monkeypatch.setattr(
        config.settings, "openrouter_model", "test/model"
    )
    monkeypatch.setattr(
        config.settings, "openrouter_base_url", base_url
    )

    with pytest.raises(RuntimeError, match="valid HTTPS URL"):
        config.validate_settings()


def test_validate_settings_rejects_whitespace_openrouter_key(monkeypatch):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(
        config.settings, "openrouter_api_key", "   "
    )

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        config.validate_settings()


@pytest.mark.parametrize(
    "redis_url",
    [
        "http://localhost:6379",
        "not-a-redis-url",
        "redis://",
        "rediss://",
        "redis://localhost:6379#unsupported-fragment",
        "redis://localhost:99999",
        "redis://[invalid-ipv6",
    ],
)
def test_validate_settings_rejects_invalid_redis_url(monkeypatch, redis_url):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "redis_url", redis_url)

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        config.validate_settings()


@pytest.mark.parametrize(
    "redis_url",
    [
        "redis://localhost:6379/0",
        "rediss://default:secret@redis.example.com:6380/0",
    ],
)
def test_validate_settings_accepts_valid_redis_url(monkeypatch, redis_url):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "redis_url", redis_url)

    config.validate_settings()
