
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
        "gemini_api_key": "",
        "gemini_model": "gemini-3.5-flash-lite",
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


@pytest.mark.parametrize("secret", ["", "short", "your_secret_key", "CHANGE_ME", "password"])
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


def test_validate_settings_rejects_empty_gemini_model_when_key_exists(monkeypatch):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "gemini_api_key", "test-api-key")
    monkeypatch.setattr(config.settings, "gemini_model", "   ")

    with pytest.raises(RuntimeError, match="GEMINI_MODEL"):
        config.validate_settings()


def test_validate_settings_allows_optional_gemini_configuration(monkeypatch):
    set_valid_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    monkeypatch.setattr(config.settings, "gemini_model", "")

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
