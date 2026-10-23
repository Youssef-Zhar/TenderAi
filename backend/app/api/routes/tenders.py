"""
app/api/routes/tenders.py
--------------------------
All HTTP routes for the /api/v1/tenders prefix.

Routes
------
POST   /api/v1/tenders/             — create a tender record manually
GET    /api/v1/tenders/             — list tenders (paginated)
GET    /api/v1/tenders/{tender_id}  — retrieve one tender
PUT    /api/v1/tenders/{tender_id}  — update a tender
DELETE /api/v1/tenders/{tender_id}  — delete a tender
POST   /api/v1/tenders/analyze-pdf  — upload a PDF and analyse it with AI
"""

from io import BytesIO

import fitz  # PyMuPDF
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.tender import Tender
from app.schemas.analysis import AnalysisResult, AnalyzeResponse
from app.schemas.tender import TenderCreate, TenderResponse
from app.services.ai_analyzer import analyze_tender

router = APIRouter(
    prefix="/api/v1/tenders",
    tags=["Tenders"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, tender_id: int) -> Tender:
    """Return a Tender by id or raise HTTP 404."""
    tender = db.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender {tender_id} not found.",
        )
    return tender


# ── CRUD routes ───────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=TenderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tender record",
)
def create_tender(
    payload: TenderCreate,
    db: Session = Depends(get_db),
) -> TenderResponse:
    """
    Manually create a new tender record in the database.

    Use this endpoint to store tenders that were not extracted from a PDF,
    or to seed test data.
    """
    tender = Tender(
        title=payload.title,
        description=payload.description,
        estimated_budget=payload.estimated_budget,
        deadline=payload.deadline,
    )
    db.add(tender)
    db.commit()
    db.refresh(tender)
    return TenderResponse.model_validate(tender)


@router.get(
    "/",
    response_model=list[TenderResponse],
    status_code=status.HTTP_200_OK,
    summary="List all tenders",
)
def list_tenders(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[TenderResponse]:
    """
    Return a paginated list of tender records.

    Parameters
    ----------
    skip  : Number of records to skip (offset). Default 0.
    limit : Maximum number of records to return. Default 20, max 100.
    """
    if limit > 100:
        limit = 100
    tenders = db.query(Tender).offset(skip).limit(limit).all()
    return [TenderResponse.model_validate(t) for t in tenders]


@router.get(
    "/{tender_id}",
    response_model=TenderResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a single tender",
)
def get_tender(
    tender_id: int,
    db: Session = Depends(get_db),
) -> TenderResponse:
    """Return a single tender by its database id."""
    tender = _get_or_404(db, tender_id)
    return TenderResponse.model_validate(tender)


@router.put(
    "/{tender_id}",
    response_model=TenderResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a tender",
)
def update_tender(
    tender_id: int,
    payload: TenderCreate,
    db: Session = Depends(get_db),
) -> TenderResponse:
    """
    Replace the fields of an existing tender record.

    All fields in the request body are applied.  Partial updates (PATCH)
    are not supported yet.
    """
    tender = _get_or_404(db, tender_id)
    tender.title = payload.title
    tender.description = payload.description
    tender.estimated_budget = payload.estimated_budget
    tender.deadline = payload.deadline
    db.commit()
    db.refresh(tender)
    return TenderResponse.model_validate(tender)


@router.delete(
    "/{tender_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tender",
)
def delete_tender(
    tender_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Permanently delete a tender record. This action cannot be undone."""
    tender = _get_or_404(db, tender_id)
    db.delete(tender)
    db.commit()


# ── PDF Analysis route ────────────────────────────────────────────────────────

@router.post(
    "/analyze-pdf",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload a PDF and analyse it with AI",
)
async def analyze_pdf(
    file: UploadFile = File(...),
) -> AnalyzeResponse:
    """
    Upload a PDF tender document and receive an AI-generated analysis.

    Steps performed:
    1. Validate file type (must be PDF) and size (max 10 MB).
    2. Extract text from every page with PyMuPDF.
    3. Detect scanned PDFs with no selectable text (OCR required).
    4. Send the extracted text to OpenRouter for structured analysis.
    5. Return the analysis result.

    The analysis is NOT automatically saved to the database.
    Use POST /api/v1/tenders/ if you want to store the record afterwards.
    """
    # 1. Validate file extension
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a PDF file.",
        )

    # 2. Read and check file size (read one extra byte to detect oversize)
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The PDF must not exceed 10 MB.",
        )

    # 3. Check PDF magic bytes
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file does not appear to be a valid PDF.",
        )

    # 4. Extract text with PyMuPDF
    try:
        with fitz.open(stream=BytesIO(content), filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password-protected PDFs are not supported yet.",
                )

            pages = [
                {
                    "page": page_number,
                    "text": page.get_text("text").strip(),
                }
                for page_number, page in enumerate(pdf, start=1)
            ]

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read this PDF. It may be corrupted.",
        ) from exc

    pages_with_text = sum(1 for p in pages if p["text"])

    # 5. Detect scanned PDF (no extractable text)
    if pages_with_text == 0:
        return AnalyzeResponse(
            filename=file.filename,
            page_count=len(pages),
            pages_with_text=0,
            analysis=AnalysisResult(
                status="ocr_required",
                model=settings.openrouter_model,
                report=(
                    "No selectable text was found in this PDF. "
                    "It is likely a scanned document. "
                    "OCR processing is required but not yet supported."
                ),
            ),
        )

    # 6. Build page-marked text and call AI analyzer
    document_text = "\n\n".join(
        f"--- Page {p['page']} ---\n{p['text']}"
        for p in pages
        if p["text"]
    )

    try:
        report = await analyze_tender(document_text)

    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot connect to OpenRouter. Check your internet connection.",
        ) from exc

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="OpenRouter took too long to respond. Try again with a smaller document.",
        ) from exc

    except httpx.HTTPStatusError as exc:
        # Surface the HTTP status from OpenRouter for easier debugging
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenRouter returned HTTP {exc.response.status_code}. "
                   "Check your API key and model name in .env.",
        ) from exc

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return AnalyzeResponse(
        filename=file.filename,
        page_count=len(pages),
        pages_with_text=pages_with_text,
        analysis=AnalysisResult(
            status="analysis_completed",
            model=settings.openrouter_model,
            report=report,
        ),
    )
