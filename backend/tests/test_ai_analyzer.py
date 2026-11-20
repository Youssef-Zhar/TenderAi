"""
tests/test_ai_analyzer.py
--------------------------
Unit tests for app/services/ai_analyzer.py.

All tests mock the OpenRouter client — no network calls are made.
Run with: .venv/Scripts/pytest.exe tests/ -v
"""

import pytest
from datetime import date
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock

import httpx

from contextlib import asynccontextmanager
from decimal import Decimal

from app.core.config import settings
from app.services.ai_analyzer import _create_client, _open_client
from app.services.ai_analyzer import _build_page_map
from app.schemas.tender import TenderInput

from app.services.ai_analyzer import (
    analyze_tender,
    split_document,
    _call_openrouter,
    _extract_chunk,
    AIConnectionError,
    AITimeoutError,
    AIStatusError,
    MAX_CHUNK_CHARS,
    CHUNK_OUTPUT_TOKENS,
    FINAL_OUTPUT_TOKENS,
    AIFinishReasonError,
    _get_retry_delay,
    _clean_int,
    _money_signature,
    _deadline_signature,
    ChunkExtractionStatus,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_openrouter_response(
    content: str,
    finish_reason: str | None = "stop",
) -> httpx.Response:
    """Build a realistic OpenRouter Chat Completions HTTP response."""
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        },
        request=httpx.Request(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
        ),
    )


def _make_openrouter_client(responses) -> MagicMock:
    """Build a mock HTTPX client returning HTTP responses."""
    client = MagicMock()
    client.aclose = AsyncMock()

    if isinstance(responses, list):
        client.post = AsyncMock(side_effect=responses)
    else:
        client.post = AsyncMock(return_value=responses)

    return client


def _make_openrouter_error_client(exc: Exception) -> MagicMock:
    """Build a mock HTTPX client that always raises an exception."""
    client = MagicMock()
    client.aclose = AsyncMock()
    client.post = AsyncMock(side_effect=exc)
    return client


def _fake_open_client() -> MagicMock:
    """Async context manager yielding a mock HTTPX client."""
    client = MagicMock()
    client.aclose = AsyncMock()
    client.post = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ── split_document ────────────────────────────────────────────────────────────

class TestSplitDocument:
    def test_single_short_page_returns_one_chunk(self):
        text = "--- Page 1 ---\nHello world."
        assert len(split_document(text)) == 1

    def test_empty_string_returns_no_chunks(self):
        assert split_document("   ") == []

    def test_plain_text_without_page_markers_is_one_chunk(self):
        assert len(split_document("No markers. " * 10)) == 1

    def test_long_page_is_split_into_multiple_chunks(self):
        long_text = "--- Page 1 ---\n" + ("x" * (MAX_CHUNK_CHARS * 3))
        chunks = split_document(long_text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= MAX_CHUNK_CHARS

    def test_two_short_pages_merge_into_one_chunk(self):
        text = "--- Page 1 ---\nFirst.\n\n--- Page 2 ---\nSecond."
        chunks = split_document(text)
        assert len(chunks) == 1
        assert "First." in chunks[0] and "Second." in chunks[0]

    def test_long_page_keeps_marker_in_every_piece(self):
        text = "--- Page 1 ---\n" + ("data " * MAX_CHUNK_CHARS)
        chunks = split_document(text)
        assert len(chunks) > 1
        assert all("--- Page 1 ---" in chunk for chunk in chunks)
        assert all(len(chunk) <= MAX_CHUNK_CHARS for chunk in chunks)

    def test_long_pages_keep_their_own_markers(self):
        text = (
            "--- Page 1 ---\n" + ("Alpha " * MAX_CHUNK_CHARS) + "\n\n"
            "--- Page 2 ---\n" + ("Beta " * MAX_CHUNK_CHARS)
        )
        chunks = split_document(text)
        assert len(chunks) > 2
        for chunk in chunks:
            if "Beta" in chunk and "Alpha" not in chunk:
                assert "--- Page 2 ---" in chunk
            elif "Alpha" in chunk and "Beta" not in chunk:
                assert "--- Page 1 ---" in chunk
            assert len(chunk) <= MAX_CHUNK_CHARS


# ── _call_openrouter (returns tuple) ─────────────────────────────────────────────


# ── _call_openrouter (returns tuple) ──

def _make_openrouter_status_response(
    status_code: int,
    headers: dict | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers,
        json={"error": {"message": "simulated HTTP error"}},
        request=httpx.Request(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
        ),
    )


@pytest.mark.asyncio
async def test_call_openrouter_returns_content_and_finish_reason_on_stop():
    client = _make_openrouter_client(
        _make_openrouter_response("Analysis complete.", "stop")
    )

    content, finish_reason = await _call_openrouter(
        client=client,
        system_prompt="sys",
        user_message="user",
        max_tokens=200,
    )

    assert content == "Analysis complete."
    assert finish_reason == "stop"
    client.post.assert_awaited_once()
    request_payload = client.post.await_args.kwargs["json"]
    assert request_payload["reasoning"] == {"effort": "none"}


@pytest.mark.asyncio
async def test_call_openrouter_maps_length_without_raising():
    client = _make_openrouter_client(
        _make_openrouter_response("Rapport partiel…", "length")
    )

    content, finish_reason = await _call_openrouter(
        client, "sys", "user", 100
    )

    assert finish_reason == "length"
    assert content == "Rapport partiel…"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish_reason",
    ["content_filter", "error", "tool_calls", "unknown"],
)
async def test_call_openrouter_raises_on_unexpected_finish_reason(
    finish_reason,
):
    client = _make_openrouter_client(
        _make_openrouter_response(
            "Blocked or incomplete response.",
            finish_reason,
        )
    )

    with pytest.raises(AIFinishReasonError):
        await _call_openrouter(client, "sys", "user", 100)


@pytest.mark.asyncio
async def test_call_openrouter_raises_when_finish_reason_is_missing():
    client = _make_openrouter_client(
        _make_openrouter_response("Some response.", None)
    )

    with pytest.raises(AIFinishReasonError):
        await _call_openrouter(client, "sys", "user", 100)


@pytest.mark.asyncio
async def test_call_openrouter_raises_on_empty_content():
    client = _make_openrouter_client(
        _make_openrouter_response("")
    )

    with pytest.raises(RuntimeError, match="empty"):
        await _call_openrouter(client, "sys", "user", 100)


@pytest.mark.asyncio
async def test_call_openrouter_raises_on_malformed_response():
    malformed = httpx.Response(
        200,
        json={"choices": []},
        request=httpx.Request(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
        ),
    )
    client = _make_openrouter_client(malformed)

    with pytest.raises(RuntimeError):
        await _call_openrouter(client, "sys", "user", 100)


@pytest.mark.asyncio
async def test_call_openrouter_retries_on_rate_limit_then_succeeds(monkeypatch):
    import app.services.ai_analyzer as analyzer

    monkeypatch.setattr(analyzer.asyncio, "sleep", AsyncMock())

    rate_limited = _make_openrouter_status_response(429)
    success = _make_openrouter_response("Analysis complete.")
    client = _make_openrouter_client([rate_limited, success])

    content, finish_reason = await _call_openrouter(
        client, "sys", "user", 200
    )

    assert content == "Analysis complete."
    assert finish_reason == "stop"
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_call_openrouter_retries_on_503_then_succeeds(monkeypatch):
    import app.services.ai_analyzer as analyzer

    monkeypatch.setattr(analyzer.asyncio, "sleep", AsyncMock())

    overloaded = _make_openrouter_status_response(503)
    success = _make_openrouter_response("Analysis complete.")
    client = _make_openrouter_client([overloaded, success])

    content, finish_reason = await _call_openrouter(
        client, "sys", "user", 200
    )

    assert content == "Analysis complete."
    assert finish_reason == "stop"
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_call_openrouter_stops_after_three_retryable_errors(monkeypatch):
    import app.services.ai_analyzer as analyzer

    monkeypatch.setattr(analyzer.asyncio, "sleep", AsyncMock())

    overloaded = _make_openrouter_status_response(503)
    client = _make_openrouter_client(
        [overloaded, overloaded, overloaded]
    )

    with pytest.raises(AIStatusError) as exc_info:
        await _call_openrouter(client, "sys", "user", 200)

    assert exc_info.value.status_code == 503
    assert client.post.await_count == 3


@pytest.mark.asyncio
async def test_call_openrouter_raises_status_error_on_permanent_error():
    bad_request = _make_openrouter_status_response(400)
    client = _make_openrouter_client(bad_request)

    with pytest.raises(AIStatusError) as exc_info:
        await _call_openrouter(client, "sys", "user", 100)

    assert exc_info.value.status_code == 400
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_call_openrouter_raises_connection_error(monkeypatch):
    import app.services.ai_analyzer as analyzer

    monkeypatch.setattr(analyzer.asyncio, "sleep", AsyncMock())

    client = _make_openrouter_error_client(
        httpx.ConnectError("connection refused")
    )

    with pytest.raises(AIConnectionError):
        await _call_openrouter(client, "sys", "user", 100)


@pytest.mark.asyncio
async def test_call_openrouter_raises_timeout_error(monkeypatch):
    import app.services.ai_analyzer as analyzer

    monkeypatch.setattr(analyzer.asyncio, "sleep", AsyncMock())

    client = _make_openrouter_error_client(
        httpx.TimeoutException("timed out")
    )

    with pytest.raises(AITimeoutError):
        await _call_openrouter(client, "sys", "user", 100)


# ── _extract_chunk — recovery strategy ──

@pytest.mark.asyncio
async def test_extract_chunk_returns_content_when_primary_completes():
    client = _make_openrouter_client(
        _make_openrouter_response("DEADLINE: 2025-12-31", "stop")
    )

    result = await _extract_chunk(
        client, "budget: 100 000 MAD", 1, 3
    )

    assert "DEADLINE: 2025-12-31" in result
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_extract_chunk_retries_on_primary_truncation_and_succeeds():
    client = _make_openrouter_client([
        _make_openrouter_response("Rapport partiel coupé ici…", "length"),
        _make_openrouter_response("• Deadline: 31/12/2025 [p.2]", "stop"),
    ])

    result = await _extract_chunk(client, "some chunk text", 2, 5)

    assert "[FALLBACK" in result
    assert "Deadline: 31/12/2025" in result
    assert client.post.await_count == 2

@pytest.mark.asyncio
async def test_extract_chunk_keeps_primary_content_when_fallback_is_empty():
    client = _make_openrouter_client([
        _make_openrouter_response("Primary partial evidence", "length"),
        _make_openrouter_response("", "stop"),
    ])
    status = ChunkExtractionStatus()

    result = await _extract_chunk(
        client, "some chunk text", 1, 2, status
    )

    assert "[PARTIAL" in result
    assert "Primary partial evidence" in result
    assert status.fallback_used is True
    assert status.truncated is True
    assert client.post.await_count == 2
@pytest.mark.asyncio
async def test_extract_chunk_accepts_partial_when_both_truncated():
    client = _make_openrouter_client([
        _make_openrouter_response("Coupé 1…", "length"),
        _make_openrouter_response("Coupé 2…", "length"),
    ])

    result = await _extract_chunk(
        client, "a very dense chunk", 3, 5
    )

    assert "[PARTIAL" in result
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_extract_chunk_propagates_connection_error(monkeypatch):
    import app.services.ai_analyzer as analyzer

    monkeypatch.setattr(analyzer.asyncio, "sleep", AsyncMock())

    client = _make_openrouter_error_client(
        httpx.ConnectError("connection refused")
    )

    with pytest.raises(AIConnectionError):
        await _extract_chunk(client, "chunk", 1, 1)


@pytest.mark.asyncio
async def test_extract_chunk_records_fallback_used():
    client = _make_openrouter_client([
        _make_openrouter_response("Partial", "length"),
        _make_openrouter_response("Complete fallback", "stop"),
    ])
    status = ChunkExtractionStatus()

    result = await _extract_chunk(client, "chunk", 1, 1, status)

    assert "[FALLBACK" in result
    assert status.fallback_used is True
    assert status.truncated is False


@pytest.mark.asyncio
async def test_extract_chunk_records_both_attempts_truncated():
    client = _make_openrouter_client([
        _make_openrouter_response("Partial 1", "length"),
        _make_openrouter_response("Partial 2", "length"),
    ])
    status = ChunkExtractionStatus()

    result = await _extract_chunk(client, "chunk", 1, 1, status)

    assert "[PARTIAL" in result
    assert status.fallback_used is True
    assert status.truncated is True


def test_get_retry_delay_returns_none_when_retry_after_exceeds_limit():
    exc = MagicMock()
    exc.response.headers = {"Retry-After": "60"}

    assert _get_retry_delay(exc, attempt=1) is None


def test_get_retry_delay_uses_fallback_for_invalid_retry_after():
    exc = MagicMock()
    exc.response.headers = {"Retry-After": "invalid-value"}

    assert _get_retry_delay(exc, attempt=2) == 1.0


def test_get_retry_delay_clamps_negative_retry_after_to_zero():
    exc = MagicMock()
    exc.response.headers = {"Retry-After": "-5"}

    assert _get_retry_delay(exc, attempt=1) == 0


def test_get_retry_delay_handles_http_date_without_timezone():
    from email.utils import formatdate

    exc = MagicMock()
    exc.response.headers = {
        "Retry-After": formatdate(usegmt=True).removesuffix(" GMT")
    }

    delay = _get_retry_delay(exc, attempt=1)

    assert delay is not None
    assert 0 <= delay <= 30


@pytest.mark.asyncio
async def test_call_openrouter_skips_retry_when_retry_after_exceeds_limit(
    monkeypatch,
):
    import app.services.ai_analyzer as analyzer

    sleep_mock = AsyncMock()
    monkeypatch.setattr(analyzer.asyncio, "sleep", sleep_mock)

    overloaded = _make_openrouter_status_response(
        503,
        headers={"Retry-After": "60"},
    )
    client = _make_openrouter_client(overloaded)

    with pytest.raises(AIStatusError) as exc_info:
        await _call_openrouter(client, "sys", "user", 200)

    assert exc_info.value.status_code == 503
    assert client.post.await_count == 1
    sleep_mock.assert_not_awaited()

# ── Token budget sanity guards ────────────────────────────────────────────────


def test_final_output_tokens_is_large_enough():
    assert FINAL_OUTPUT_TOKENS >= 3_000

def test_chunk_output_tokens_is_large_enough():
    assert CHUNK_OUTPUT_TOKENS >= 1_000

import json

from app.schemas.analysis import (
    AnalysisMetadata,
    ExtractionConflictItem,
    StructuredTenderAnalysis,
    TenderCriterionItem,
    TenderDetails,
)
from app.services.ai_analyzer import (
    analysis_status,
    analyze_tender,
    build_analysis_metadata,
    extract_structured_tender,
    _normalise_structured_payload,
)


def test_structured_tender_schema_accepts_missing_information():
    data = {
        "tender": {
            "title": "Test tender",
            "reference": None,
            "contracting_authority": None,
            "estimated_budget": None,
            "currency": None,
            "deadline": None,
            "provisional_guarantee": None,
        },
        "conditions": [],
        "documents": [],
        "criteria": [],
        "evidence": [],
    }

    result = StructuredTenderAnalysis.model_validate(data)

    assert result.tender.title == "Test tender"
    assert result.tender.estimated_budget is None
    assert result.tender.quantity is None
    assert result.tender.processor is None
    assert result.tender.ram_gb is None
    assert result.tender.storage_gb is None
    assert result.tender.screen_size_inches is None
    assert result.tender.warranty_months is None
    assert result.tender.accessories == []
    assert result.conditions == []
    assert result.documents == []
    assert result.criteria == []
    assert result.evidence == []
    assert result.extraction_conflicts == []


class TestTechnicalSpecifications:
    def test_valid_technical_specifications(self):
        details = TenderDetails(
            quantity=10,
            processor="Intel Core i7-1355U",
            ram_gb=16,
            storage_gb=512,
            screen_size_inches=15.6,
            warranty_months=24,
            accessories=["charger", "laptop bag"],
        )

        assert details.quantity == 10
        assert details.processor == "Intel Core i7-1355U"
        assert details.ram_gb == 16
        assert details.storage_gb == 512
        assert details.screen_size_inches == 15.6
        assert details.warranty_months == 24
        assert details.accessories == ["charger", "laptop bag"]

    @pytest.mark.parametrize(
        "value",
        [float("inf"), float("-inf"), float("nan")],
    )
    def test_screen_size_rejects_non_finite_values(self, value):
        with pytest.raises(ValidationError):
            TenderDetails(screen_size_inches=value)

    @pytest.mark.parametrize(
        "value",
        [float("inf"), float("-inf"), float("nan")],
    )
    def test_estimated_budget_rejects_non_finite_values(self, value):
        with pytest.raises(ValidationError):
            TenderInput(
                title="Valid title",
                description="This is a sufficiently long description",
                estimated_budget=value,
            )
    @pytest.mark.parametrize(
        "value",
        [float("inf"), float("-inf"), float("nan")],
    )
    def test_criterion_weight_rejects_non_finite_values(self, value):
        with pytest.raises(ValidationError):
            TenderCriterionItem(name="Price", weight=value)

    @pytest.mark.parametrize(
        "value",
        [float("inf"), float("-inf"), float("nan")],
    )
    def test_extraction_conflict_rejects_non_finite_values(self, value):
        with pytest.raises(ValidationError):
            ExtractionConflictItem(
                field_name="estimated_budget",
                first_value=value,
            )
    @pytest.mark.parametrize(
        "value",
        [float("inf"), float("-inf"), float("nan")],
    )
    def test_normalizer_rejects_non_finite_screen_size(self, value):
        result = _normalise_structured_payload({
            "tender": {
                "screen_size_inches": value,
            }
        })
        assert isinstance(result, dict)
        tender = result["tender"]
        assert isinstance(tender, dict)

        assert result["tender"]["screen_size_inches"] is None

    def test_normalizer_preserves_valid_screen_size(self):
        result = _normalise_structured_payload({
            "tender": {
                "screen_size_inches": 15.6,
            }
        })
        assert isinstance(result, dict)
        tender = result["tender"]
        assert isinstance(tender, dict)

        assert result["tender"]["screen_size_inches"] == 15.6



    def test_missing_technical_specifications_use_defaults(self):
        details = TenderDetails(title="Tender without technical details")

        assert details.quantity is None
        assert details.processor is None
        assert details.ram_gb is None
        assert details.storage_gb is None
        assert details.screen_size_inches is None
        assert details.warranty_months is None
        assert details.accessories == []

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("quantity", "10"),
            ("quantity", 0),
            ("processor", 123),
            ("processor", ""),
            ("ram_gb", "16 GB"),
            ("ram_gb", 1.5),
            ("storage_gb", -1),
            ("screen_size_inches", "15.6 inches"),
            ("screen_size_inches", -1),
            ("warranty_months", "24 months"),
            ("accessories", "charger"),
            ("accessories", [1]),
        ],
    )
    def test_invalid_technical_specification_types_are_rejected(
        self, field_name, value
    ):
        with pytest.raises(ValidationError):
            TenderDetails(**{field_name: value})

    def test_existing_tender_payload_remains_backward_compatible(self):
        data = {
            "title": "Existing tender",
            "reference": "AO-2026-01",
            "contracting_authority": "Commune de test",
            "estimated_budget": 100000,
            "currency": "MAD",
            "deadline": "31/12/2026",
            "provisional_guarantee": "5000 MAD",
        }

        details = TenderDetails.model_validate(data)

        assert details.title == "Existing tender"
        assert details.reference == "AO-2026-01"
        assert details.contracting_authority == "Commune de test"
        assert details.estimated_budget == 100000
        assert details.currency == "MAD"
        assert details.deadline == "31/12/2026"
        assert details.provisional_guarantee == "5000 MAD"
        assert details.quantity is None
        assert details.accessories == []


from unittest.mock import patch


@pytest.mark.asyncio
async def test_extract_structured_tender_merges_multiple_chunks():
    """Structured results from multiple chunks are merged without API calls."""
    from app.services import ai_analyzer

    first_json = {
        "tender": {
            "title": "Travaux de construction",
            "reference": "AO-2026-01",
            "contracting_authority": None,
            "estimated_budget": 100000,
            "currency": "MAD",
            "deadline": None,
            "provisional_guarantee": None,
        },
        "conditions": [
            {"condition_type": "experience", "description": "5 ans"}
        ],
        "documents": [],
        "criteria": [],
        "evidence": [],
    }

    second_json = {
        "tender": {
            "title": "Autre titre",
            "reference": None,
            "contracting_authority": "Commune de test",
            "estimated_budget": None,
            "currency": None,
            "deadline": "31/12/2026",
            "provisional_guarantee": None,
        },
        "conditions": [],
        "documents": [
            {
                "name": "CPS",
                "description": "Cahier des prescriptions spéciales",
                "is_mandatory": True,
            }
        ],
        "criteria": [],
        "evidence": [],
    }

    responses = iter([
        json.dumps(first_json),
        json.dumps(second_json),
    ])

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        return f"Evidence for chunk {index}"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return next(responses), "stop"

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk 1", "chunk 2"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):

        result = await ai_analyzer.extract_structured_tender(
            "text for testing"
        )

    assert result.tender.title == "Travaux de construction"
    assert result.tender.reference == "AO-2026-01"
    assert result.tender.contracting_authority == "Commune de test"
    assert result.tender.estimated_budget == 100000
    assert result.tender.deadline == "31/12/2026"
    assert len(result.conditions) == 1
    assert len(result.documents) == 1


@pytest.mark.asyncio
async def test_analyze_tender_populates_shared_evidence_cache():
    from app.services import ai_analyzer

    evidence_cache = []

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        return f"Evidence for chunk {index}"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return "Rapport complet", "stop"

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        report = await ai_analyzer.analyze_tender(
            "text for testing",
            evidence_cache=evidence_cache,
        )

    assert report == "Rapport complet"
    assert len(evidence_cache) == 1
    assert evidence_cache[0][0] == "Evidence for chunk 1"
    assert isinstance(evidence_cache[0][1], ChunkExtractionStatus)


@pytest.mark.asyncio
async def test_extract_structured_tender_reuses_cached_evidence():
    from app.services import ai_analyzer
    from app.schemas.analysis import AnalysisMetadata

    metadata = AnalysisMetadata()
    cached_status = ChunkExtractionStatus(fallback_used=True, truncated=True)
    evidence_cache = [("CACHED EVIDENCE", cached_status)]
    payload = {"tender": {"title": "Titre extrait depuis le cache"}}

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        assert "CACHED EVIDENCE" in user_message
        return json.dumps(payload), "stop"

    extract_mock = AsyncMock(
        side_effect=AssertionError("Evidence must not be extracted twice.")
    )

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk"]),
        patch.object(ai_analyzer, "_extract_chunk", new=extract_mock),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        result = await ai_analyzer.extract_structured_tender(
            "text for testing",
            metadata=metadata,
            evidence_cache=evidence_cache,
        )

    extract_mock.assert_not_awaited()
    assert result.tender.title == "Titre extrait depuis le cache"
    assert metadata.fallback_used is True
    assert metadata.structured_truncated is True


from app.services.deadline_parser import parse_deadline


@pytest.mark.parametrize(
    ("deadline_text", "expected"),
    [
        ("2026-11-15", date(2026, 11, 15)),
        ("15/11/2026", date(2026, 11, 15)),
        ("15-11-2026", date(2026, 11, 15)),
        ("15 novembre 2026", date(2026, 11, 15)),
        ("15 novembre 2026 à 12 h 00", date(2026, 11, 15)),
        ("15 novembre 2026 à 12:00", date(2026, 11, 15)),
        ("15 Novembre 2026 à 12 h 00", date(2026, 11, 15)),
        ("15 fevrier 2026", date(2026, 2, 15)),
        ("15 février 2026", date(2026, 2, 15)),
        ("15 aout 2026", date(2026, 8, 15)),
        ("15 août 2026", date(2026, 8, 15)),
        ("1er novembre 2026", date(2026, 11, 1)),
        ("15 November 2026 at 12:00", date(2026, 11, 15)),
        ("31/12/2026", date(2026, 12, 31)),
    ],
)
def test_deadline_date_formats(deadline_text, expected):
    assert parse_deadline(deadline_text) == expected


@pytest.mark.parametrize(
    "deadline_text",
    [
        None,
        "",
        "   ",
        "date inconnue",
        "31/02/2026",          # invalid calendar day
        "31 février 2026",    # invalid textual calendar date
        "15 xambruary 2026",   # unknown month
    ],
)
def test_deadline_unrecognised_returns_none(deadline_text):
    assert parse_deadline(deadline_text) is None


# ── Structured extraction: technical specifications ──────────────────────────


async def _run_structured_extraction(
    payloads, chunks, document_text="text for testing"
):
    """Run extract_structured_tender with mocked chunking and model calls."""
    from app.services import ai_analyzer

    responses = iter(payloads)

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        return f"Evidence for chunk {index}"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return next(responses), "stop"

    with (
        patch.object(ai_analyzer, "split_document", return_value=list(chunks)),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        return await ai_analyzer.extract_structured_tender(document_text)


def _technical_payload(**technical):
    tender = {
        "title": "Fourniture d'ordinateurs portables",
        "reference": "AO-2026-TECH",
        "contracting_authority": "Commune de test",
        "estimated_budget": 250000,
        "currency": "MAD",
        "deadline": "31/12/2026",
        "provisional_guarantee": None,
    }
    tender.update(technical)
    return {
        "tender": tender,
        "conditions": [],
        "documents": [],
        "criteria": [],
        "evidence": [],
    }


def _payload_with_evidence(*items):
    payload = _technical_payload()
    payload["evidence"] = list(items)
    return payload

@pytest.mark.asyncio
async def test_extract_structured_tender_deduplicates_merged_collections():
    first = _technical_payload()
    first["conditions"] = [
        {"condition_type": "experience", "description": "5 ans"},
        {"condition_type": "experience", "description": "5 ans"},
        {"condition_type": "experience", "description": "3 ans"},
    ]
    first["documents"] = [
        {
            "name": "CPS",
            "description": "Cahier des prescriptions spéciales",
            "is_mandatory": True,
        },
        {
            "name": "CPS",
            "description": "Cahier des prescriptions spéciales",
            "is_mandatory": True,
        },
    ]
    first["criteria"] = [
        {"name": "Prix", "description": "Offre financière", "weight": 60},
        {"name": "Prix", "description": "Offre financière", "weight": 60},
        {"name": "Prix", "description": "Offre financière", "weight": 40},
    ]
    first["evidence"] = [
        {
            "field_name": "quantity",
            "extracted_value": "10",
            "page_number": 1,
            "source_text": "Quantité : 10",
        },
        {
            "field_name": "quantity",
            "extracted_value": "10",
            "page_number": 1,
            "source_text": "Quantité : 10",
        },
    ]

    second = _technical_payload()
    second["documents"] = [
        {
            "name": "CPS",
            "description": "Cahier des prescriptions spéciales",
            "is_mandatory": False,
        }
    ]
    second["evidence"] = [
        {
            "field_name": "quantity",
            "extracted_value": "20",
            "page_number": 1,
            "source_text": "Quantité : 20",
        }
    ]

    document_text = (
        "--- Page 1 ---\n"
        "Quantité : 10\n"
        "Quantité : 20"
    )

    result = await _run_structured_extraction(
        [json.dumps(first), json.dumps(second)],
        ["chunk 1", "chunk 2"],
        document_text=document_text,
    )

    assert len(result.conditions) == 2
    assert len(result.documents) == 2
    assert len(result.criteria) == 2
    assert len(result.evidence) == 2
    assert result.verified_evidence_count == 2
    assert result.rejected_evidence_count == 0


@pytest.mark.asyncio
async def test_extract_structured_tender_extracts_technical_specifications():
    payload = _technical_payload(
        quantity=10,
        processor="Intel Core i7-1355U",
        ram_gb=16,
        storage_gb=512,
        screen_size_inches=15.6,
        warranty_months=24,
        accessories=["charger", "laptop bag"],
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["technical chunk"]
    )

    assert result.tender.quantity == 10
    assert result.tender.processor == "Intel Core i7-1355U"
    assert result.tender.ram_gb == 16
    assert result.tender.storage_gb == 512
    assert result.tender.screen_size_inches == 15.6
    assert result.tender.warranty_months == 24
    assert result.tender.accessories == ["charger", "laptop bag"]


@pytest.mark.asyncio
async def test_extract_structured_tender_missing_technical_specs_are_null():
    payload = _technical_payload()

    result = await _run_structured_extraction([json.dumps(payload)], ["chunk"])

    assert result.tender.quantity is None
    assert result.tender.processor is None
    assert result.tender.ram_gb is None
    assert result.tender.storage_gb is None
    assert result.tender.screen_size_inches is None
    assert result.tender.warranty_months is None
    assert result.tender.accessories == []
    assert not [
        item for item in result.evidence
        if item.field_name.startswith("conflict:")
    ]
    assert result.extraction_conflicts == []


@pytest.mark.asyncio
async def test_extract_structured_tender_preserves_technical_fields_across_chunks():
    first = _technical_payload(
        quantity=10,
        processor="Intel Core i5-1235U",
        ram_gb=16,
        accessories=["charger"],
    )
    second = _technical_payload(
        storage_gb=512,
        screen_size_inches=15.6,
        warranty_months=24,
        accessories=["laptop bag", "charger"],
    )

    result = await _run_structured_extraction(
        [json.dumps(first), json.dumps(second)],
        ["chunk 1", "chunk 2"],
    )

    assert result.tender.quantity == 10
    assert result.tender.processor == "Intel Core i5-1235U"
    assert result.tender.ram_gb == 16
    assert result.tender.storage_gb == 512
    assert result.tender.screen_size_inches == 15.6
    assert result.tender.warranty_months == 24
    assert result.tender.accessories == ["charger", "laptop bag"]
    assert not [
        item for item in result.evidence
        if item.field_name.startswith("conflict:")
    ]
    assert result.extraction_conflicts == []


@pytest.mark.asyncio
async def test_extract_structured_tender_invalid_technical_values_become_null():
    payload = _technical_payload(
        quantity="10",
        processor=123,
        ram_gb="16 GB",
        storage_gb=1.5,
        screen_size_inches="15.6 inches",
        warranty_months="24 months",
        accessories="charger",
    )

    result = await _run_structured_extraction([json.dumps(payload)], ["chunk"])

    assert result.tender.quantity is None
    assert result.tender.processor is None
    assert result.tender.ram_gb is None
    assert result.tender.storage_gb is None
    assert result.tender.screen_size_inches is None
    assert result.tender.warranty_months is None
    assert result.tender.accessories == []


@pytest.mark.asyncio
async def test_extract_structured_tender_records_conflicting_technical_values():
    first = _technical_payload(
        quantity=10,
        processor="Intel Core i5-1235U",
        ram_gb=16,
        accessories=["charger"],
    )
    first["evidence"] = [
        {
            "field_name": "quantity",
            "extracted_value": "10",
            "page_number": 1,
            "source_text": "Quantité : 10 unités",
        }
    ]
    second = _technical_payload(
        quantity=20,
        processor="Intel Core i7-1355U",
        ram_gb=32,
        accessories=["laptop bag"],
    )
    second["evidence"] = [
        {
            "field_name": "quantity",
            "extracted_value": "20",
            "page_number": 2,
            "source_text": "Quantité : 20 unités",
        }
    ]

    result = await _run_structured_extraction(
        [json.dumps(first), json.dumps(second)],
        ["chunk 1", "chunk 2"],
        document_text=(
            "--- Page 1 ---\nQuantité : 10 unités\n\n"
            "--- Page 2 ---\nQuantité : 20 unités"
        ),
    )

    # First known values are retained, not silently overwritten.
    assert result.tender.quantity == 10
    assert result.tender.processor == "Intel Core i5-1235U"
    assert result.tender.ram_gb == 16
    assert result.tender.accessories == ["charger", "laptop bag"]

    # Conflicts are stored separately from PDF evidence.
    assert len(result.extraction_conflicts) == 3
    assert all(
        not item.field_name.startswith("conflict:")
        for item in result.evidence
    )
    assert [item.source_text for item in result.evidence] == [
        "Quantité : 10 unités",
        "Quantité : 20 unités",
    ]
    assert result.verified_evidence_count == 2
    assert result.rejected_evidence_count == 0
    assert result.corrected_page_count == 0
    assert result.ambiguous_evidence_count == 0

    conflicts = {
        item.field_name: item for item in result.extraction_conflicts
    }

    assert conflicts["quantity"].first_value == 10
    assert conflicts["quantity"].second_value == 20
    assert conflicts["quantity"].first_chunk_index == 1
    assert conflicts["quantity"].second_chunk_index == 2

    assert conflicts["processor"].first_value == "Intel Core i5-1235U"
    assert conflicts["processor"].second_value == "Intel Core i7-1355U"
    assert conflicts["processor"].first_chunk_index == 1
    assert conflicts["processor"].second_chunk_index == 2

    assert conflicts["ram_gb"].first_value == 16
    assert conflicts["ram_gb"].second_value == 32
    assert conflicts["ram_gb"].first_chunk_index == 1
    assert conflicts["ram_gb"].second_chunk_index == 2


@pytest.mark.asyncio
async def test_extract_structured_tender_deduplicates_identical_conflicts():
    first = _technical_payload(quantity=10)
    second = _technical_payload(quantity=20)
    third = _technical_payload(quantity=20)

    result = await _run_structured_extraction(
        [json.dumps(first), json.dumps(second), json.dumps(third)],
        ["chunk 1", "chunk 2", "chunk 3"],
    )

    assert len(result.extraction_conflicts) == 1
    conflict = result.extraction_conflicts[0]
    assert conflict.field_name == "quantity"
    assert conflict.first_value == 10
    assert conflict.second_value == 20
    assert conflict.first_chunk_index == 1
    assert conflict.second_chunk_index == 2


@pytest.mark.asyncio
async def test_extract_structured_tender_backward_compatible_payload():
    legacy = {
        "tender": {
            "title": "Legacy tender",
            "reference": "AO-LEGACY",
            "contracting_authority": "Commune de test",
            "estimated_budget": 100000,
            "currency": "MAD",
            "deadline": "31/12/2026",
            "provisional_guarantee": "5000 MAD",
        },
        "conditions": [],
        "documents": [],
        "criteria": [],
        "evidence": [],
    }

    result = await _run_structured_extraction([json.dumps(legacy)], ["chunk"])

    assert result.tender.title == "Legacy tender"
    assert result.tender.reference == "AO-LEGACY"
    assert result.tender.estimated_budget == 100000
    assert result.tender.quantity is None
    assert result.tender.processor is None
    assert result.tender.ram_gb is None
    assert result.tender.storage_gb is None
    assert result.tender.screen_size_inches is None
    assert result.tender.warranty_months is None
    assert result.tender.accessories == []
    assert result.extraction_conflicts == []
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 0
    assert result.corrected_page_count == 0
    assert result.ambiguous_evidence_count == 0


# ── PDF evidence verification ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_evidence_accepts_exact_quote():
    document = (
        "--- Page 1 ---\nBudget estimé : 250 000 MAD\n\n"
        "--- Page 2 ---\nDélai : 31/12/2026"
    )
    payload = _payload_with_evidence(
        {
            "field_name": "estimated_budget",
            "extracted_value": "250000",
            "page_number": 1,
            "source_text": "Budget estimé : 250 000 MAD",
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert len(result.evidence) == 1
    assert result.evidence[0].page_number == 1
    assert result.evidence[0].source_text == "Budget estimé : 250 000 MAD"
    assert result.verified_evidence_count == 1
    assert result.rejected_evidence_count == 0
    assert result.corrected_page_count == 0
    assert result.ambiguous_evidence_count == 0


@pytest.mark.asyncio
async def test_verify_evidence_normalises_whitespace():
    document = "--- Page 1 ---\nBudget estimé : 250 000 MAD"
    payload = _payload_with_evidence(
        {
            "field_name": "estimated_budget",
            "extracted_value": "250000",
            "page_number": 1,
            "source_text": "Budget   estimé\t:\n250 000 MAD",
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert len(result.evidence) == 1
    assert result.verified_evidence_count == 1
    assert result.rejected_evidence_count == 0


@pytest.mark.asyncio
async def test_verify_evidence_corrects_wrong_page_number():
    document = (
        "--- Page 1 ---\nBudget estimé : 250 000 MAD\n\n"
        "--- Page 2 ---\nDélai : 31/12/2026"
    )
    payload = _payload_with_evidence(
        {
            "field_name": "deadline",
            "extracted_value": "31/12/2026",
            "page_number": 1,
            "source_text": "Délai : 31/12/2026",
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert len(result.evidence) == 1
    assert result.evidence[0].page_number == 2
    assert result.evidence[0].source_text == "Délai : 31/12/2026"
    assert result.verified_evidence_count == 1
    assert result.corrected_page_count == 1
    assert result.rejected_evidence_count == 0
    assert result.ambiguous_evidence_count == 0


@pytest.mark.asyncio
async def test_verify_evidence_rejects_value_not_present_in_quote():
    document = "--- Page 1 ---\nQuantité : 10 unités"
    payload = _payload_with_evidence(
        {
            "field_name": "quantity",
            "extracted_value": "20",
            "page_number": 1,
            "source_text": "Quantité : 10 unités",
        }
    )
    payload["tender"]["quantity"] = 20

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert result.evidence == []
    assert result.tender.quantity is None
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 1


@pytest.mark.asyncio
async def test_verify_evidence_accepts_numeric_value_with_grouping_spaces():
    document = "--- Page 1 ---\nBudget estimé : 250 000 MAD"
    payload = _payload_with_evidence(
        {
            "field_name": "estimated_budget",
            "extracted_value": "250000",
            "page_number": 1,
            "source_text": "Budget estimé : 250 000 MAD",
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert len(result.evidence) == 1
    assert result.tender.estimated_budget == 250000
    assert result.verified_evidence_count == 1
    assert result.rejected_evidence_count == 0


@pytest.mark.asyncio
async def test_verify_evidence_rejects_wrong_numeric_value_even_if_quote_exists():
    document = "--- Page 1 ---\nRAM : 16 Go"
    payload = _payload_with_evidence(
        {
            "field_name": "ram_gb",
            "extracted_value": "32",
            "page_number": 1,
            "source_text": "RAM : 16 Go",
        }
    )
    payload["tender"]["ram_gb"] = 32

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert result.evidence == []
    assert result.tender.ram_gb is None
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 1


@pytest.mark.asyncio
async def test_verify_evidence_rejects_quote_labelled_for_another_field():
    document = "--- Page 1 ---\nQuantité : 16 unités"
    payload = _payload_with_evidence(
        {
            "field_name": "ram_gb",
            "extracted_value": "16",
            "page_number": 1,
            "source_text": "Quantité : 16 unités",
        }
    )
    payload["tender"]["ram_gb"] = 16

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert result.evidence == []
    assert result.tender.ram_gb is None
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 1


@pytest.mark.asyncio
async def test_verify_evidence_does_not_match_numeric_substrings():
    document = "--- Page 1 ---\nRAM : 160 Go"
    payload = _payload_with_evidence(
        {
            "field_name": "ram_gb",
            "extracted_value": "16",
            "page_number": 1,
            "source_text": "RAM : 160 Go",
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert result.evidence == []
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 1


@pytest.mark.asyncio
async def test_verify_evidence_rejects_missing_quote():
    document = "--- Page 1 ---\nBudget estimé : 250 000 MAD"
    payload = _payload_with_evidence(
        {
            "field_name": "deadline",
            "extracted_value": "31/12/2026",
            "page_number": 1,
            "source_text": "Cette phrase n'existe pas dans le document",
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert result.evidence == []
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 1
    assert result.corrected_page_count == 0
    assert result.ambiguous_evidence_count == 0

@pytest.mark.asyncio
@pytest.mark.parametrize("source_text", ["", "   ", "\n\t"])
async def test_verify_evidence_rejects_empty_quote(source_text):
    document = "--- Page 1 ---\nBudget estimé : 250 000 MAD"

    payload = _payload_with_evidence(
        {
            "field_name": "estimated_budget",
            "extracted_value": "250000",
            "page_number": 1,
            "source_text": source_text,
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert result.evidence == []
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 1
    assert result.corrected_page_count == 0
    assert result.ambiguous_evidence_count == 0

@pytest.mark.asyncio
async def test_verify_evidence_marks_ambiguous_quotes():
    document = (
        "--- Page 1 ---\nMontant : 250 000 MAD\n\n"
        "--- Page 2 ---\nMontant : 250 000 MAD"
    )
    payload = _payload_with_evidence(
        {
            "field_name": "estimated_budget",
            "extracted_value": "250000",
            "page_number": 99,
            "source_text": "Montant : 250 000 MAD",
        }
    )

    result = await _run_structured_extraction(
        [json.dumps(payload)], ["chunk"], document_text=document
    )

    assert result.evidence == []
    assert result.verified_evidence_count == 0
    assert result.rejected_evidence_count == 0
    assert result.corrected_page_count == 0
    assert result.ambiguous_evidence_count == 1


@pytest.mark.asyncio
async def test_verify_evidence_preserves_extraction_conflicts():
    document = "--- Page 1 ---\nQuantité : 10 unités"
    first = _technical_payload(quantity=10)
    first["evidence"] = [
        {
            "field_name": "quantity",
            "extracted_value": "10",
            "page_number": 1,
            "source_text": "Quantité : 10 unités",
        }
    ]
    second = _technical_payload(quantity=20)
    second["evidence"] = [
        {
            "field_name": "quantity",
            "extracted_value": "20",
            "page_number": 1,
            "source_text": "Quantité : 20 unités",
        }
    ]

    result = await _run_structured_extraction(
        [json.dumps(first), json.dumps(second)],
        ["chunk 1", "chunk 2"],
        document_text=document,
    )

    assert result.tender.quantity == 10
    assert len(result.extraction_conflicts) == 1
    assert result.extraction_conflicts[0].field_name == "quantity"
    assert result.extraction_conflicts[0].first_value == 10
    assert result.extraction_conflicts[0].second_value == 20
    assert result.verified_evidence_count == 1
    assert result.rejected_evidence_count == 1
    assert [item.source_text for item in result.evidence] == [
        "Quantité : 10 unités"
    ]


# ── Phase 4: execution / quality metadata ─────────────────────────────────────


async def _run_analyze_tender(
    chunk_evidence,
    final_content="Rapport complet",
    final_finish="stop",
    metadata=None,
):
    """Run analyze_tender with mocked chunking and model calls."""
    from app.services import ai_analyzer

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        if callable(chunk_evidence):
            return chunk_evidence(status)
        return chunk_evidence

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return final_content, final_finish

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        return await ai_analyzer.analyze_tender("text", metadata=metadata)


@pytest.mark.asyncio
async def test_analyze_tender_records_clean_metadata():
    metadata = AnalysisMetadata()

    report = await _run_analyze_tender("Evidence", metadata=metadata)

    assert report == "Rapport complet"
    assert metadata.fallback_used is False
    assert metadata.report_truncated is False


@pytest.mark.asyncio
async def test_analyze_tender_records_explicit_chunk_status():
    metadata = AnalysisMetadata()

    def evidence_with_status(status):
        status.fallback_used = True
        return "Evidence from fallback"

    await _run_analyze_tender(evidence_with_status, metadata=metadata)

    assert metadata.fallback_used is True
    assert metadata.report_truncated is False

@pytest.mark.asyncio
async def test_analyze_tender_records_explicit_chunk_truncation():
    metadata = AnalysisMetadata()

    def evidence_with_truncation(status):
        status.truncated = True
        return "Evidence was truncated"

    await _run_analyze_tender(
        evidence_with_truncation,
        metadata=metadata,
    )

    assert metadata.report_truncated is True
    assert metadata.fallback_used is False

@pytest.mark.asyncio
async def test_analyze_tender_detects_legacy_fallback_marker():
    metadata = AnalysisMetadata()

    await _run_analyze_tender(
        "[FALLBACK] Evidence extracted using fallback",
        metadata=metadata,
    )

    assert metadata.fallback_used is True
    assert metadata.report_truncated is False

@pytest.mark.asyncio
async def test_analyze_tender_detects_legacy_partial_marker():
    metadata = AnalysisMetadata()

    await _run_analyze_tender("[PARTIAL] Evidence cut off", metadata=metadata)

    assert metadata.fallback_used is True
    assert metadata.report_truncated is True


@pytest.mark.asyncio
async def test_analyze_tender_returns_partial_report_and_marks_truncation():
    metadata = AnalysisMetadata()

    report = await _run_analyze_tender(
        "Evidence",
        final_content="Rapport partiel",
        final_finish="length",
        metadata=metadata,
    )

    assert report == "Rapport partiel"
    assert metadata.report_truncated is True


@pytest.mark.asyncio
async def test_analyze_tender_raises_on_truncated_report_without_metadata():
    with pytest.raises(RuntimeError):
        await _run_analyze_tender(
            "Evidence",
            final_content="Rapport partiel",
            final_finish="length",
            metadata=None,
        )


async def _run_structured_metadata(responses, chunks, document_text, metadata):
    """Run extract_structured_tender with mocked calls and metadata."""
    from app.services import ai_analyzer

    response_iter = iter(responses)

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        return f"Evidence for chunk {index}"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        response = next(response_iter)

        if isinstance(response, BaseException):
            raise response

        return response

    with (
        patch.object(ai_analyzer, "split_document", return_value=list(chunks)),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        return await ai_analyzer.extract_structured_tender(
            document_text, metadata=metadata
        )


@pytest.mark.asyncio
async def test_extract_structured_tender_marks_truncation_with_metadata():
    metadata = AnalysisMetadata()

    result = await _run_structured_metadata(
        [(json.dumps(_technical_payload()), "length")],
        ["chunk"],
        "text for testing",
        metadata,
    )

    assert isinstance(result, StructuredTenderAnalysis)
    assert metadata.structured_truncated is True
    assert metadata.structured_failed is False


@pytest.mark.asyncio
async def test_extract_structured_tender_raises_on_truncation_without_metadata():
    from app.services import ai_analyzer

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        return "Evidence"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return json.dumps(_technical_payload()), "length"

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):

        with pytest.raises(RuntimeError):
            await ai_analyzer.extract_structured_tender("text")


@pytest.mark.asyncio
async def test_extract_structured_tender_marks_invalid_json_with_metadata():
    metadata = AnalysisMetadata()

    result = await _run_structured_metadata(
        [("not valid json", "stop")],
        ["chunk"],
        "text for testing",
        metadata,
    )

    assert result.tender.title is None
    assert result.evidence == []
    assert result.conditions == []
    assert result.documents == []
    assert result.criteria == []
    assert metadata.structured_failed is True
    assert metadata.structured_truncated is False


@pytest.mark.asyncio
async def test_extract_structured_tender_keeps_validated_partial_on_failure():
    metadata = AnalysisMetadata()
    valid = json.dumps(
        _technical_payload(title="Marché partiel", quantity=10)
    )

    result = await _run_structured_metadata(
        [(valid, "stop"), ("{broken", "stop")],
        ["chunk 1", "chunk 2"],
        "text for testing",
        metadata,
    )

    assert result.tender.title == "Marché partiel"
    assert result.tender.quantity == 10
    assert metadata.structured_failed is True

@pytest.mark.asyncio
async def test_extract_structured_tender_keeps_partial_on_openrouter_429():
    from app.services import ai_analyzer

    metadata = AnalysisMetadata()
    valid = json.dumps(
        _technical_payload(title="Marché partiel", quantity=10)
    )

    result = await _run_structured_metadata(
        [
            (valid, "stop"),
            ai_analyzer.AIStatusError(429, "Rate limit exceeded"),
        ],
        ["chunk 1", "chunk 2"],
        "text for testing",
        metadata,
    )

    assert result.tender.title == "Marché partiel"
    assert result.tender.quantity == 10
    assert metadata.structured_failed is True

@pytest.mark.asyncio
async def test_extract_structured_tender_handles_evidence_extraction_failure():
    from app.services import ai_analyzer

    metadata = AnalysisMetadata()

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        if index == 1:
            return "Evidence for first chunk"
        raise ai_analyzer.AIConnectionError("Connection failed")

    valid = json.dumps(
        _technical_payload(title="Marché partiel", quantity=10)
    )

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return valid, "stop"

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk 1", "chunk 2"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        result = await ai_analyzer.extract_structured_tender(
            "text for testing",
            metadata=metadata,
        )

    assert result.tender.title == "Marché partiel"
    assert result.tender.quantity == 10
    assert metadata.structured_failed is True

@pytest.mark.asyncio
async def test_extract_structured_tender_raises_on_invalid_json_without_metadata():
    from app.services import ai_analyzer

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        return "Evidence"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return "not valid json", "stop"

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):

        with pytest.raises(RuntimeError):
            await ai_analyzer.extract_structured_tender("text")

@pytest.mark.asyncio
async def test_extract_structured_tender_raises_on_OpenRouter_429_without_metadata():
    from app.services import ai_analyzer

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        return "Evidence"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        raise ai_analyzer.AIStatusError(429, "Rate limit exceeded")

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        with pytest.raises(ai_analyzer.AIStatusError) as exc_info:
            await ai_analyzer.extract_structured_tender("text")

    assert exc_info.value.status_code == 429


def test_build_analysis_metadata_completed_has_no_reasons():
    metadata = build_analysis_metadata(
        AnalysisMetadata(), StructuredTenderAnalysis()
    )

    assert metadata.degradation_reasons == []
    assert analysis_status(metadata) == "analysis_completed"


def test_build_analysis_metadata_copies_counts_and_reasons():
    structured = StructuredTenderAnalysis(
        rejected_evidence_count=2,
        ambiguous_evidence_count=1,
        extraction_conflicts=[
            ExtractionConflictItem(
                field_name="quantity",
                first_value=10,
                second_value=20,
                first_chunk_index=1,
                second_chunk_index=2,
            )
        ],
    )
    metadata = AnalysisMetadata(
        report_truncated=True,
        structured_failed=True,
        fallback_used=True,
    )

    build_analysis_metadata(metadata, structured)

    assert metadata.rejected_evidence_count == 2
    assert metadata.ambiguous_evidence_count == 1
    assert metadata.extraction_conflict_count == 1
    assert metadata.degradation_reasons == [
        "report_truncated",
        "structured_failed",
        "fallback_used",
        "rejected_evidence",
        "ambiguous_evidence",
        "extraction_conflicts",
    ]
    assert analysis_status(metadata) == "analysis_partial"


def test_build_analysis_metadata_does_not_duplicate_reasons():
    metadata = AnalysisMetadata(
        report_truncated=True,
        structured_truncated=True,
        structured_failed=True,
        fallback_used=True,
        degradation_reasons=["report_truncated", "fallback_used"],
    )

    first = build_analysis_metadata(metadata, StructuredTenderAnalysis())
    second = build_analysis_metadata(metadata, StructuredTenderAnalysis())

    assert first.degradation_reasons == [
        "report_truncated",
        "structured_truncated",
        "structured_failed",
        "fallback_used",
    ]
    assert second.degradation_reasons == first.degradation_reasons


async def _run_structured_evidence_status(
    mutate_status, responses, chunks, document_text, metadata
):
    """Run extract_structured_tender with a fake that mutates chunk status."""
    from app.services import ai_analyzer

    response_iter = iter(responses)

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        if status is not None:
            mutate_status(status)
        return f"Evidence for chunk {index}"

    async def fake_call_openrouter(
        client, system_prompt, user_message, max_tokens
    ):
        return next(response_iter)

    with (
        patch.object(ai_analyzer, "split_document", return_value=list(chunks)),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_call_openrouter", side_effect=fake_call_openrouter),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        return await ai_analyzer.extract_structured_tender(
            document_text, metadata=metadata
        )


@pytest.mark.asyncio
async def test_extract_structured_tender_records_evidence_fallback():
    metadata = AnalysisMetadata()

    await _run_structured_evidence_status(
        lambda status: setattr(status, "fallback_used", True),
        [(json.dumps(_technical_payload()), "stop")],
        ["chunk"],
        "text for testing",
        metadata,
    )

    assert metadata.fallback_used is True
    assert metadata.structured_truncated is False


@pytest.mark.asyncio
async def test_extract_structured_tender_records_evidence_truncation():
    metadata = AnalysisMetadata()

    await _run_structured_evidence_status(
        lambda status: setattr(status, "truncated", True),
        [(json.dumps(_technical_payload()), "stop")],
        ["chunk"],
        "text for testing",
        metadata,
    )

    assert metadata.structured_truncated is True
    assert metadata.fallback_used is False


# ── Regression: numeric evidence[].extracted_value ────────────────────────────


def _sample_payload_with_numeric_evidence():
    payload = _technical_payload(quantity=500)
    payload["evidence"] = [
        {
            "field_name": "estimated_budget",
            "extracted_value": 250000,
            "page_number": 1,
            "source_text": "Budget : 250 000 MAD",
        },
        {
            "field_name": "quantity",
            "extracted_value": 500,
            "page_number": 1,
            "source_text": "Quantité : 500 unités",
        },
        {
            "field_name": "ram_gb",
            "extracted_value": 16,
            "page_number": 1,
            "source_text": "RAM : 16 Go",
        },
        {
            "field_name": "storage_gb",
            "extracted_value": 512,
            "page_number": 1,
            "source_text": "Stockage : 512 Go",
        },
        {
            "field_name": "screen_size_inches",
            "extracted_value": 15.6,
            "page_number": 1,
            "source_text": "Écran : 15.6 pouces",
        },
        {
            "field_name": "warranty_months",
            "extracted_value": 24,
            "page_number": 1,
            "source_text": "Garantie : 24 mois",
        },
    ]
    return payload


def test_normalise_structured_payload_stringifies_numeric_evidence():
    payload = _sample_payload_with_numeric_evidence()

    normalised = _normalise_structured_payload(payload)
    assert isinstance(normalised, dict)

    evidence = normalised["evidence"]

    assert isinstance(evidence, list)

    values = [item["extracted_value"] for item in evidence]

    assert values == ["250000", "500", "16", "512", "15.6", "24"]
    assert all(isinstance(value, str) for value in values)


def test_normalise_structured_payload_keeps_tender_numbers_native():
    payload = _technical_payload(
        quantity=500,
        ram_gb=16,
        storage_gb=512,
        screen_size_inches=15.6,
        warranty_months=24,
    )

    normalised = _normalise_structured_payload(payload)
    assert isinstance(normalised, dict)
    tender = normalised["tender"]
    assert isinstance(tender, dict)

    assert tender["quantity"] == 500
    assert tender["ram_gb"] == 16
    assert tender["storage_gb"] == 512
    assert tender["screen_size_inches"] == 15.6
    assert tender["warranty_months"] == 24
    assert isinstance(normalised, dict)


def test_normalise_structured_payload_rejects_non_scalar_evidence_values():
    payload = _technical_payload()
    payload["evidence"] = [
        {
            "field_name": "x",
            "extracted_value": [1, 2],
            "page_number": 1,
            "source_text": "x",
        },
        {
            "field_name": "y",
            "extracted_value": {"a": 1},
            "page_number": 1,
            "source_text": "y",
        },
    ]

    normalised = _normalise_structured_payload(payload)
    assert isinstance(normalised, dict)
    evidence = normalised["evidence"]
    assert isinstance(evidence, list)
    assert evidence[0]["extracted_value"] == [1, 2]
    assert evidence[1]["extracted_value"] == {"a": 1}
    with pytest.raises(ValidationError):
        StructuredTenderAnalysis.model_validate(normalised)

@pytest.mark.asyncio
async def test_extract_structured_tender_accepts_numeric_evidence_values():
    """The reported sample must not fail validation only because values are numeric."""
    metadata = AnalysisMetadata()
    document = (
        "--- Page 1 ---\nBudget : 250 000 MAD\nQuantité : 500 unités\n"
        "RAM : 16 Go\nStockage : 512 Go\nÉcran : 15.6 pouces\n"
        "Garantie : 24 mois"
    )
    payload = _sample_payload_with_numeric_evidence()

    result = await _run_structured_metadata(
        [(json.dumps(payload), "stop")],
        ["chunk"],
        document,
        metadata,
    )

    assert metadata.structured_failed is False
    assert [item.extracted_value for item in result.evidence] == [
        "250000",
        "500",
        "16",
        "512",
        "15.6",
        "24",
    ]


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("40 000,00 MAD, valable 120 jours", "40 000 MAD", True),
        ("40 000 MAD", "40000.00 MAD", True),
        ("40 000 MAD", "45 000 MAD", False),
        ("40 000 MAD", "40 000 EUR", False),
        ("Montant non précisé", "40 000 MAD", False),
    ],
)
def test_provisional_guarantee_comparison(first, second, expected):
    from app.services.ai_analyzer import _scalar_values_equivalent

    assert (
        _scalar_values_equivalent("provisional_guarantee", first, second)
        is expected
    )

def test_authority_scalar_comparison_uses_authority_equivalence():
    from app.services.ai_analyzer import _scalar_values_equivalent

    assert _scalar_values_equivalent(
        "contracting_authority",
        "Agence Régionale de Modernisation Administrative (ARMA)",
        "ARMA",
    ) is True

    assert _scalar_values_equivalent(
        "contracting_authority",
        "Commune de Rabat",
        "Commune de Salé",
    ) is False


def test_technical_scalar_comparison_remains_strict():
    from app.services.ai_analyzer import _scalar_values_equivalent

    assert not _scalar_values_equivalent("quantity", 10, 20)
    assert not _scalar_values_equivalent(
        "processor",
        "Intel Core i5",
        "Intel Core i7",
    )

@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (
            "Mardi 15 d\u00e9cembre 2026 \u00e0 10h00 (heure du Maroc, GMT+1)",
            "15 d\u00e9cembre 2026 \u00e0 10h00",
            True,
        ),
        (
            "15 d\u00e9cembre 2026 \u00e0 10h00",
            "15 d\u00e9cembre 2026 \u00e0 10 h 00",
            True,
        ),
        (
            "15 d\u00e9cembre 2026 \u00e0 10h00",
            "15 d\u00e9cembre 2026 \u00e0 11:00",
            False,
        ),
        (
            "15 d\u00e9cembre 2026",
            "15 d\u00e9cembre 2026 \u00e0 10h00",
            False,
        ),
        (
            "15 d\u00e9cembre 2026 \u00e0 10h00",
            "16 d\u00e9cembre 2026 \u00e0 10h00",
            False,
        ),
    ],
)

def test_deadline_scalar_comparison(first, second, expected):
    from app.services.ai_analyzer import _scalar_values_equivalent

    assert (
        _scalar_values_equivalent("deadline", first, second)
        is expected
    )


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (
            "Agence Régionale de Modernisation Administrative "
            "de Fès-Meknès (ARMA-FM)",
            "ARMA-FM",
            True,
        ),
        (
            "ARMA-FM",
            "Agence Régionale de Modernisation Administrative "
            "de Fès-Meknès (ARMA-FM)",
            True,
        ),
        ("ARMA-FM", "ARMA-FX", False),
        ("Agence Régionale de Modernisation Administrative", "ARMA-FM", False),
        ("", "ARMA-FM", False),
        (None, "ARMA-FM", False),
    ],
)
def test_authority_values_equivalent(first, second, expected):
    from app.services.ai_analyzer import _authority_values_equivalent

    assert _authority_values_equivalent(first, second) is expected


class TestOpenRouterClientLifecycle:

    def test_create_client_rejects_missing_api_key(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "")

        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            _create_client()

    def test_create_client_rejects_missing_model(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
        monkeypatch.setattr(settings, "openrouter_model", "")

        with pytest.raises(RuntimeError, match="OPENROUTER_MODEL"):
            _create_client()

    def test_create_client_uses_configured_credentials(self, monkeypatch):
        fake_client = MagicMock()
        client_factory = MagicMock(return_value=fake_client)

        monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
        monkeypatch.setattr(settings, "openrouter_model", "test-model")
        monkeypatch.setattr(
            settings,
            "openrouter_base_url",
            "https://openrouter.ai/api/v1",
        )
        monkeypatch.setattr(
            "app.services.ai_analyzer.httpx.AsyncClient",
            client_factory,
        )

        result = _create_client()

        assert result is fake_client
        client_factory.assert_called_once()

        kwargs = client_factory.call_args.kwargs
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1/"
        assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"
        assert kwargs["timeout"].read == 180.0

    @pytest.mark.asyncio
    async def test_open_client_closes_transport_after_success(self, monkeypatch):
        fake_client = MagicMock()
        fake_client.aclose = AsyncMock()

        monkeypatch.setattr(
            "app.services.ai_analyzer._create_client",
            lambda: fake_client,
        )

        async with _open_client() as client:
            assert client is fake_client

        fake_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_client_closes_transport_after_exception(self, monkeypatch):
        fake_client = MagicMock()
        fake_client.aclose = AsyncMock()

        monkeypatch.setattr(
            "app.services.ai_analyzer._create_client",
            lambda: fake_client,
        )

        with pytest.raises(RuntimeError, match="simulated failure"):
            async with _open_client():
                raise RuntimeError("simulated failure")

        fake_client.aclose.assert_awaited_once()


@pytest.mark.parametrize(
    ("value", "minimum", "expected"),
    [
        (10, 1, 10),          # Integer مقبول
        (0, 0, 0),            # الحد الأدنى مقبول
        (-1, 0, None),        # أقل من الحد الأدنى
        (10.0, 1, 10),        # Float صحيح عددياً
        (10.5, 1, None),      # Float عشري
        (True, 1, None),      # Boolean مرفوض
        (False, 0, None),     # Boolean مرفوض حتى لو False
        ("10", 1, None),      # String مرفوض
        (None, 1, None),      # None مرفوض
    ],
)
def test_clean_int(value, minimum, expected):
    assert _clean_int(value, minimum) == expected

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        (1234, None),
        ("Budget: 1.234,56 MAD", (Decimal("1234.56"), "MAD")),
        ("Budget: 1,234.56 MAD", (Decimal("1234.56"), "MAD")),
        ("Budget: 1.234 MAD", (Decimal("1234"), "MAD")),
        ("Budget: 1,234 MAD", (Decimal("1234"), "MAD")),
        ("Budget: 2500 DH", (Decimal("2500"), "MAD")),
        ("Budget: 2500 DHS", (Decimal("2500"), "MAD")),
        ("Budget: 2500 EUR", (Decimal("2500"), "EUR")),
        ("Budget: 2500 USD", (Decimal("2500"), "USD")),
        ("Budget: 2500 GBP", (Decimal("2500"), "GBP")),
        ("Budget: 2500 €", (Decimal("2500"), "EUR")),
        ("Budget: 2500 £", (Decimal("2500"), "GBP")),
        ("Budget: 100 MAD and 200 EUR", None),
        ("Budget: 1.234,567.89 MAD", None),
        ("No amount here", None),
    ],
)
def test_money_signature(value, expected):
    assert _money_signature(value) == expected

@pytest.mark.parametrize(
    ("value", "expected_time"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("No valid date here", None),
        ("15 novembre 2026 à 10:30", "10:30"),
        ("15 novembre 2026 à 9h05", "09:05"),
        ("15/12/2026", None),
        ("15 novembre 2026 à 10:30 et 11:00", None),
        ("15 novembre 2026 à 24:00", None),
        ("15 novembre 2026 à 10:60", None),
    ],
)
def test_deadline_signature(value, expected_time):
    result = _deadline_signature(value)


    if expected_time is None:
        assert result is None or result[1] is None
        if result is not None:
            assert result[1] is None
    else:
        assert result is not None
        assert result[1] == expected_time

@pytest.mark.parametrize(
    "evidence",
    [
        None,
        "invalid evidence",
        {"extracted_value": 250000},
        123,
    ],
)
def test_normalise_evidence_values_preserves_non_list(evidence):
    from app.services.ai_analyzer import _normalise_evidence_values

    assert _normalise_evidence_values(evidence) is evidence

@pytest.mark.parametrize("data", [None, "invalid", [], 123])
def test_normalise_structured_payload_preserves_non_dict(data):
    assert _normalise_structured_payload(data) is data

def test_normalise_structured_payload_normalises_evidence_without_tender():
    payload = {
        "evidence": [
            {"extracted_value": 250000}
        ]
    }

    normalised = _normalise_structured_payload(payload)

    assert normalised == {
        "evidence": [
            {"extracted_value": "250000"}
        ]
    }

def test_build_page_map_merges_repeated_page_markers():
    text = (
        "--- Page 1 ---\nFirst part.\n"
        "--- Page 1 ---\nSecond part."
    )

    assert _build_page_map(text) == {
        1: "First part. Second part."
    }
def test_build_page_map_returns_empty_for_blank_text():
    assert _build_page_map("") == {}
    assert _build_page_map("   \n  ") == {}

@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
async def test_analyze_tender_rejects_empty_text(text):
    with pytest.raises(
        ValueError,
        match="No text was provided for analysis.",
    ):
        await analyze_tender(text)

@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
async def test_extract_structured_tender_rejects_empty_text(text):
    with pytest.raises(
        ValueError,
        match="No text was provided for structured extraction.",
    ):
        await extract_structured_tender(text)

@pytest.mark.asyncio
async def test_extract_structured_tender_propagates_evidence_failure_without_metadata():
    from app.services import ai_analyzer

    async def fake_extract_chunk(client, chunk, index, total, status=None):
        raise ai_analyzer.AIConnectionError("Connection failed")

    with (
        patch.object(ai_analyzer, "split_document", return_value=["chunk"]),
        patch.object(ai_analyzer, "_extract_chunk", side_effect=fake_extract_chunk),
        patch.object(ai_analyzer, "_open_client", return_value=_fake_open_client()),
    ):
        with pytest.raises(
            ai_analyzer.AIConnectionError,
            match="Connection failed",
        ):
            await ai_analyzer.extract_structured_tender("text")

def test_evidence_matches_scalar_compares_provisional_guarantee_as_money():
    from app.schemas.analysis import TenderEvidenceItem
    from app.services.ai_analyzer import _evidence_matches_scalar

    evidence = TenderEvidenceItem(
        field_name="provisional_guarantee",
        extracted_value="5 000 MAD",
        page_number=1,
        source_text="Caution provisoire : 5 000 MAD",
    )

    assert _evidence_matches_scalar(
        evidence, "provisional_guarantee", "5000 MAD"
    ) is True
    assert _evidence_matches_scalar(
        evidence, "provisional_guarantee", "5 000 EUR"
    ) is False
    assert _evidence_matches_scalar(
        evidence, "provisional_guarantee", "6 000 MAD"
    ) is False
