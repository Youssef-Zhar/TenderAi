import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError

from app.api.routes.auth import router as auth_router
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.models.user import User

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.rate_limit import configure_rate_limiting, limiter

from argon2 import PasswordHasher
from app.core.security import password_needs_rehash

@pytest.fixture
def auth_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    # Create ONLY the users table in isolated SQLite.
    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__],
    )

    db = TestingSessionLocal()

    app = FastAPI()
    configure_rate_limiting(app)
    limiter.reset()
    app.include_router(auth_router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(
            bind=engine,
            tables=[User.__table__],
        )
        engine.dispose()


def test_register_success(auth_env):
    client, db = auth_env

    response = client.post(
        "/auth/register",
        json={
            "email": "  TEST@example.com  ",
            "password": "StrongPassword123",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
    assert "hashed_password" not in response.json()

    user = db.scalar(
        select(User).where(User.email == "test@example.com")
    )

    assert user is not None
    assert user.hashed_password != "StrongPassword123"
    assert user.hashed_password.startswith("$argon2")


def test_register_duplicate_email(auth_env):
    client, _ = auth_env

    payload = {
        "email": "test@example.com",
        "password": "StrongPassword123",
    }

    first = client.post("/auth/register", json=payload)
    second = client.post("/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_login_success_and_me(auth_env):
    client, _ = auth_env

    client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "StrongPassword123",
        },
    )

    login_response = client.post(
        "/auth/login",
        json={
            "email": "TEST@example.com",
            "password": "StrongPassword123",
        },
    )

    assert login_response.status_code == 200

    token_data = login_response.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["access_token"]

    me_response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token_data['access_token']}"
        },
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "test@example.com"
    assert "hashed_password" not in me_response.json()


def test_login_wrong_password(auth_env):
    client, _ = auth_env

    client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "StrongPassword123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPassword123",
        },
    )

    assert response.status_code == 401


def test_me_without_token(auth_env):
    client, _ = auth_env

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_with_invalid_token(auth_env):
    client, _ = auth_env

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401


def test_inactive_user_cannot_login_or_access_me(auth_env):
    client, db = auth_env

    user = User(
        email="inactive@example.com",
        hashed_password=hash_password("StrongPassword123"),
        is_active=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    login_response = client.post(
        "/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "StrongPassword123",
        },
    )

    assert login_response.status_code == 403

    token = create_access_token(user.id)

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 401


def make_test_token(
    sub: str,
    iat: datetime,
    exp: datetime,
    secret: str | None = None,
) -> str:
    payload = {
        "sub": sub,
        "iat": iat,
        "exp": exp,
    }

    return jwt.encode(
        payload,
        secret or settings.secret_key,
        algorithm="HS256",
    )


def test_me_with_expired_token(auth_env):
    client, _ = auth_env
    now = datetime.now(timezone.utc)

    token = make_test_token(
        sub="1",
        iat=now - timedelta(hours=2),
        exp=now - timedelta(hours=1),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_me_with_wrong_signature(auth_env):
    client, _ = auth_env
    now = datetime.now(timezone.utc)

    token = make_test_token(
        sub="1",
        iat=now,
        exp=now + timedelta(minutes=30),
        secret="wrong-secret-key-that-is-not-valid",
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_me_with_invalid_subject(auth_env):
    client, _ = auth_env
    now = datetime.now(timezone.utc)

    token = make_test_token(
        sub="not-a-user-id",
        iat=now,
        exp=now + timedelta(minutes=30),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_me_with_future_issued_token(auth_env):
    client, _ = auth_env
    now = datetime.now(timezone.utc)

    token = make_test_token(
        sub="1",
        iat=now + timedelta(hours=1),
        exp=now + timedelta(hours=2),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401

def test_login_rate_limit(auth_env):
    client, db = auth_env

    user = User(
        email="ratelimit@example.com",
        hashed_password=hash_password("StrongPassword123"),
        is_active=True,
    )
    db.add(user)
    db.commit()

    payload = {
        "email": "ratelimit@example.com",
        "password": "WrongPassword123",
    }

    for _ in range(5):
        response = client.post("/auth/login", json=payload)
        assert response.status_code == 401

    response = client.post("/auth/login", json=payload)
    assert response.status_code == 429


def test_register_rate_limit(auth_env):
    client, _ = auth_env

    for i in range(3):
        response = client.post(
            "/auth/register",
            json={
                "email": f"user{i}@example.com",
                "password": "StrongPassword123",
            },
        )
        assert response.status_code == 201

    response = client.post(
        "/auth/register",
        json={
            "email": "user4@example.com",
            "password": "StrongPassword123",
        },
    )

    assert response.status_code == 429


@pytest.mark.parametrize(
    "password",
    [
        "Short123",
        "password123456",
        "123456789012",
        "qwerty123456",
    ],
)
def test_register_rejects_weak_passwords(auth_env, password):
    client, _ = auth_env

    response = client.post(
        "/auth/register",
        json={
            "email": "weak-password@example.com",
            "password": password,
        },
    )

    assert response.status_code == 422


def test_register_accepts_long_password(auth_env):
    client, _ = auth_env

    response = client.post(
        "/auth/register",
        json={
            "email": "strong-password@example.com",
            "password": "MyVeryStrongPassword2026!",
        },
    )

    assert response.status_code == 201

def test_login_rehashes_old_password_hash(auth_env):
    client, db = auth_env

    password = "StrongPassword123"

    old_hasher = PasswordHasher(
        time_cost=1,
        memory_cost=8192,
        parallelism=1,
    )
    old_hash = old_hasher.hash(password)

    user = User(
        email="old-hash@example.com",
        hashed_password=old_hash,
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/auth/login",
        json={
            "email": "old-hash@example.com",
            "password": password,
        },
    )

    assert response.status_code == 200
    assert "access_token" in response.json()

    db.refresh(user)

    assert user.hashed_password != old_hash
    assert not password_needs_rehash(user.hashed_password)


def test_register_rolls_back_on_integrity_error(auth_env, monkeypatch):
    client, db = auth_env

    rollback_calls = []
    original_rollback = db.rollback

    def failing_commit():
        raise IntegrityError(
            "INSERT INTO users",
            {},
            Exception("Duplicate email"),
        )

    def tracked_rollback():
        rollback_calls.append(True)
        return original_rollback()

    monkeypatch.setattr(db, "commit", failing_commit)
    monkeypatch.setattr(db, "rollback", tracked_rollback)

    response = client.post(
        "/auth/register",
        json={
            "email": "integrity@example.com",
            "password": "StrongPassword123",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered."
    assert len(rollback_calls) == 1


def test_register_rolls_back_on_unexpected_exception(auth_env, monkeypatch):
    client, db = auth_env

    rollback_calls = []
    original_rollback = db.rollback

    def failing_commit():
        raise RuntimeError("Unexpected database failure")

    def tracked_rollback():
        rollback_calls.append(True)
        return original_rollback()

    monkeypatch.setattr(db, "commit", failing_commit)
    monkeypatch.setattr(db, "rollback", tracked_rollback)

    with pytest.raises(RuntimeError, match="Unexpected database failure"):
        client.post(
            "/auth/register",
            json={
                "email": "error@example.com",
                "password": "StrongPassword123",
            },
        )

    assert len(rollback_calls) == 1
