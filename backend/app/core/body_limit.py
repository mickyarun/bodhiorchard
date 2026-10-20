# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Refuse request bodies over a size limit before they are buffered.

Upload routes check each file's own limit, but only after Starlette has
read the whole multipart body into a temporary file. Behind a proxy the
proxy caps that (``client_max_body_size`` in
``frontend/nginx.conf.template``); Full Docker also publishes the
backend's port directly, where nothing did. This caps every request at
the same size the proxy allows, so the backend never spools more than
that to disk.

Two checks: a declared ``Content-Length`` over the limit is refused
before anything is read, and the bytes actually received are counted so
a chunked body (no length) can't get past either.
"""

import json
from typing import Any

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.settings import MAX_CONFIGURABLE_ATTACHMENT_MB

# 1 MB above the largest attachment an org can allow, like the proxy:
# multipart framing fits, and an at-the-limit upload still gets the
# route's own clear message. Keep in step with nginx's client_max_body_size.
MAX_REQUEST_BODY_MB = MAX_CONFIGURABLE_ATTACHMENT_MB + 1
MAX_REQUEST_BODY_BYTES = MAX_REQUEST_BODY_MB * 1024 * 1024


def too_large(max_bytes: int) -> str:
    """The 413 message for a limit of ``max_bytes``."""
    size = max_bytes / (1024 * 1024)
    limit = f"{size:g} MB" if size >= 1 else f"{max_bytes} bytes"
    return f"The request is larger than the {limit} limit."


class BodyTooLargeError(HTTPException):
    """Raised while reading a body that has grown past the limit."""

    def __init__(self, max_bytes: int) -> None:
        """A 413 with the limit in the message."""
        super().__init__(status_code=413, detail=too_large(max_bytes))


class BodySizeLimitMiddleware:
    """ASGI middleware enforcing :data:`MAX_REQUEST_BODY_BYTES` (or ``max_bytes``)."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        """Wrap ``app``."""
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Refuse an oversized body, declared or streamed."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if _declared_length(scope) > self.max_bytes:
            await _refuse(send, self.max_bytes)
            return
        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI re-raises HTTPException from body parsing, so
                    # routes answer 413 themselves; anything else lands below.
                    raise BodyTooLargeError(self.max_bytes)
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BodyTooLargeError:
            if started:
                raise
            await _refuse(send, self.max_bytes)


def _declared_length(scope: Scope) -> int:
    """The request's Content-Length, or 0 when absent or unreadable."""
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


async def _refuse(send: Send, max_bytes: int) -> None:
    """Answer 413 with the same JSON shape as every other API error."""
    body = json.dumps({"detail": too_large(max_bytes)}, separators=(",", ":")).encode()
    headers: list[Any] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        # The rest of the body isn't read; tell the client not to reuse it.
        (b"connection", b"close"),
    ]
    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": body})
