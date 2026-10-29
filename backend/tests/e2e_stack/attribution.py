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


"""Which browser test a request (and anything it starts) is serving.

The Playwright fixtures send ``x-e2e-test`` on every request. The middleware
puts it in a context variable for that request; asyncio copies the context
into tasks the request creates, so background work it starts is tagged too.
Work started elsewhere (job workers, scheduler loops) has no test, and the
suite checks those entries once, at the end of the run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from typing import Any, TypeVar

from starlette.types import ASGIApp, Receive, Scope, Send

T = TypeVar("T")
TEST_HEADER = b"x-e2e-test"
_MAX_ID = 300

current_test: ContextVar[str | None] = ContextVar("e2e_current_test", default=None)


class TestIdMiddleware:
    """Sets :data:`current_test` from the request header for the request's lifetime."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        test_id = None
        if scope["type"] in ("http", "websocket"):
            for name, value in scope.get("headers", []):
                if name == TEST_HEADER:
                    test_id = value.decode("latin-1")[:_MAX_ID]
        if test_id is None:
            await self.app(scope, receive, send)
            return
        token = current_test.set(test_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_test.reset(token)


class ContextThreadPool(ThreadPoolExecutor):
    """A default executor that runs each job in its submitter's context.

    ``loop.run_in_executor`` (async DNS lookups, for one) doesn't copy
    context variables into the thread, so a refusal there would lose its
    test. Installed as the loop's default executor by ``serve``.
    """

    def submit(self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T]:
        return super().submit(copy_context().run, fn, *args, **kwargs)


@dataclass
class TaggedLog:
    """Entries recorded with the test that was running when they happened."""

    entries: list[tuple[str | None, str]] = field(default_factory=list)

    def add(self, what: str) -> None:
        self.entries.append((current_test.get(), what))

    def for_test(self, test_id: str | None) -> list[str]:
        return [what for test, what in self.entries if test == test_id]

    def everything(self) -> list[str]:
        return [f"[{test or 'no test'}] {what}" for test, what in self.entries]


class TaggingList(list[T]):
    """A list that also tags each item appended to it in a :class:`TaggedLog`."""

    def __init__(self, log: TaggedLog, describe: Callable[[T], str]) -> None:
        super().__init__()
        self._log = log
        self._describe = describe

    def append(self, item: T) -> None:
        super().append(item)
        self._log.add(self._describe(item))

    def extend(self, items: Iterable[T]) -> None:
        for item in items:
            self.append(item)
