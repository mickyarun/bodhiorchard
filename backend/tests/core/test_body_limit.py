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

"""Request bodies over the limit are refused before they're buffered."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from httpx import ASGITransport, AsyncClient

from app.core.body_limit import (
    MAX_REQUEST_BODY_MB,
    BodySizeLimitMiddleware,
    too_large,
)

LIMIT = 1000
REPO_ROOT = Path(__file__).resolve().parents[3]


def _app() -> tuple[FastAPI, list[str]]:
    app = FastAPI()
    reached: list[str] = []

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        reached.append("echo")
        return {"size": len(await request.body())}

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)) -> dict[str, int]:  # noqa: B008
        reached.append("upload")
        return {"size": len(await file.read())}

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=LIMIT)
    return app, reached


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_declared_length_over_the_limit_is_refused_unread() -> None:
    app, reached = _app()
    async with _client(app) as client:
        response = await client.post("/echo", content=b"x" * (LIMIT + 1))
    assert response.status_code == 413
    assert response.json() == {"detail": too_large(LIMIT)}
    assert reached == []


async def test_a_chunked_body_is_counted_as_it_arrives() -> None:
    app, _ = _app()

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(5):
            yield b"x" * 400

    async with _client(app) as client:
        response = await client.post("/echo", content=chunks())
    assert "content-length" not in response.request.headers
    assert response.status_code == 413 and response.json() == {"detail": too_large(LIMIT)}


async def test_an_upload_gets_413_not_a_parse_error() -> None:
    app, _ = _app()

    async def chunks() -> AsyncIterator[bytes]:
        boundary = b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
        yield boundary
        for _ in range(5):
            yield b"x" * 400
        yield b"\r\n--b--\r\n"

    async with _client(app) as client:
        response = await client.post(
            "/upload",
            content=chunks(),
            headers={"content-type": "multipart/form-data; boundary=b"},
        )
    assert response.status_code == 413


async def test_normal_requests_pass() -> None:
    app, reached = _app()
    async with _client(app) as client:
        echoed = await client.post("/echo", content=b"x" * LIMIT)
        uploaded = await client.post("/upload", files={"file": ("a.pdf", b"y" * 200)})
    assert (echoed.status_code, echoed.json()) == (200, {"size": LIMIT})
    assert (uploaded.status_code, uploaded.json()) == (200, {"size": 200})
    assert reached == ["echo", "upload"]


def test_the_limit_matches_the_proxy() -> None:
    nginx = (REPO_ROOT / "frontend" / "nginx.conf.template").read_text()
    match = re.search(r"client_max_body_size\s+(\d+)M;", nginx)
    assert match is not None
    assert int(match.group(1)) == MAX_REQUEST_BODY_MB


def test_the_message_names_the_limit() -> None:
    assert too_large(26 * 1024 * 1024) == "The request is larger than the 26 MB limit."
    assert too_large(LIMIT) == "The request is larger than the 1000 bytes limit."
