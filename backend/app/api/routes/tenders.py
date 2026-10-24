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
from pathlib import Path

import logging

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.tender import Tender
from app.models.tender_condition import TenderCondition
from app.models.tender_document import TenderDocument
from app.models.tender_criterion import TenderCriterion
from app.models.tender_evidence import TenderEvidence
from app.schemas.analysis import (
    AnalysisMetadata,
    AnalysisResult,
    AnalyzeResponse,
    StructuredTenderAnalysis,
)
from app.schemas.tender import TenderCreate, TenderResponse
from app.services.ai_analyzer import (
    AIConnectionError,
    AIStatusError,
    AITimeoutError,
    analysis_status,
    analyze_tender,
    build_analysis_metadata,
    extract_structured_tender,
)
from app.services.deadline_parser import parse_deadline

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/tenders",
    tags=["Tenders"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_DEADLINE_LABELS = (
    "date limite de remise des offres",
    "date limite de réception des offres",
    "date limite de depot des offres",
    "date limite de dépôt des offres",
    "date limite de soumission",
    "dernier delai de remise des offres",
    "dernier délai de remise des offres",
)


def _parse_deadline_from_document(text: str):
    """Extract a deadline only from lines explicitly labelled as submission deadlines."""
    for line in text.splitlines():
        normalized_line = line.casefold()

        if any(label in normalized_line for label in _DEADLINE_LABELS):
            parsed = parse_deadline(line)
            if parsed is not None:
                return parsed

    return None


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
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    """Analyse a PDF and save its structured data to the database."""

    # 1. Validate file extension
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a PDF file.",
        )

    # 2. Validate file size
    content = await file.read(MAX_FILE_SIZE + 1)

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The PDF must not exceed 10 MB.",
        )

    # 3. Validate PDF signature
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file does not appear to be a valid PDF.",
        )

    # 4. Extract text from PDF pages
    try:
        with fitz.open(stream=BytesIO(content), filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password-protected PDFs are not supported yet.",
                )

            pages = [
                {
                    "page": number,
                    "text": page.get_text("text").strip(),
                }
                for number, page in enumerate(pdf, start=1)
            ]

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read this PDF. It may be corrupted.",
        ) from exc

    pages_with_text = sum(1 for page in pages if page["text"])

    # 5. Scanned PDF detection
    if pages_with_text == 0:
        return AnalyzeResponse(
            filename=file.filename,
            page_count=len(pages),
            pages_with_text=0,
            analysis=AnalysisResult(
                status="ocr_required",
                model=settings.gemini_model,
                report=(
                    "No selectable text was found. "
                    "OCR processing is required but not yet supported."
                ),
            ),
        )

    # 6. Prepare text with page numbers
    document_text = "\n\n".join(
        f"--- Page {page['page']} ---\n{page['text']}"
        for page in pages
        if page["text"]
    )

    # 7. Ask AI to generate the report and structured data.
    # The report is generated first so a valid report is never discarded when
    # structured extraction degrades or fails.
    metadata = AnalysisMetadata()

    try:
        report = await analyze_tender(document_text, metadata=metadata)

    except AIConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot connect to the Gemini API. Check your internet connection.",
        ) from exc

    except AITimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Gemini took too long to respond.",
        ) from exc

    except AIStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini returned HTTP {exc.status_code}.",
        ) from exc

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    try:
        structured = await extract_structured_tender(
            document_text, metadata=metadata
        )
    except (AIConnectionError, AITimeoutError, AIStatusError, ValueError, RuntimeError) as exc:
        # Structured extraction failed but the report is valid: degrade rather
        # than failing the whole request.
        logger.warning("Structured extraction failed: %s", exc)
        metadata.structured_failed = True
        structured = StructuredTenderAnalysis()

    build_analysis_metadata(metadata, structured)
    analysis_status_value = analysis_status(metadata)

    # 8. Parse the deadline only when its format is recognized
    parsed_deadline = parse_deadline(structured.tender.deadline)
    if parsed_deadline is None:
        parsed_deadline = _parse_deadline_from_document(document_text)
    # The existing database requires both title and description.
    title = (
        structured.tender.title or Path(file.filename).stem
    )[:200]

    tender = Tender(
        title=title,
        description=report,
        estimated_budget=structured.tender.estimated_budget,
        deadline=parsed_deadline,
    )

    # 9. Save the tender and its related records atomically
    try:
        db.add(tender)
        db.flush()

        for item in structured.conditions:
            db.add(
                TenderCondition(
                    tender_id=tender.id,
                    condition_type=item.condition_type,
                    description=item.description,
                )
            )

        for item in structured.documents:
            db.add(
                TenderDocument(
                    tender_id=tender.id,
                    name=item.name,
                    description=item.description,
                    is_mandatory=item.is_mandatory,
                )
            )

        for item in structured.criteria:
            db.add(
                TenderCriterion(
                    tender_id=tender.id,
                    name=item.name,
                    description=item.description,
                    weight=item.weight,
                )
            )

        # Persist only evidence returned by the verification pipeline.
        # Scalar fields are never turned into synthetic evidence rows, and
        # items without a verified source quote and page are skipped.
        for item in structured.evidence:
            if not item.source_text or item.page_number is None:
                continue
            db.add(
                TenderEvidence(
                    tender_id=tender.id,
                    field_name=item.field_name,
                    extracted_value=item.extracted_value,
                    page_number=item.page_number,
                    source_text=item.source_text,
                )
            )

        db.commit()
        db.refresh(tender)

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the analysis to the database.",
        ) from exc

    # 10. Return the analysis and the saved record ID
    return AnalyzeResponse(
        filename=file.filename,
        page_count=len(pages),
        pages_with_text=pages_with_text,
        tender_id=tender.id,
        analysis=AnalysisResult(
            status=analysis_status_value,
            model=settings.gemini_model,
            report=report,
            structured_data=structured,
            metadata=metadata,
        ),
    )
