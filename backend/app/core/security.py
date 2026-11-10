
"""
Password hashing (Argon2id) and JWT token management.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from app.core.config import settings


# --- Password hashing: Argon2id ---

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except (VerificationError, InvalidHashError):
        return True


# --- JWT configuration ---

_ALGORITHM = settings.jwt_algorithm
_SECRET = settings.secret_key
_EXPIRE_MINUTES = settings.access_token_expire_minutes

_RESERVED_CLAIMS = {"sub", "iat", "exp"}


def _validate_jwt_settings() -> None:
    if not _SECRET or len(_SECRET) < 32:
        raise RuntimeError(
            "SECRET_KEY must be configured with at least 32 characters."
        )

    if _ALGORITHM != "HS256":
        raise RuntimeError("Only HS256 is supported by this configuration.")

    if _EXPIRE_MINUTES <= 0:
        raise RuntimeError(
            "ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero."
        )


def create_access_token(
    user_id: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    _validate_jwt_settings()

    if user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    if extra_claims and _RESERVED_CLAIMS.intersection(extra_claims):
        raise ValueError("extra_claims cannot override reserved JWT claims.")

    now = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=_EXPIRE_MINUTES),
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    _validate_jwt_settings()

    try:
        payload = jwt.decode(
            token,
            _SECRET,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )

        if not isinstance(payload.get("sub"), str):
            return None

        if not payload["sub"].isdigit() or int(payload["sub"]) <= 0:
            return None

        return payload

    except jwt.PyJWTError:
        return None
