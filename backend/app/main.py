
from fastapi import FastAPI

from app.api.routes.tenders import router as tenders_router
from app.db.base import Base
from app.db.session import engine
from app.models.tender import Tender

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TenderAI API",
    description="AI-powered public procurement analysis",
    version="0.1.0",
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


app.include_router(tenders_router)
