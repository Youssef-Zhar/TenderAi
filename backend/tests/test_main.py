
from unittest.mock import MagicMock, patch

import redis

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app


client = TestClient(app)


def test_home_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Welcome to TenderAI",
        "status": "running",
    }


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_readiness_endpoint_when_database_is_available():
    with patch("app.main.engine.connect") as mock_connect:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
    }
    mock_connect.assert_called_once_with()


def test_readiness_endpoint_when_database_is_unavailable():
    with patch(
        "app.main.engine.connect",
        side_effect=SQLAlchemyError("Database unavailable"),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }



def test_request_id_is_returned_in_response_header():
    response = client.get("/", headers={"X-Request-ID": "trace-123_abc"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-123_abc"


def test_invalid_request_id_is_replaced():
    response = client.get("/", headers={"X-Request-ID": "invalid request id"})

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert request_id != "invalid request id"
    assert len(request_id) == 32


def test_readiness_endpoint_checks_configured_redis(monkeypatch):
    monkeypatch.setattr(
        "app.main.settings.redis_url",
        "rediss://default:secret@redis.example.com:6380/0",
    )
    redis_client = MagicMock()

    with (
        patch("app.main.engine.connect"),
        patch("app.main.redis.Redis.from_url", return_value=redis_client) as factory,
    ):
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
        "redis": "connected",
    }
    factory.assert_called_once()
    redis_client.ping.assert_called_once_with()
    redis_client.close.assert_called_once_with()


def test_readiness_endpoint_is_unavailable_when_configured_redis_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.main.settings.redis_url",
        "redis://redis.internal:6379/0",
    )
    redis_client = MagicMock()
    redis_client.ping.side_effect = redis.RedisError("connection refused")

    with (
        patch("app.main.engine.connect"),
        patch("app.main.redis.Redis.from_url", return_value=redis_client),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "connected",
        "redis": "unavailable",
    }
    redis_client.close.assert_called_once_with()
