
import jwt
import pytest

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from argon2 import PasswordHasher

from app.core import security


def test_hash_password_and_verify_password():
    password = "StrongPassword123"

    hashed = security.hash_password(password)

    assert hashed != password
    assert security.verify_password(password, hashed)
    assert not security.verify_password("WrongPassword123", hashed)


def test_hash_password_rejects_empty_password():
    with pytest.raises(ValueError, match="Password cannot be empty"):
        security.hash_password("")


def test_verify_password_rejects_invalid_hash():
    assert not security.verify_password("password", "invalid-hash")


def test_password_needs_rehash_returns_false_for_current_hash():
    hashed = security.hash_password("StrongPassword123")

    assert not security.password_needs_rehash(hashed)


def test_password_needs_rehash_returns_true_for_invalid_hash():
    assert security.password_needs_rehash("invalid-hash")


def test_create_and_decode_access_token():
    token = security.create_access_token(123)

    payload = security.decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == "123"
    assert "iat" in payload
    assert "exp" in payload


def test_create_access_token_rejects_invalid_user_id():
    with pytest.raises(ValueError, match="positive integer"):
        security.create_access_token(0)


def test_create_access_token_rejects_reserved_claims():
    with pytest.raises(ValueError, match="reserved JWT claims"):
        security.create_access_token(123, {"sub": "456"})


def test_decode_access_token_rejects_invalid_signature():
    token = security.create_access_token(123)

    with patch.object(security, "_SECRET", "X" * 64):
        assert security.decode_access_token(token) is None


def test_decode_access_token_rejects_invalid_token():
    assert security.decode_access_token("not-a-valid-token") is None


def test_decode_access_token_rejects_invalid_subject():
    payload = {
        "sub": "0",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }

    token = jwt.encode(
        payload,
        security._SECRET,
        algorithm=security._ALGORITHM,
    )

    assert security.decode_access_token(token) is None


def test_validate_jwt_settings_rejects_short_secret():
    with patch.object(security, "_SECRET", "short"):
        with pytest.raises(RuntimeError, match="32 characters"):
            security._validate_jwt_settings()


def test_validate_jwt_settings_rejects_unsupported_algorithm():
    with patch.object(security, "_ALGORITHM", "HS512"):
        with pytest.raises(RuntimeError, match="Only HS256 is supported"):
            security._validate_jwt_settings()


def test_validate_jwt_settings_rejects_zero_expiration():
    with patch.object(security, "_EXPIRE_MINUTES", 0):
        with pytest.raises(RuntimeError, match="greater than zero"):
            security._validate_jwt_settings()


def test_validate_jwt_settings_rejects_negative_expiration():
    with patch.object(security, "_EXPIRE_MINUTES", -5):
        with pytest.raises(RuntimeError, match="greater than zero"):
            security._validate_jwt_settings()


def test_decode_access_token_rejects_expired_token():
    payload = {
        "sub": "123",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
    }

    token = jwt.encode(
        payload,
        security._SECRET,
        algorithm=security._ALGORITHM,
    )

    assert security.decode_access_token(token) is None


def test_decode_access_token_rejects_missing_claims():
    token = jwt.encode(
        {"sub": "123"},
        security._SECRET,
        algorithm=security._ALGORITHM,
    )

    assert security.decode_access_token(token) is None


def test_create_access_token_accepts_custom_claims():
    token = security.create_access_token(123, {"role": "admin"})

    payload = security.decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == "123"
    assert payload["role"] == "admin"



def test_decode_access_token_rejects_non_string_subject():
    with patch.object(
        security.jwt,
        "decode",
        return_value={"sub": 123},
    ):
        assert security.decode_access_token("fake-token") is None
