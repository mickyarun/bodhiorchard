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

"""PR-author resolution must follow a member merge.

Regression coverage for the split-identity defect: PR ingestion resolved
the author through ``users.github_username`` alone, which only ever
matches the provisioned stub. The real member — invited by work email —
had ``github_username`` unset, so every PR bound to the stub and the
surviving member showed zero throughput.

The fix routes through :func:`resolve_canonical_user` with the GitHub
noreply address, which the merge leaves behind as an alias on the target.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_webhook_handler import _resolve_github_user


@pytest.mark.asyncio
async def test_passes_both_login_and_noreply_email() -> None:
    """Both arms are supplied so the email/alias fallback can fire."""
    org_id = uuid.uuid4()
    canonical = AsyncMock(return_value=uuid.uuid4())

    with patch("app.services.github_webhook_handler.resolve_canonical_user", new=canonical):
        await _resolve_github_user(MagicMock(), org_id, "octo-dev")

    _, kwargs = canonical.call_args
    assert kwargs["github_login"] == "octo-dev"
    assert kwargs["email"] == "octo-dev@users.noreply.github.com"


@pytest.mark.asyncio
async def test_resolves_merged_member_via_alias() -> None:
    """Login misses after a merge cleared the stub; the alias still lands."""
    target_id = uuid.uuid4()
    canonical = AsyncMock(return_value=target_id)

    with patch("app.services.github_webhook_handler.resolve_canonical_user", new=canonical):
        resolved = await _resolve_github_user(MagicMock(), uuid.uuid4(), "mixed-case-dev")

    assert resolved == target_id


@pytest.mark.asyncio
@pytest.mark.parametrize("login", ["", "   ", None])
async def test_blank_login_short_circuits(login: str | None) -> None:
    """No login means no lookup — never build a bare '@users.noreply' address."""
    canonical = AsyncMock()

    with patch("app.services.github_webhook_handler.resolve_canonical_user", new=canonical):
        resolved = await _resolve_github_user(MagicMock(), uuid.uuid4(), login)  # type: ignore[arg-type]

    assert resolved is None
    canonical.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_is_trimmed() -> None:
    """Surrounding whitespace must not leak into the alias address."""
    canonical = AsyncMock(return_value=None)

    with patch("app.services.github_webhook_handler.resolve_canonical_user", new=canonical):
        await _resolve_github_user(MagicMock(), uuid.uuid4(), "  spaced-dev  ")

    _, kwargs = canonical.call_args
    assert kwargs["github_login"] == "spaced-dev"
    assert kwargs["email"] == "spaced-dev@users.noreply.github.com"


@pytest.mark.asyncio
async def test_unresolved_author_returns_none() -> None:
    """External collaborators stay NULL rather than mis-crediting someone."""
    canonical = AsyncMock(return_value=None)

    with patch("app.services.github_webhook_handler.resolve_canonical_user", new=canonical):
        resolved = await _resolve_github_user(MagicMock(), uuid.uuid4(), "outsider")

    assert resolved is None
