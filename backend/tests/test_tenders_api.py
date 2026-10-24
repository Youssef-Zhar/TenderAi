"""
tests/test_tenders_api.py
--------------------------
Tests d'intégration pour POST /api/v1/tenders/analyze-pdf.

- Base de données : SQLite en mémoire (isolée, jamais MariaDB)
- IA mockée : pas d'appel réel à Gemini
- Vérifie : statut HTTP, données renvoyées, enregistrements en DB
"""

import io
from datetime import date
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
def client(db_session):
    """TestClient FastAPI utilisant la session SQLite de test."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # db_session est fermée par sa propre fixture

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# ── Helper : créer un vrai PDF ─────────────────────────────────────────────────

def make_pdf(text: str = "Test procurement document") -> bytes:
    """Génère un vrai PDF avec PyMuPDF contenant le texte fourni."""
    buffer = io.BytesIO()
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
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


def call_analyze_pdf(client, pdf_bytes: bytes | None = None):
    """Appelle POST /api/v1/tenders/analyze-pdf avec un PDF valide."""
    if pdf_bytes is None:
        pdf_bytes = make_pdf()
    return client.post(
        "/api/v1/tenders/analyze-pdf",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )


# ── Tests principaux ──────────────────────────────────────────────────────────

def test_analyze_pdf_http_200(client):
    """L'endpoint répond 200 avec un PDF valide et des mocks IA."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    assert response.status_code == 200, response.text


def test_analyze_pdf_response_fields(client):
    """La réponse JSON contient les champs attendus."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    data = response.json()
    assert data["tender_id"] is not None
    assert data["analysis"]["status"] == "analysis_completed"
    assert data["analysis"]["structured_data"]["tender"]["title"] == "Appel d'offres de test"


def test_analyze_pdf_saves_tender(client, db_session):
    """Le Tender est bien enregistré dans la DB SQLite de test."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    assert response.status_code == 200
    tender_id = response.json()["tender_id"]

    tender = db_session.get(Tender, tender_id)
    assert tender is not None
    assert tender.title == "Appel d'offres de test"
    assert tender.estimated_budget == 250000.0


def test_analyze_pdf_deadline_parsed(client, db_session):
    """La date '15 November 2026 at 12:00' est parsée en 2026-11-15."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    tender = db_session.get(Tender, tender_id)
    assert tender.deadline == date(2026, 11, 15)


def test_analyze_pdf_saves_condition(client, db_session):
    """La condition est enregistrée en DB."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    conditions = db_session.query(TenderCondition).filter_by(tender_id=tender_id).all()
    assert len(conditions) == 1
    assert conditions[0].description == "Livraison sous 30 jours"


def test_analyze_pdf_saves_document(client, db_session):
    """Le document obligatoire est enregistré en DB."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    docs = db_session.query(TenderDocument).filter_by(tender_id=tender_id).all()
    assert len(docs) == 1
    assert docs[0].name == "CPS"
    assert docs[0].is_mandatory is True


def test_analyze_pdf_saves_criterion(client, db_session):
    """Le critère d'évaluation est enregistré en DB."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    criteria = db_session.query(TenderCriterion).filter_by(tender_id=tender_id).all()
    assert len(criteria) == 1
    assert criteria[0].name == "Prix"
    assert criteria[0].weight == 50.0


def test_analyze_pdf_persists_verified_evidence(client, db_session):
    """Seule la preuve vérifiée est enregistrée en DB, avec sa citation."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()

    assert len(evidences) == 1
    assert evidences[0].field_name == "deadline"
    assert evidences[0].extracted_value == "15 November 2026 at 12:00"
    assert evidences[0].page_number == 1
    assert evidences[0].source_text == "Date limite : 15 November 2026 at 12:00"


def test_analyze_pdf_does_not_create_synthetic_evidence(client, db_session):
    """Les champs scalaires sans source vérifiée ne créent pas de preuve."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

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


def test_analyze_pdf_does_not_persist_rejected_evidence(client, db_session):
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
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()

    assert len(evidences) == 1
    assert evidences[0].field_name == "deadline"


def test_analyze_pdf_preserves_corrected_page_number(client, db_session):
    """Une page corrigée par la vérification est conservée en base."""
    structured = make_structured()
    structured.evidence[0].page_number = 2

    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=structured)),
    ):
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()

    assert len(evidences) == 1
    assert evidences[0].field_name == "deadline"
    assert evidences[0].page_number == 2


def test_analyze_pdf_serializes_extraction_conflicts_separately(client):
    """Les conflits sont exposés séparément des preuves PDF dans la réponse."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured_with_conflict())),
    ):
        response = call_analyze_pdf(client)

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


def test_analyze_pdf_serializes_verification_counts(client):
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
        response = call_analyze_pdf(client)

    structured_data = response.json()["analysis"]["structured_data"]
    assert structured_data["verified_evidence_count"] == 1
    assert structured_data["rejected_evidence_count"] == 2
    assert structured_data["corrected_page_count"] == 1
    assert structured_data["ambiguous_evidence_count"] == 1


def test_analyze_pdf_does_not_persist_extraction_conflicts_as_evidence(
    client, db_session
):
    """Les conflits ne doivent jamais être enregistrés dans TenderEvidence."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured_with_conflict())),
    ):
        response = call_analyze_pdf(client)

    tender_id = response.json()["tender_id"]
    evidences = db_session.query(TenderEvidence).filter_by(tender_id=tender_id).all()
    field_names = {e.field_name for e in evidences}

    assert len(evidences) == 1
    assert not any(name.startswith("conflict:") for name in field_names)
    assert field_names == {"deadline"}


# ── Tests d'erreur ────────────────────────────────────────────────────────────

def test_analyze_pdf_rejects_non_pdf_extension(client):
    """Un fichier .txt doit être rejeté avec HTTP 400."""
    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={"file": ("document.txt", b"contenu", "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_analyze_pdf_rejects_fake_pdf(client):
    """Un fichier .pdf sans signature %PDF- doit être rejeté avec HTTP 400."""
    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={"file": ("fake.pdf", b"not a real pdf", "application/pdf")},
    )
    assert response.status_code == 400


def test_analyze_pdf_rejects_oversized_file(client):
    """Un fichier > 10 Mo doit être rejeté avec HTTP 413."""
    big_content = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/api/v1/tenders/analyze-pdf",
        files={"file": ("big.pdf", big_content, "application/pdf")},
    )
    assert response.status_code == 413


def test_analyze_pdf_null_deadline_when_unknown(client, db_session):
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
        response = call_analyze_pdf(client)

    assert response.status_code == 200
    tender_id = response.json()["tender_id"]
    tender = db_session.get(Tender, tender_id)
    assert tender.deadline is None


# ── Phase 4 : statut partiel et métadonnées ───────────────────────────────────

def test_analyze_pdf_reports_partial_status_on_conflicts(client):
    """Un conflit d'extraction doit produire un statut partiel explicite."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured_with_conflict())),
    ):
        response = call_analyze_pdf(client)

    analysis = response.json()["analysis"]
    assert response.status_code == 200
    assert analysis["status"] == "analysis_partial"
    assert analysis["metadata"]["extraction_conflict_count"] == 1
    assert "extraction_conflicts" in analysis["metadata"]["degradation_reasons"]


def test_analyze_pdf_metadata_counts_match_structured_data(client):
    """Les compteurs de métadonnées reflètent StructuredTenderAnalysis."""
    structured = make_structured_with_conflict()
    structured.verified_evidence_count = 1
    structured.rejected_evidence_count = 2
    structured.ambiguous_evidence_count = 1

    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=structured)),
    ):
        response = call_analyze_pdf(client)

    payload = response.json()["analysis"]
    metadata = payload["metadata"]
    structured_data = payload["structured_data"]

    assert metadata["rejected_evidence_count"] == structured_data["rejected_evidence_count"]
    assert metadata["ambiguous_evidence_count"] == structured_data["ambiguous_evidence_count"]
    assert metadata["extraction_conflict_count"] == len(structured_data["extraction_conflicts"])
    assert metadata["rejected_evidence_count"] == 2
    assert metadata["ambiguous_evidence_count"] == 1


def test_analyze_pdf_preserves_report_when_structured_fails(client):
    """Un échec structuré après un rapport valide ne doit pas renvoyer 502."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport valide")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        response = call_analyze_pdf(client)

    analysis = response.json()["analysis"]
    assert response.status_code == 200
    assert analysis["report"] == "Rapport valide"
    assert analysis["status"] == "analysis_partial"
    assert analysis["metadata"]["structured_failed"] is True
    assert "structured_failed" in analysis["metadata"]["degradation_reasons"]
    assert analysis["structured_data"]["tender"]["title"] is None


def test_analyze_pdf_completed_status_has_empty_reasons(client):
    """Une analyse sans dégradation reste analysis_completed sans raisons."""
    with (
        patch("app.api.routes.tenders.analyze_tender", new=AsyncMock(return_value="Rapport test")),
        patch("app.api.routes.tenders.extract_structured_tender", new=AsyncMock(return_value=make_structured())),
    ):
        response = call_analyze_pdf(client)

    analysis = response.json()["analysis"]
    assert analysis["status"] == "analysis_completed"
    assert analysis["metadata"]["degradation_reasons"] == []
