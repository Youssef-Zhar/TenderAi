from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import decode_access_token


def get_storage_uri(redis_url: str | None) -> str:
    """Use shared Redis storage when configured, otherwise local memory."""
    normalized_url = (redis_url or "").strip()
    return normalized_url or "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_storage_uri(settings.redis_url),
)


def get_authenticated_user_key(request: Request) -> str:
    """Use the authenticated user ID for limits, falling back to client IP."""
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme.lower() == "bearer" and token:
        payload = decode_access_token(token)
        if payload is not None:
            return f"user:{payload['sub']}"

    return get_remote_address(request)


def _handle_rate_limit_exceeded(
    request: Request,
    exc: Exception,
) -> Response:
    if not isinstance(exc, RateLimitExceeded):
        raise exc

    return _rate_limit_exceeded_handler(request, exc)


def configure_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        _handle_rate_limit_exceeded,
    )
