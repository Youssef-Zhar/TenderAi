"""
tests/test_ai_analyzer.py
--------------------------
Unit tests for app/services/ai_analyzer.py.

All tests mock httpx.AsyncClient — no network calls are made.
Run with: .venv/Scripts/pytest.exe tests/ -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.services.ai_analyzer import (
    split_document,
    _call_openrouter,
    _extract_chunk,
    MAX_CHUNK_CHARS,
    CHUNK_OUTPUT_TOKENS,
    FINAL_OUTPUT_TOKENS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(content: str, finish_reason: str) -> MagicMock:
    """Build a mock httpx.Response that returns a Chat Completions body."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {"content": content},
                "finish_reason": finish_reason,
            }
        ]
    }
    return mock_resp


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


# ── _call_openrouter (returns tuple) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_openrouter_returns_content_and_finish_reason_on_stop():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _mock_response("Analysis complete.", "stop")

    content, finish_reason = await _call_openrouter(
        client=mock_client,
        system_prompt="sys",
        user_message="user",
        max_tokens=200,
    )

    assert content == "Analysis complete."
    assert finish_reason == "stop"


@pytest.mark.asyncio
async def test_call_openrouter_returns_length_finish_reason_without_raising():
    """
    _call_openrouter must return the tuple even when finish_reason='length'.
    It is now the caller's responsibility to decide how to handle truncation.
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _mock_response("Rapport partiel…", "length")

    content, finish_reason = await _call_openrouter(
        client=mock_client,
        system_prompt="sys",
        user_message="user",
        max_tokens=100,
    )

    assert finish_reason == "length"
    assert content == "Rapport partiel…"


@pytest.mark.asyncio
async def test_call_openrouter_raises_on_empty_content():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _mock_response("", "stop")

    with pytest.raises(RuntimeError, match="empty"):
        await _call_openrouter(mock_client, "sys", "user", 100)


@pytest.mark.asyncio
async def test_call_openrouter_raises_on_malformed_response():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.return_value = {"error": "model not found"}
    mock_client.post.return_value = bad_resp

    with pytest.raises(RuntimeError):
        await _call_openrouter(mock_client, "sys", "user", 100)


# ── _extract_chunk — recovery strategy ───────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_chunk_returns_content_when_primary_completes():
    """Primary extraction succeeds → return it directly, no retry."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _mock_response("DEADLINE: 2025-12-31", "stop")

    result = await _extract_chunk(mock_client, "budget: 100 000 MAD", 1, 3)

    assert "DEADLINE: 2025-12-31" in result
    assert mock_client.post.call_count == 1   # no retry


@pytest.mark.asyncio
async def test_extract_chunk_retries_on_primary_truncation_and_succeeds():
    """
    Primary truncates → fallback is attempted → fallback completes.
    The result must include the fallback content and a [FALLBACK] marker.
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [
        _mock_response("Rapport partiel coupé ici…", "length"),   # primary
        _mock_response("• Deadline: 31/12/2025 [p.2]", "stop"),  # fallback OK
    ]

    result = await _extract_chunk(mock_client, "some chunk text", 2, 5)

    assert "[FALLBACK" in result
    assert "Deadline: 31/12/2025" in result
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_extract_chunk_accepts_partial_when_both_truncated():
    """
    Primary truncates AND fallback also truncates → accept partial with
    a [PARTIAL] marker rather than raising an exception.
    The overall analysis can still proceed with incomplete evidence.
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [
        _mock_response("Coupé 1…", "length"),  # primary truncated
        _mock_response("Coupé 2…", "length"),  # fallback also truncated
    ]

    result = await _extract_chunk(mock_client, "a very dense chunk", 3, 5)

    assert "[PARTIAL" in result
    assert mock_client.post.call_count == 2  # both attempts made


@pytest.mark.asyncio
async def test_extract_chunk_propagates_network_error():
    """Network errors must propagate — they are not a truncation event."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with pytest.raises(httpx.ConnectError):
        await _extract_chunk(mock_client, "chunk", 1, 1)


# ── Token budget sanity guards ────────────────────────────────────────────────

def test_final_output_tokens_is_large_enough():
    assert FINAL_OUTPUT_TOKENS >= 3_000

def test_chunk_output_tokens_is_large_enough():
    assert CHUNK_OUTPUT_TOKENS >= 1_000
