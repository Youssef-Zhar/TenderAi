
import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLarge(Exception):
    """Raised when the incoming request body exceeds the configured limit."""


class RequestBodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_body_size: int,
        paths: set[str],
    ) -> None:
        self.app = app
        self.max_body_size = max_body_size
        self.paths = paths

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] not in self.paths
        ):
            await self.app(scope, receive, send)
            return

        content_length = self._get_content_length(scope)

        if content_length is not None and content_length > self.max_body_size:
            await self._send_413(send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received

            message = await receive()

            if message["type"] == "http.request":
                received += len(message.get("body", b""))

                if received > self.max_body_size:
                    raise RequestBodyTooLarge

            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLarge:
            if not response_started:
                await self._send_413(send)

    def _get_content_length(self, scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None

        return None

    async def _send_413(self, send: Send) -> None:
        body = json.dumps(
            {"detail": "Request body must not exceed 11 MiB."}
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )

        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )
