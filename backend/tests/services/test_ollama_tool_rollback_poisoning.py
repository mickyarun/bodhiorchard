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

"""One failing tool call must not poison the ones after it.

A handler crash rolls the session back, and ``rollback()`` expires every ORM
instance in it — including the org every handler reads. The next tool touching
``org.id`` would then lazy-load through sync attribute access and raise
MissingGreenlet, so a single bad call cascaded into every later call failing on
the org rather than on its own merits. The model saw a wall of "backend error"
and abandoned an otherwise healthy run — observed as a designer that refused to
draw anything. The reload after rollback is what keeps the run recoverable.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai_runner import ollama_tools

_MOD = "app.services.ai_runner.ollama_tools"


def _auth() -> MagicMock:
    auth = MagicMock()
    auth.org = MagicMock()
    return auth


@pytest.mark.asyncio
async def test_failing_handler_rolls_back_and_reloads_the_org() -> None:
    """The org must be re-loaded, or the next tool dies on it, not on itself."""
    db = MagicMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    auth = _auth()

    with patch.dict(
        ollama_tools.TOOL_HANDLERS,
        {"get_features": AsyncMock(side_effect=RuntimeError("boom"))},
        clear=False,
    ):
        out = await ollama_tools.dispatch_tool(db, auth, "get_features", {})

    assert "boom" in json.loads(out)["error"]
    db.rollback.assert_awaited_once()
    # The org is reloaded so the *next* call has a usable instance.
    db.refresh.assert_awaited_once_with(auth.org)


@pytest.mark.asyncio
async def test_reload_failure_does_not_escape_and_kill_the_run() -> None:
    """We're already reporting one failure — a second must not become a crash
    that escapes run() and breaks its always-return-a-result contract."""
    db = MagicMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock(side_effect=RuntimeError("session gone"))
    auth = _auth()

    with patch.dict(
        ollama_tools.TOOL_HANDLERS,
        {"get_features": AsyncMock(side_effect=RuntimeError("boom"))},
        clear=False,
    ):
        out = await ollama_tools.dispatch_tool(db, auth, "get_features", {})

    assert "boom" in json.loads(out)["error"]


@pytest.mark.asyncio
async def test_successful_call_neither_rolls_back_nor_reloads() -> None:
    """Regression guard: the happy path must not pay for the failure path."""
    db = MagicMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    auth = _auth()

    with patch.dict(
        ollama_tools.TOOL_HANDLERS,
        {"get_features": AsyncMock(return_value={"features": []})},
        clear=False,
    ):
        out = await ollama_tools.dispatch_tool(db, auth, "get_features", {})

    assert json.loads(out) == {"features": []}
    db.rollback.assert_not_awaited()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_tool_needs_no_rollback() -> None:
    """The model inventing a tool never touched the session."""
    db = MagicMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()

    out = await ollama_tools.dispatch_tool(db, _auth(), "no_such_tool", {})

    assert "No such tool" in json.loads(out)["error"]
    db.rollback.assert_not_awaited()
