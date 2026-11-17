from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.security import decode_access_token


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
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