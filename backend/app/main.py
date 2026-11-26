
import logging
import re
import time
import uuid

import redis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.rate_limit import configure_rate_limiting
from app.core.logging_config import configure_logging
from app.core.request_size_limit import RequestBodySizeLimitMiddleware
from app.api.routes.auth import router as auth_router
from app.api.routes.tenders import router as tenders_router
from app.core.config import settings, validate_settings
from app.db.session import engine


MAX_REQUEST_BODY_SIZE = 11 * 1024 * 1024

app = FastAPI(
    title="TenderAI API",
    description="AI-powered public procurement analysis",
    version="0.1.0",
)

validate_settings()
configure_logging(settings.log_level)
configure_rate_limiting(app)

request_logger = logging.getLogger("tenderai.request")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

app.add_middleware(
    RequestBodySizeLimitMiddleware,
    max_body_size=MAX_REQUEST_BODY_SIZE,
    paths={"/api/v1/tenders/analyze-pdf"},
)

# Keep CORS outermost so browser clients also receive CORS headers on error responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    """Attach a correlation ID and log request status/duration without bodies."""
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid.uuid4().hex
    )
    request.state.request_id = request_id
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        request_logger.exception(
            "Unhandled request exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    request_logger.info(
        "HTTP request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.get("/")
def home():
    return {
        "message": "Welcome to TenderAI",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/ready")
def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "unavailable",
            },
        )

    readiness = {
        "status": "ready",
        "database": "connected",
    }

    if settings.redis_url.strip():
        redis_client = None
        try:
            redis_client = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            redis_client.ping()
        except redis.RedisError:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "database": "connected",
                    "redis": "unavailable",
                },
            )
        finally:
            if redis_client is not None:
                redis_client.close()

        readiness["redis"] = "connected"

    return readiness


app.include_router(tenders_router)
app.include_router(auth_router)
