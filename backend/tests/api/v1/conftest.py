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

"""Shared fixtures for handler-with-fakes tests under ``tests/api/v1``.

The handler tests in this directory invoke FastAPI route functions
directly with mocked sessions and repositories (no live ASGI server —
see top-level ``tests/conftest.py`` for the historical reason). Every
such test needs the same two stand-ins, so they live here.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def fake_user() -> SimpleNamespace:
    """Minimal authenticated-user stand-in (id + org_id + name)."""
    return SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), name="Tester")


@pytest.fixture
def fake_db() -> MagicMock:
    """AsyncSession stand-in with awaitable ``flush`` / ``refresh``."""
    db = MagicMock(name="AsyncSession")
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db
