
import pytest

from app.core.request_size_limit import RequestBodySizeLimitMiddleware


MAX_BODY_SIZE = 11 * 1024 * 1024
TARGET_PATH = "/api/v1/tenders/analyze-pdf"


async def invoke_middleware(
    middleware,
    scope,
    receive,
):
    messages = []

    async def send(message):
        messages.append(message)

    await middleware(scope, receive, send)

    return messages


def make_scope(path=TARGET_PATH, method="POST", headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
    }


@pytest.mark.asyncio
async def test_rejects_request_using_content_length():
    app_called = False

    async def app(scope, receive, send):
        nonlocal app_called
        app_called = True

    middleware = RequestBodySizeLimitMiddleware(
        app,
        max_body_size=MAX_BODY_SIZE,
        paths={TARGET_PATH},
    )

    async def receive():
        return {
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }

    scope = make_scope(
        headers=[
            (
                b"content-length",
                str(MAX_BODY_SIZE + 1).encode("ascii"),
            )
        ]
    )

    messages = await invoke_middleware(
        middleware,
        scope,
        receive,
    )

    assert app_called is False
    assert messages[0]["status"] == 413
    assert messages[0]["headers"][0] == (
        b"content-type",
        b"application/json",
    )
    assert messages[1]["type"] == "http.response.body"
    assert b"11 MiB" in messages[1]["body"]


@pytest.mark.asyncio
async def test_rejects_actual_body_exceeding_limit_without_content_length():
    app_called = False

    async def app(scope, receive, send):
        nonlocal app_called
        app_called = True

        while True:
            message = await receive()

            if not message.get("more_body", False):
                break

    middleware = RequestBodySizeLimitMiddleware(
        app,
        max_body_size=MAX_BODY_SIZE,
        paths={TARGET_PATH},
    )

    chunks = [
        {
            "type": "http.request",
            "body": b"a" * MAX_BODY_SIZE,
            "more_body": True,
        },
        {
            "type": "http.request",
            "body": b"b",
            "more_body": False,
        },
    ]

    async def receive():
        return chunks.pop(0)

    messages = await invoke_middleware(
        middleware,
        make_scope(),
        receive,
    )

    assert app_called is True
    assert messages[0]["status"] == 413
    assert messages[1]["type"] == "http.response.body"
    assert b"11 MiB" in messages[1]["body"]


@pytest.mark.asyncio
async def test_does_not_limit_other_paths():
    app_called = False

    async def app(scope, receive, send):
        nonlocal app_called
        app_called = True

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"OK",
                "more_body": False,
            }
        )

    middleware = RequestBodySizeLimitMiddleware(
        app,
        max_body_size=MAX_BODY_SIZE,
        paths={TARGET_PATH},
    )

    async def receive():
        return {
            "type": "http.request",
            "body": b"a" * (MAX_BODY_SIZE + 1),
            "more_body": False,
        }

    messages = await invoke_middleware(
        middleware,
        make_scope(path="/health"),
        receive,
    )

    assert app_called is True
    assert messages[0]["status"] == 200
    assert messages[1]["body"] == b"OK"
