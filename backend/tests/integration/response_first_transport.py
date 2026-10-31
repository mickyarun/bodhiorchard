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

"""An httpx transport that returns a response as soon as a server would.

httpx's ``ASGITransport`` waits for the whole ASGI call to return before it
hands back the response, so anything an app does after sending it (a yield
dependency's exit code, background tasks) has already finished by the time
the test reads. A real client gets the response the moment its last byte is
sent; this transport does the same and lets the app finish in the background.
"""

from __future__ import annotations

import asyncio
from collections.abc import MutableMapping
from typing import Any

import httpx
from starlette.types import ASGIApp

Message = MutableMapping[str, Any]


class ResponseFirstTransport(httpx.AsyncBaseTransport):
    """Run each request on ``app`` and return once the response body is complete."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._running: set[asyncio.Task[None]] = set()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        start: Message = {}
        parts: list[bytes] = []
        sent = asyncio.Event()
        body_delivered = False

        async def receive() -> Message:
            nonlocal body_delivered
            if body_delivered:
                await sent.wait()
                return {"type": "http.disconnect"}
            body_delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                start.update(message)
            elif message["type"] == "http.response.body":
                parts.append(message.get("body", b""))
                if not message.get("more_body", False):
                    sent.set()

        async def run_app() -> None:
            await self._app(_scope(request), receive, send)

        app_call: asyncio.Task[None] = asyncio.create_task(run_app())
        self._running.add(app_call)
        response_sent = asyncio.create_task(sent.wait())
        await asyncio.wait({app_call, response_sent}, return_when=asyncio.FIRST_COMPLETED)
        if not sent.is_set():
            # The app returned or failed without responding: report it here, once.
            response_sent.cancel()
            self._running.discard(app_call)
            await app_call
            raise RuntimeError("the app returned without sending a response")
        return httpx.Response(
            start["status"], headers=start.get("headers", []), content=b"".join(parts)
        )

    async def aclose(self) -> None:
        """Let the app finish whatever it does after responding."""
        await asyncio.gather(*self._running)


def _scope(request: httpx.Request) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": request.method,
        "headers": [(k.lower(), v) for k, v in request.headers.raw],
        "scheme": request.url.scheme,
        "path": request.url.path,
        "raw_path": request.url.raw_path.split(b"?")[0],
        "query_string": request.url.query,
        "server": (request.url.host, request.url.port),
        "client": ("127.0.0.1", 123),
        "root_path": "",
    }
