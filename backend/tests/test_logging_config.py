import json
import logging

from app.core.logging_config import JsonFormatter


def test_json_formatter_includes_request_context_without_extra_data():
    record = logging.LogRecord(
        name="tenderai.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="HTTP request completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "trace-123"
    record.method = "GET"
    record.path = "/ready"
    record.status_code = 200
    record.duration_ms = 4.25

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "tenderai.request"
    assert payload["message"] == "HTTP request completed"
    assert payload["request_id"] == "trace-123"
    assert payload["method"] == "GET"
    assert payload["path"] == "/ready"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 4.25
    assert "args" not in payload
