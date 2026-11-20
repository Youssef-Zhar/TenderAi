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
from time import perf_counter

import logging

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, Query, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.models.user import User

from app.core.config import settings
from app.core.rate_limit import get_authenticated_user_key, limiter
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
from app.services.deadline_parser import parse_deadline, parse_deadline_time
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/tenders",
    tags=["Tenders"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_PAGES = 200
MAX_EXTRACTED_TEXT_CHARS = 300_000
_DEADLINE_LABELS = (
    "date limite de remise des offres",
    "date limite de réception des offres",
    "date limite de depot des offres",
    "date limite de dépôt des offres",
    "date limite de soumission",
    "dernier delai de remise des offres",
    "dernier délai de remise des offres",
)


def _deadline_line_from_document(text: str) -> str | None:
    """Return the first explicitly labelled submission-deadline line."""
    for line in text.splitlines():
        normalized_line = line.casefold()
        if any(label in normalized_line for label in _DEADLINE_LABELS):
            if parse_deadline(line) is not None:
                return line
    return None


def _parse_deadline_from_document(text: str):
    """Extract the date from an explicitly labelled submission deadline."""
    line = _deadline_line_from_document(text)
    return parse_deadline(line) if line is not None else None


def _parse_deadline_time_from_document(text: str):
    """Extract the time from an explicitly labelled submission deadline."""
    line = _deadline_line_from_document(text)
    return parse_deadline_time(line) if line is not None else None


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_or_404(
    db: Session,
    tender_id: int,
    current_user: User,
) -> Tender:
    """Return the user's Tender or raise HTTP 404."""

    tender = (
        db.query(Tender)
        .filter(
            Tender.id == tender_id,
            Tender.owner_id == current_user.id,
        )
        .first()
    )

    if tender is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found.",
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
    current_user: User = Depends(get_current_user),
) -> TenderResponse:
    """
    Manually create a new tender record in the database.

    Use this endpoint to store tenders that were not extracted from a PDF,
    or to seed test data.
    """
    tender = Tender(
        owner_id=current_user.id,
        title=payload.title,
        description=payload.description,
        estimated_budget=payload.estimated_budget,
        currency=payload.currency,
        deadline=payload.deadline,
        deadline_time=payload.deadline_time,
        deadline_text=payload.deadline_text,
    )

    try:
        db.add(tender)
        db.commit()
        db.refresh(tender)
    except Exception:
        db.rollback()
        raise

    return TenderResponse.model_validate(tender)


@router.get(
    "/",
    response_model=list[TenderResponse],
    status_code=status.HTTP_200_OK,
    summary="List all tenders",
)
def list_tenders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TenderResponse]:
    """Return only the authenticated user's tenders."""

    tenders = (
        db.query(Tender)
        .filter(Tender.owner_id == current_user.id)
        .order_by(Tender.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

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
    current_user: User = Depends(get_current_user),
) -> TenderResponse:
    """Return one tender belonging to the authenticated user."""

    tender = _get_or_404(db, tender_id, current_user)
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
    current_user: User = Depends(get_current_user),
) -> TenderResponse:
    """
    Replace the fields of an existing tender record.

    All fields in the request body are applied. Partial updates (PATCH)
    are not supported yet.
    """
    tender = _get_or_404(db, tender_id, current_user)

    try:
        tender.title = payload.title
        tender.description = payload.description
        tender.estimated_budget = payload.estimated_budget
        tender.currency = payload.currency
        tender.deadline = payload.deadline
        tender.deadline_time = payload.deadline_time
        tender.deadline_text = payload.deadline_text



        db.commit()
        db.refresh(tender)
    except Exception:
        db.rollback()
        raise

    return TenderResponse.model_validate(tender)

@router.delete(
    "/{tender_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tender",
)
def delete_tender(
    tender_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Permanently delete a tender record. This action cannot be undone."""
    tender = _get_or_404(db, tender_id, current_user)

    try:
        db.delete(tender)
        db.commit()
    except Exception:
        db.rollback()
        raise



# ── PDF Analysis route ────────────────────────────────────────────────────────

@router.post(
    "/analyze-pdf",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload a PDF and analyse it with AI",
)
@limiter.limit("3/hour", key_func=get_authenticated_user_key)
async def analyze_pdf(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyzeResponse:
    """Analyse a PDF and save its structured data to the database."""
    _ = request  # Required by SlowAPI for request-scoped rate limiting.

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
        # 4. Extract text from PDF pages
    try:
        with fitz.open(stream=BytesIO(content), filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password-protected PDFs are not supported yet.",
                )

            if pdf.page_count > MAX_PAGES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"The PDF must not exceed {MAX_PAGES} pages.",
                )

            pages = []
            total_text_chars = 0
            pages_with_text = 0

            for page_number in range(pdf.page_count):
                page_text = (
                    pdf.load_page(page_number)
                    .get_text("text") # type: ignore[attr-defined]
                    .strip()
                )

                total_text_chars += len(page_text)

                if total_text_chars > MAX_EXTRACTED_TEXT_CHARS:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "The extracted PDF text must not exceed "
                            f"{MAX_EXTRACTED_TEXT_CHARS:,} characters."
                        ),
                    )

                if page_text:
                    pages_with_text += 1

                pages.append({
                    "page": page_number + 1,
                    "text": page_text,
                })

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read this PDF. It may be corrupted.",
        ) from exc
    # 5. Scanned PDF detection
    if pages_with_text == 0:
        return AnalyzeResponse(
            filename=file.filename,
            page_count=len(pages),
            pages_with_text=0,
            analysis=AnalysisResult(
                status="ocr_required",
                model=settings.openrouter_model,
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
    pages_without_text = [
        page["page"] for page in pages if not page["text"]
    ]
    metadata = AnalysisMetadata(pages_without_text=pages_without_text)
    evidence_cache = []
    analysis_started = perf_counter()

    try:
        report = await analyze_tender(
            document_text,
            metadata=metadata,
            evidence_cache=evidence_cache,
        )

    except AIConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot connect to the AI provider. Check your internet connection.",
        ) from exc

    except AITimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The AI provider took too long to respond.",
        ) from exc

    except AIStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider returned HTTP {exc.status_code}.",
        ) from exc

    except (ValueError, RuntimeError) as exc:
        logger.error("Tender report generation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate the tender analysis report.",
        ) from exc

    try:
        structured = await extract_structured_tender(
            document_text,
            metadata=metadata,
            evidence_cache=evidence_cache,
        )
    except (AIConnectionError, AITimeoutError, AIStatusError, ValueError, RuntimeError) as exc:
        # Structured extraction failed but the report is valid: degrade rather
        # than failing the whole request.
        logger.warning("Structured extraction failed (%s).", type(exc).__name__)
        metadata.structured_failed = True
        structured = StructuredTenderAnalysis()

    logger.info(
        "Tender AI analysis finished: chunks=%d, duration=%.2fs, "
        "report_truncated=%s, structured_truncated=%s, structured_failed=%s",
        len(evidence_cache),
        perf_counter() - analysis_started,
        metadata.report_truncated,
        metadata.structured_truncated,
        metadata.structured_failed,
    )

    build_analysis_metadata(metadata, structured)
    analysis_status_value = analysis_status(metadata)

    # 8. Parse the deadline only when its format is recognized
    parsed_deadline = parse_deadline(structured.tender.deadline)
    if parsed_deadline is None:
        parsed_deadline = _parse_deadline_from_document(document_text)
    parsed_deadline_time = parse_deadline_time(structured.tender.deadline)
    if parsed_deadline_time is None:
        parsed_deadline_time = _parse_deadline_time_from_document(document_text)
    if parsed_deadline is None:
        parsed_deadline_time = None
    deadline_text = (
        structured.tender.deadline or _deadline_line_from_document(document_text)
    )
    # The existing database requires both title and description.
    title = (
        structured.tender.title or Path(file.filename).stem
    )[:200]

    summary_parts = ["Dossier de marché analysé par TenderAI."]
    if structured.tender.reference:
        summary_parts.append(f"Référence : {structured.tender.reference}.")
    if structured.tender.contracting_authority:
        summary_parts.append(
            f"Autorité contractante : {structured.tender.contracting_authority}."
        )
    tender_summary = " ".join(summary_parts)

    tender = Tender(
        owner_id=current_user.id,
        title=title,
        description=tender_summary,
        analysis_report=report,
        estimated_budget=structured.tender.estimated_budget,
        currency=structured.tender.currency,
        deadline=parsed_deadline,
        deadline_time=parsed_deadline_time,
        deadline_text=deadline_text,
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


        db.refresh(tender)
        db.commit()

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
            model=settings.openrouter_model,
            report=report,
            structured_data=structured,
            metadata=metadata,
        ),
    )
