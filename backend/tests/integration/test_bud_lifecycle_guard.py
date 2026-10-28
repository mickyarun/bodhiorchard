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

"""The BUD lifecycle tests' app-database guard really is fail-closed."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration


async def test_app_database_connections_are_refused_and_recorded(
    app_database_blocked: list[str],
) -> None:
    """Opening a session on the app engine fails and is recorded for teardown."""
    with pytest.raises(RuntimeError, match="app database"):
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))

    assert app_database_blocked == ["connect"]
    # Clear the record so this deliberate attempt does not fail the teardown check.
    app_database_blocked.clear()
