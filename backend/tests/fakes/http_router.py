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

"""Route every outbound ``httpx`` request to an in-process fake.

The app builds its HTTP clients inline (``async with httpx.AsyncClient() as
client``) rather than taking one as a dependency, so there is no client to
inject. :class:`FakeHttpRouter` instead gives every ``httpx.AsyncClient`` /
``httpx.Client`` constructed *without* an explicit transport an
``httpx.MockTransport`` that dispatches on the request host:

* a host registered with :meth:`mount` goes to that fake's handler;
* any other host is recorded on the :class:`ExternalCallGuard` and answered
  with ``httpx.ConnectError``, the same thing the code would see offline.

Clients that pass their own transport (the tests' ``ASGITransport`` clients)
are left alone.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.fakes.guard import ExternalCallGuard

Handler = Callable[[httpx.Request], httpx.Response]


def host_matches(pattern: str, host: str) -> bool:
    """``api.github.com`` matches itself; ``*.atlassian.net`` matches subdomains."""
    if pattern.startswith("*."):
        return host.endswith(pattern[1:])
    return host == pattern


class FakeHttpRouter:
    """One ``MockTransport`` for every fake external HTTP service."""

    def __init__(self, guard: ExternalCallGuard) -> None:
        self._guard = guard
        self._mounts: list[tuple[str, Handler]] = []
        self.requests: list[httpx.Request] = []

    def mount(self, host_pattern: str, handler: Handler) -> None:
        """Send requests for ``host_pattern`` to ``handler``.

        Later mounts win, so a test can override a fake for one host.
        """
        self._mounts.insert(0, (host_pattern, handler))

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Dispatch one request; unknown hosts are a guard violation."""
        self.requests.append(request)
        host = request.url.host
        for pattern, handler in self._mounts:
            if host_matches(pattern, host):
                return handler(request)
        self._guard.violations.append(f"HTTP {request.method} {request.url}")
        raise httpx.ConnectError(f"no fake mounted for host {host!r}", request=request)

    def transport(self) -> httpx.MockTransport:
        """A fresh transport bound to this router."""
        return httpx.MockTransport(self.handle)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default every new httpx client's transport to this router."""
        router = self
        real_async_init = httpx.AsyncClient.__init__
        real_sync_init = httpx.Client.__init__

        def async_init(client: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
            if kwargs.get("transport") is None and kwargs.get("app") is None:
                kwargs["transport"] = router.transport()
            real_async_init(client, *args, **kwargs)

        def sync_init(client: httpx.Client, *args: Any, **kwargs: Any) -> None:
            if kwargs.get("transport") is None and kwargs.get("app") is None:
                kwargs["transport"] = router.transport()
            real_sync_init(client, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", async_init)
        monkeypatch.setattr(httpx.Client, "__init__", sync_init)
