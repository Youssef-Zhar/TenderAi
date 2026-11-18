
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.rate_limit import configure_rate_limiting
from app.core.request_size_limit import RequestBodySizeLimitMiddleware
from app.api.routes.auth import router as auth_router
from app.api.routes.tenders import router as tenders_router
from app.core.config import validate_settings
from app.db.session import engine


MAX_REQUEST_BODY_SIZE = 11 * 1024 * 1024

app = FastAPI(
    title="TenderAI API",
    description="AI-powered public procurement analysis",
    version="0.1.0",
)

validate_settings()
configure_rate_limiting(app)

app.add_middleware(
    RequestBodySizeLimitMiddleware,
    max_body_size=MAX_REQUEST_BODY_SIZE,
    paths={"/api/v1/tenders/analyze-pdf"},
)


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

    return {
        "status": "ready",
        "database": "connected",
    }


app.include_router(tenders_router)
app.include_router(auth_router)
