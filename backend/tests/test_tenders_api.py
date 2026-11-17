"""
tests/test_tenders_api.py
--------------------------
Tests d'intégration pour POST /api/v1/tenders/analyze-pdf.

- Base de données : SQLite en mémoire (isolée, jamais MariaDB)
- AI is mocked; no real provider call is made
- Vérifie : statut HTTP, données renvoyées, enregistrements en DB
"""

import io
from datetime import date
from unittest.mock import AsyncMock, patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api.routes.tenders import _parse_deadline_from_document

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.tender import Tender
from app.models.tender_condition import TenderCondition
from app.models.tender_document import TenderDocument
from app.models.tender_criterion import TenderCriterion
from app.models.tender_evidence import TenderEvidence
from app.schemas.analysis import (
    StructuredTenderAnalysis,
    TenderDetails,
    TenderConditionItem,
    TenderDocumentItem,
    TenderCriterionItem,
    TenderEvidenceItem,
    ExtractionConflictItem,
)

from app.core.security import create_access_token, hash_password
from app.core.rate_limit import limiter
from app.models.user import User

# ── Fixture : client avec SQLite temporaire ───────────────────────────────────

@pytest.fixture
def db_session():
    """Session SQLite en mémoire, isolée du MariaDB réel."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

@pytest.fixture
def test_user(db_session):
    """Create the primary test user."""
    user = User(
        email="tenders-test@example.com",
        hashed_password=hash_password("StrongPassword123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """Return JWT headers for the primary test user."""
    token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def second_test_user(db_session):
    """Create a second test user."""
    user = User(
        email="second-tenders-test@example.com",
        hashed_password=hash_password("AnotherStrongPassword123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def second_auth_headers(second_test_user):
    """Return JWT headers for the second test user."""
    token = create_access_token(second_test_user.id)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def client(db_session):
    """TestClient FastAPI utilisant la session SQLite de test."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # db_session est fermée par sa propre fixture

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        limiter.reset()
        app.dependency_overrides.clear()


# ── Helper : créer un vrai PDF ─────────────────────────────────────────────────

def make_pdf(text: str = "Test procurement document") -> bytes:
    """Génère un vrai PDF avec PyMuPDF contenant le texte fourni."""
    buffer = io.BytesIO()
    with pymupdf.open() as pdf:
        page = pdf.new_page()  # type: ignore[attr-defined]
        page.insert_text((72, 72), text)
        pdf.save(buffer)
    return buffer.getvalue()

def make_encrypted_pdf() -> bytes:
    buffer = io.BytesIO()

    with pymupdf.open() as pdf:
        page = pdf.new_page()    # type: ignore[attr-defined]
        page.insert_text((72, 72), "Confidential procurement document")
        pdf.save(
            buffer,
            encryption=getattr(pymupdf, "PDF_ENCRYPT_AES_256"),
            owner_pw="owner-password",
            user_pw="user-password",
        )

    return buffer.getvalue()

def make_pdf_pages(page_count: int) -> bytes:
    """Génère un PDF contenant un nombre précis de pages."""
    buffer = io.BytesIO()

    with pymupdf.open() as pdf:
        for _ in range(page_count):
            pdf.new_page()   # type: ignore[attr-defined]

        pdf.save(buffer)

    return buffer.getvalue()

def make_pdf_with_large_text() -> bytes:
    """Génère un PDF multi-pages contenant plus de 300 000 caractères extraits."""
    buffer = io.BytesIO()

    with pymupdf.open() as pdf:
        for _ in range(101):
            page = pdf.new_page()  # type: ignore[attr-defined]
            page.insert_textbox(
                pymupdf.Rect(20, 20, 590, 770),
                "Tender data " * 250,
                fontsize=2,
            )

        pdf.save(buffer)

    return buffer.getvalue()
# ── Données de mock réutilisables ─────────────────────────────────────────────

def make_structured() -> StructuredTenderAnalysis:
    return StructuredTenderAnalysis(
        tender=TenderDetails(
            title="Appel d'offres de test",
            reference="AO-TEST-2026-001",
            contracting_authority="Commune de test",
            estimated_budget=250000.0,
            currency="MAD",
            deadline="15 November 2026 at 12:00",
            provisional_guarantee="5000 MAD",
        ),
        conditions=[
            TenderConditionItem(
                condition_type="delivery",
                description="Livraison sous 30 jours",
            )
        ],
        documents=[
            TenderDocumentItem(
                name="CPS",
                description="Cahier des prescriptions spéciales",
                is_mandatory=True,
            )
        ],
        criteria=[
            TenderCriterionItem(name="Prix", weight=50.0)
        ],
        evidence=[
            TenderEvidenceItem(
                field_name="deadline",
                extracted_value="15 November 2026 at 12:00",
                page_number=1,
                source_text="Date limite : 15 November 2026 at 12:00",
            )
        ],
    )


def make_structured_with_conflict() -> StructuredTenderAnalysis:
    structured = make_structured()
    structured.extraction_conflicts.append(
        ExtractionConflictItem(
            field_name="estimated_budget",
            first_value=250000.0,
            second_value=300000.0,
            first_chunk_index=1,
            second_chunk_index=2,
        )
    )
    return structured


def call_analyze_pdf(
    client,
    headers: dict[str, str],
    pdf_bytes: bytes | None = None,
    file_name: str = "test.pdf",
):
    """Appelle POST /api/v1/tenders/analyze-pdf avec un JWT valide."""
    if pdf_bytes is None:
        pdf_bytes = make_pdf()

    return client.post(
        "/api/v1/tenders/analyze-pdf",
        files={"file": (file_name, pdf_bytes, "application/pdf")},
        headers=headers,
    )


# ── Tests principaux ──────────────────────────────────────────────────────────

def test_analyze_pdf_http_200(client , auth_headers):
    """L'endpoint répond 200 avec un PDF valide et des mocks IA."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client , auth_headers)

    assert response.status_code == 200, response.text


def test_analyze_pdf_response_fields(client, auth_headers):
    """La réponse JSON contient les champs attendus."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client , auth_headers)

    data = response.json()
    assert data["tender_id"] is not None
    assert data["analysis"]["status"] == "analysis_completed"
    assert data["analysis"]["structured_data"]["tender"]["title"] == "Appel d'offres de test"


def test_analyze_pdf_saves_tender(client, db_session, test_user, auth_headers):
    """Le Tender est bien enregistré dans la DB SQLite de test."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    assert response.status_code == 200
    tender_id = response.json()["tender_id"]

    tender = db_session.get(Tender, tender_id)
    assert tender is not None
    assert tender.owner_id == test_user.id
    assert tender.title == "Appel d'offres de test"
    assert tender.estimated_budget == 250000.0


def test_analyze_pdf_deadline_parsed(client, db_session , auth_headers):
    """La date '15 November 2026 at 12:00' est parsée en 2026-11-15."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    tender = db_session.get(Tender, tender_id)
    assert tender.deadline == date(2026, 11, 15)


def test_analyze_pdf_saves_condition(client, db_session , auth_headers):
    """La condition est enregistrée en DB."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    conditions = db_session.query(TenderCondition).filter_by(tender_id=tender_id).all()
    assert len(conditions) == 1
    assert conditions[0].description == "Livraison sous 30 jours"


def test_analyze_pdf_saves_document(client, db_session , auth_headers):
    """Le document obligatoire est enregistré en DB."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    docs = db_session.query(TenderDocument).filter_by(tender_id=tender_id).all()
    assert len(docs) == 1
    assert docs[0].name == "CPS"
    assert docs[0].is_mandatory is True


def test_analyze_pdf_saves_criterion(client, db_session , auth_headers):
    """Le critère d'évaluation est enregistré en DB."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    criteria = db_session.query(TenderCriterion).filter_by(tender_id=tender_id).all()
    assert len(criteria) == 1
    assert criteria[0].name == "Prix"
    assert criteria[0].weight == 50.0


def test_analyze_pdf_persists_verified_evidence(client, db_session , auth_headers):
    """Seule la preuve vérifiée est enregistrée en DB, avec sa citation."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()

    assert len(evidences) == 1
    assert evidences[0].field_name == "deadline"
    assert evidences[0].extracted_value == "15 November 2026 at 12:00"
    assert evidences[0].page_number == 1
    assert evidences[0].source_text == "Date limite : 15 November 2026 at 12:00"


def test_analyze_pdf_does_not_create_synthetic_evidence(client, db_session , auth_headers):
    """Les champs scalaires sans source vérifiée ne créent pas de preuve."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()
    field_names = {e.field_name for e in evidences}

    assert field_names == {"deadline"}
    assert not field_names & {
        "reference",
        "contracting_authority",
        "currency",
        "provisional_guarantee",
    }


def test_analyze_pdf_does_not_persist_rejected_evidence(client, db_session , auth_headers):
    """Une preuve rejetée par la vérification n'est jamais enregistrée."""
    structured = make_structured()
    structured.rejected_evidence_count = 1
    structured.evidence.append(
        TenderEvidenceItem(
            field_name="reference",
            extracted_value="AO-FABRIQUE",
            page_number=None,
            source_text=None,
        )
    )

    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=structured)),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()

    assert len(evidences) == 1
    assert evidences[0].field_name == "deadline"


def test_analyze_pdf_preserves_corrected_page_number(client, db_session , auth_headers):
    """Une page corrigée par la vérification est conservée en base."""
    structured = make_structured()
    structured.evidence[0].page_number = 2

    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=structured)),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()

    assert len(evidences) == 1
    assert evidences[0].field_name == "deadline"
    assert evidences[0].page_number == 2


def test_analyze_pdf_serializes_extraction_conflicts_separately(client , auth_headers):
    """Les conflits sont exposés séparément des preuves PDF dans la réponse."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured_with_conflict())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    assert response.status_code == 200
    structured_data = response.json()["analysis"]["structured_data"]

    assert structured_data["extraction_conflicts"] == [
        {
            "field_name": "estimated_budget",
            "first_value": 250000.0,
            "second_value": 300000.0,
            "first_chunk_index": 1,
            "second_chunk_index": 2,
        }
    ]
    assert [item["field_name"] for item in structured_data["evidence"]] == [
        "deadline"
    ]
    assert structured_data["verified_evidence_count"] == 0
    assert structured_data["rejected_evidence_count"] == 0
    assert structured_data["corrected_page_count"] == 0
    assert structured_data["ambiguous_evidence_count"] == 0


def test_analyze_pdf_serializes_verification_counts(client, auth_headers):
    """Les compteurs de vérification sont exposés dans la réponse."""
    structured = make_structured()
    structured.verified_evidence_count = 1
    structured.rejected_evidence_count = 2
    structured.corrected_page_count = 1
    structured.ambiguous_evidence_count = 1

    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=structured)),
    ):
        response = call_analyze_pdf(client, auth_headers)

    structured_data = response.json()["analysis"]["structured_data"]
    assert structured_data["verified_evidence_count"] == 1
    assert structured_data["rejected_evidence_count"] == 2
    assert structured_data["corrected_page_count"] == 1
    assert structured_data["ambiguous_evidence_count"] == 1


def test_analyze_pdf_does_not_persist_extraction_conflicts_as_evidence(
    client, db_session, auth_headers
):
    """Les conflits ne doivent jamais être enregistrés dans TenderEvidence."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured_with_conflict())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()
    field_names = {e.field_name for e in evidences}

    assert len(evidences) == 1
    assert not any(name.startswith("conflict:") for name in field_names)
    assert field_names == {"deadline"}


# ── Tests d'erreur ────────────────────────────────────────────────────────────

def test_analyze_pdf_rejects_non_pdf_extension(client , auth_headers):
    """Un fichier .txt doit être rejeté avec HTTP 400."""
    response = call_analyze_pdf(client, auth_headers, pdf_bytes=b"contenu", file_name="document.txt")
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_analyze_pdf_rejects_fake_pdf(client , auth_headers):
    """Un fichier .pdf sans signature %PDF- doit être rejeté avec HTTP 400."""
    response = call_analyze_pdf(client, auth_headers, pdf_bytes=b"not a real pdf", file_name="fake.pdf")
    assert response.status_code == 400


def test_analyze_pdf_rejects_oversized_file(client , auth_headers):
    """Un fichier > 10 Mo doit être rejeté avec HTTP 413."""
    big_content = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 1)
    response = call_analyze_pdf(client, auth_headers, pdf_bytes=big_content, file_name="big.pdf")
    assert response.status_code == 413

def test_analyze_pdf_rejects_too_many_pages(client, auth_headers):
    """Un PDF dépassant 200 pages doit être rejeté avant l'analyse IA."""
    pdf_bytes = make_pdf_pages(201)

    with (
        patch(
            "app.api.routes.tenders.analyze_tender",
            new=AsyncMock(),
        ) as analyze_mock,
        patch(
            "app.api.routes.tenders.extract_structured_tender",
            new=AsyncMock(),
        ) as structured_mock,
    ):
        response = call_analyze_pdf(
            client,
            auth_headers,
            pdf_bytes=pdf_bytes,
        )

    assert response.status_code == 413
    assert "200 pages" in response.json()["detail"]
    analyze_mock.assert_not_awaited()
    structured_mock.assert_not_awaited()

def test_analyze_pdf_rejects_excessive_extracted_text(client, auth_headers):
    """Un PDF dépassant 300 000 caractères doit être rejeté avant l'analyse IA."""
    pdf_bytes = make_pdf_with_large_text()

    with (
        patch(
            "app.api.routes.tenders.analyze_tender",
            new=AsyncMock(),
        ) as analyze_mock,
        patch(
            "app.api.routes.tenders.extract_structured_tender",
            new=AsyncMock(),
        ) as structured_mock,
    ):
        response = call_analyze_pdf(
            client,
            auth_headers,
            pdf_bytes=pdf_bytes,
        )

    assert response.status_code == 413
    assert "300,000 characters" in response.json()["detail"]
    analyze_mock.assert_not_awaited()
    structured_mock.assert_not_awaited()

def test_analyze_pdf_null_deadline_when_unknown(client, db_session , auth_headers):
    """Quand la deadline est inconnue, le champ deadline du Tender est None."""
    structured_no_deadline = StructuredTenderAnalysis(
        tender=TenderDetails(
            title="Test sans date",
            deadline="date inconnue",  # format non reconnu → None
        ),
    )
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=structured_no_deadline)),
    ):
        response = call_analyze_pdf(client , auth_headers)

    assert response.status_code == 200
    tender_id = response.json()["tender_id"]
    tender = db_session.get(Tender, tender_id)
    assert tender.deadline is None


# ── Phase 4 : statut partiel et métadonnées ───────────────────────────────────

def test_analyze_pdf_reports_partial_status_on_conflicts(client , auth_headers):
    """Un conflit d'extraction doit produire un statut partiel explicite."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured_with_conflict())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    analysis = response.json()["analysis"]
    assert response.status_code == 200
    assert analysis["status"] == "analysis_partial"
    assert analysis["metadata"]["extraction_conflict_count"] == 1
    assert "extraction_conflicts" in analysis["metadata"]["degradation_reasons"]


def test_analyze_pdf_metadata_counts_match_structured_data(client , auth_headers):
    """Les compteurs de métadonnées reflètent StructuredTenderAnalysis."""
    structured = make_structured_with_conflict()
    structured.verified_evidence_count = 1
    structured.rejected_evidence_count = 2
    structured.ambiguous_evidence_count = 1

    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=structured)),
    ):
        response = call_analyze_pdf(client , auth_headers)

    payload = response.json()["analysis"]
    metadata = payload["metadata"]
    structured_data = payload["structured_data"]

    assert metadata["rejected_evidence_count"] == structured_data["rejected_evidence_count"]
    assert metadata["ambiguous_evidence_count"] == structured_data["ambiguous_evidence_count"]
    assert metadata["extraction_conflict_count"] == len(structured_data["extraction_conflicts"])
    assert metadata["rejected_evidence_count"] == 2
    assert metadata["ambiguous_evidence_count"] == 1


def test_analyze_pdf_preserves_report_when_structured_fails(client , auth_headers):
    """Un échec structuré après un rapport valide ne doit pas renvoyer 502."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport valide")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        response = call_analyze_pdf(client, auth_headers)

    analysis = response.json()["analysis"]
    assert response.status_code == 200
    assert analysis["report"] == "Rapport valide"
    assert analysis["status"] == "analysis_partial"
    assert analysis["metadata"]["structured_failed"] is True
    assert "structured_failed" in analysis["metadata"]["degradation_reasons"]
    assert analysis["structured_data"]["tender"]["title"] is None

def test_analyze_pdf_hides_internal_report_generation_error(client, auth_headers):
    """Les erreurs internes ne doivent pas être exposées au client."""
    internal_error = "OPENROUTER_API_KEY is not configured."

    with patch(
        "app.api.routes.tenders.analyze_tender",
        new=AsyncMock(side_effect=RuntimeError(internal_error)),
    ):
        response = call_analyze_pdf(client, auth_headers)

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Could not generate the tender analysis report."
    )
    assert internal_error not in response.text


def test_analyze_pdf_completed_status_has_empty_reasons(client , auth_headers):
    """Une analyse sans dégradation reste analysis_completed sans raisons."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client, auth_headers)

    analysis = response.json()["analysis"]
    assert analysis["status"] == "analysis_completed"
    assert analysis["metadata"]["degradation_reasons"] == []


# ── Tests : pagination GET /api/v1/tenders/ ──

def create_test_tenders(db_session, owner_id, count=5):
    """Create tenders owned by the specified test user."""
    tenders = [
        Tender(
            owner_id=owner_id,
            title=f"Test Tender {i}",
            description=f"Description for test tender number {i}",
        )
        for i in range(1, count + 1)
    ]
    db_session.add_all(tenders)
    db_session.commit()


def test_list_tenders_pagination_skip_and_limit(
    client, db_session, test_user, auth_headers
):
    create_test_tenders(
        db_session,
        owner_id=test_user.id,
        count=5,
    )

    all_response = client.get(
        "/api/v1/tenders/",
        headers=auth_headers,
    )
    page_response = client.get(
        "/api/v1/tenders/?skip=1&limit=2",
        headers=auth_headers,
    )

    assert all_response.status_code == 200
    assert page_response.status_code == 200

    all_tenders = all_response.json()
    page_tenders = page_response.json()

    all_ids = [tender["id"] for tender in all_tenders]
    page_ids = [tender["id"] for tender in page_tenders]

    assert all_ids == sorted(all_ids)
    assert page_ids == all_ids[1:3]
    assert page_tenders == all_tenders[1:3]

def test_list_tenders_rejects_zero_limit(client, auth_headers):
    response = client.get("/api/v1/tenders/?limit=0", headers=auth_headers)

    assert response.status_code == 422


def test_list_tenders_rejects_limit_above_100(client, auth_headers):
    response = client.get("/api/v1/tenders/?limit=101", headers=auth_headers)

    assert response.status_code == 422


# ── Authorization tests ──────────────────────────────────────

VALID_TENDER_PAYLOAD = {
    "title": "Test tender authorization",
    "description": "A valid description for authorization testing.",
    "estimated_budget": 10000,
    "deadline": "2026-12-31",
}


def test_create_tender_requires_authentication(client):
    response = client.post(
        "/api/v1/tenders/",
        json=VALID_TENDER_PAYLOAD,
    )
    assert response.status_code == 401


def test_update_tender_requires_authentication(client):
    response = client.put(
        "/api/v1/tenders/1",
        json=VALID_TENDER_PAYLOAD,
    )
    assert response.status_code == 401


def test_delete_tender_requires_authentication(client):
    response = client.delete("/api/v1/tenders/1")
    assert response.status_code == 401


def test_list_tenders_requires_authentication(client):
    response = client.get("/api/v1/tenders/")
    assert response.status_code == 401


def test_get_tender_requires_authentication(client):
    response = client.get("/api/v1/tenders/1")
    assert response.status_code == 401

def test_get_tender_with_authentication(
    client, db_session, test_user, auth_headers
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()

    response = client.get(
        f"/api/v1/tenders/{tender.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == tender.title

def test_create_tender_with_authentication(
    client, db_session, test_user, auth_headers
):
    response = client.post(
        "/api/v1/tenders/",
        json=VALID_TENDER_PAYLOAD,
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["title"] == VALID_TENDER_PAYLOAD["title"]

    tender = db_session.query(Tender).first()
    assert tender is not None
    assert tender.owner_id == test_user.id


def test_update_tender_with_authentication(
    client, db_session, test_user, auth_headers
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()

    response = client.put(
        f"/api/v1/tenders/{tender.id}",
        json=VALID_TENDER_PAYLOAD,
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == VALID_TENDER_PAYLOAD["title"]


def test_delete_tender_with_authentication(
    client, db_session, test_user, auth_headers
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()
    tender_id = tender.id

    response = client.delete(
        f"/api/v1/tenders/{tender_id}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert db_session.get(Tender, tender_id) is None

def test_user_cannot_get_another_users_tender(
    client, db_session, test_user, second_auth_headers
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()

    response = client.get(
        f"/api/v1/tenders/{tender.id}",
        headers=second_auth_headers,
    )

    assert response.status_code == 404


def test_user_cannot_update_another_users_tender(
    client, db_session, test_user, second_auth_headers
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()
    original_title = tender.title

    response = client.put(
        f"/api/v1/tenders/{tender.id}",
        json=VALID_TENDER_PAYLOAD,
        headers=second_auth_headers,
    )

    assert response.status_code == 404

    db_session.refresh(tender)
    assert tender.title == original_title


def test_user_cannot_delete_another_users_tender(
    client, db_session, test_user, second_auth_headers
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()
    tender_id = tender.id

    response = client.delete(
        f"/api/v1/tenders/{tender_id}",
        headers=second_auth_headers,
    )

    assert response.status_code == 404
    assert db_session.get(Tender, tender_id) is not None


def test_list_tenders_returns_only_current_users_tenders(
    client, db_session, test_user, second_test_user, auth_headers
):
    create_test_tenders(db_session, owner_id=test_user.id, count=2)
    create_test_tenders(db_session, owner_id=second_test_user.id, count=3)

    response = client.get(
        "/api/v1/tenders/",
        headers=auth_headers,
    )

    assert response.status_code == 200
    tenders = response.json()

    assert len(tenders) == 2
    assert all(tender["title"].startswith("Test Tender") for tender in tenders)

def test_update_nonexistent_tender_returns_404(client, auth_headers):
    response = client.put(
        "/api/v1/tenders/9999",
        json=VALID_TENDER_PAYLOAD,
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_delete_nonexistent_tender_returns_404(client, auth_headers):
    response = client.delete(
        "/api/v1/tenders/9999",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "abc"),
        ("description", "too short"),
        ("estimated_budget", -1),
    ],
)
def test_create_tender_rejects_invalid_fields(
    client, auth_headers, field, value
):
    payload = VALID_TENDER_PAYLOAD.copy()
    payload[field] = value

    response = client.post(
        "/api/v1/tenders/",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_analyze_pdf_requires_authentication(client):
    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={
            "file": (
                "test.pdf",
                make_pdf(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 401


def test_create_tender_rolls_back_on_commit_failure(
    client, db_session, auth_headers, monkeypatch
):
    rollback_called = False

    def failing_commit():
        raise RuntimeError("Simulated database commit failure")

    original_rollback = db_session.rollback

    def tracking_rollback():
        nonlocal rollback_called
        rollback_called = True
        original_rollback()

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracking_rollback)

    with pytest.raises(RuntimeError, match="Simulated database commit failure"):
        client.post(
            "/api/v1/tenders/",
            json=VALID_TENDER_PAYLOAD,
            headers=auth_headers,
        )

    assert rollback_called is True
    assert db_session.query(Tender).count() == 0


def test_update_tender_rolls_back_on_commit_failure(
    client, db_session, test_user, auth_headers, monkeypatch
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()
    original_title = tender.title

    rollback_called = False

    def failing_commit():
        raise RuntimeError("Simulated database commit failure")

    original_rollback = db_session.rollback

    def tracking_rollback():
        nonlocal rollback_called
        rollback_called = True
        original_rollback()

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracking_rollback)

    with pytest.raises(RuntimeError, match="Simulated database commit failure"):
        client.put(
            f"/api/v1/tenders/{tender.id}",
            json=VALID_TENDER_PAYLOAD,
            headers=auth_headers,
        )

    assert rollback_called is True
    db_session.expire_all()
    restored_tender = db_session.get(Tender, tender.id)
    assert restored_tender.title == original_title

def test_delete_tender_rolls_back_on_commit_failure(
    client, db_session, test_user, auth_headers, monkeypatch
):
    create_test_tenders(db_session, owner_id=test_user.id, count=1)
    tender = db_session.query(Tender).first()
    tender_id = tender.id

    rollback_called = False

    def failing_commit():
        raise RuntimeError("Simulated database commit failure")

    original_rollback = db_session.rollback

    def tracking_rollback():
        nonlocal rollback_called
        rollback_called = True
        original_rollback()

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracking_rollback)

    with pytest.raises(RuntimeError, match="Simulated database commit failure"):
        client.delete(
            f"/api/v1/tenders/{tender_id}",
            headers=auth_headers,
        )

    assert rollback_called is True
    db_session.expire_all()
    assert db_session.get(Tender, tender_id) is not None


def test_analyze_pdf_rolls_back_all_records_on_commit_failure(
    client, db_session, auth_headers, monkeypatch
):
    def failing_commit():
        # Flush all pending records into the current transaction.
        db_session.flush()
        raise RuntimeError("Simulated database commit failure")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with (
        patch(
            "app.api.routes.tenders.analyze_tender",
            new=AsyncMock(return_value="Rapport test"),
        ),
        patch(
            "app.api.routes.tenders.extract_structured_tender",
            new=AsyncMock(return_value=make_structured()),
        ),
    ):
        response = call_analyze_pdf(client, auth_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Could not save the analysis to the database."
    )

    # No partial records should remain after rollback.
    assert db_session.query(Tender).count() == 0
    assert db_session.query(TenderCondition).count() == 0
    assert db_session.query(TenderDocument).count() == 0
    assert db_session.query(TenderCriterion).count() == 0
    assert db_session.query(TenderEvidence).count() == 0

def test_list_tenders_hides_legacy_tenders_without_owner(
    client, db_session, test_user, auth_headers
):
    legacy_tender = Tender(
        owner_id=None,
        title="Legacy Tender",
        description="Old tender without an owner",
    )
    db_session.add(legacy_tender)

    create_test_tenders(db_session, owner_id=test_user.id, count=1)

    db_session.commit()

    response = client.get(
        "/api/v1/tenders/",
        headers=auth_headers,
    )

    assert response.status_code == 200

    tenders = response.json()
    assert len(tenders) == 1
    assert tenders[0]["title"] == "Test Tender 1"
    assert all(tender["title"] != "Legacy Tender" for tender in tenders)


def test_parse_deadline_from_document_extracts_labeled_deadline():
    document_text = (
        "Objet : Appel d'offres\n"
        "Date limite de remise des offres : 15 novembre 2026 à 10 h 00\n"
    )

    result = _parse_deadline_from_document(document_text)

    assert result == date(2026, 11, 15)

def test_upload_rejects_password_protected_pdf(client, auth_headers):
    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={
            "file": (
                "encrypted.pdf",
                make_encrypted_pdf(),
                "application/pdf",
            )
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "password" in response.json()["detail"].lower()

def test_upload_rejects_pdf_when_reader_raises_exception(
    client, auth_headers, monkeypatch
):
    def raise_reader_error(*args, **kwargs):
        raise RuntimeError("Simulated PDF reader failure")

    monkeypatch.setattr(
        "app.api.routes.tenders.fitz.open",
        raise_reader_error,
    )

    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={
            "file": (
                "broken.pdf",
                make_pdf(),
                "application/pdf",
            )
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Could not read this PDF. It may be corrupted."
    )

def test_upload_scanned_pdf_returns_ocr_required(client, auth_headers):
    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={
            "file": (
                "scanned.pdf",
                make_pdf_pages(1),
                "application/pdf",
            )
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["pages_with_text"] == 0
    assert response.json()["analysis"]["status"] == "ocr_required"

def test_upload_returns_503_when_ai_connection_fails(
    client, auth_headers, monkeypatch
):
    from app.services.ai_analyzer import AIConnectionError

    async def fail_analysis(*args, **kwargs):
        raise AIConnectionError("OpenRouter unavailable")

    monkeypatch.setattr(
        "app.api.routes.tenders.analyze_tender",
        fail_analysis,
    )

    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={
            "file": ("test.pdf", make_pdf(), "application/pdf")
        },
        headers=auth_headers,
    )

    assert response.status_code == 503


def test_upload_returns_504_when_ai_times_out(
    client, auth_headers, monkeypatch
):
    from app.services.ai_analyzer import AITimeoutError

    async def fail_analysis(*args, **kwargs):
        raise AITimeoutError("OpenRouter timeout")

    monkeypatch.setattr(
        "app.api.routes.tenders.analyze_tender",
        fail_analysis,
    )

    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={
            "file": ("test.pdf", make_pdf(), "application/pdf")
        },
        headers=auth_headers,
    )

    assert response.status_code == 504


def test_upload_returns_502_when_ai_returns_error_status(
    client, auth_headers, monkeypatch
):
    from app.services.ai_analyzer import AIStatusError

    async def fail_analysis(*args, **kwargs):
        raise AIStatusError(503, "OpenRouter service unavailable")

    monkeypatch.setattr(
        "app.api.routes.tenders.analyze_tender",
        fail_analysis,
    )

    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={
            "file": ("test.pdf", make_pdf(), "application/pdf")
        },
        headers=auth_headers,
    )

    assert response.status_code == 502
    assert "503" in response.json()["detail"]


# ── PDF analysis rate limiting ────────────────────────────────────────────────

def test_analyze_pdf_rate_limit_is_per_authenticated_user(
    client, auth_headers, second_auth_headers
):
    """Limit each authenticated user independently to three analyses/hour."""
    limiter.reset()

    with (
        patch(
            "app.api.routes.tenders.analyze_tender",
            new=AsyncMock(return_value="Rapport test"),
        ),
        patch(
            "app.api.routes.tenders.extract_structured_tender",
            new=AsyncMock(return_value=make_structured()),
        ),
    ):
        for _ in range(3):
            response = call_analyze_pdf(client, auth_headers)
            assert response.status_code == 200

        blocked_response = call_analyze_pdf(client, auth_headers)
        assert blocked_response.status_code == 429

        # A different authenticated user has an independent quota.
        other_user_response = call_analyze_pdf(client, second_auth_headers)
        assert other_user_response.status_code == 200

    limiter.reset()
