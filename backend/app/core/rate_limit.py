from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)


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