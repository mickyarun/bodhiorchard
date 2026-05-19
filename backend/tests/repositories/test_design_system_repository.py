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

"""Tests for the design system customisation layer.

Covers the merge contract between extracted ``content`` and user-authored
``custom_content``, plus the normalisation in ``set_custom_content`` that
keeps the ``is_customised`` flag truthful.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.design_system import DesignSystemRef
from app.repositories.design_system import DesignSystemRefRepository


def _row(*, content: str = "extracted body", custom: str | None = None) -> DesignSystemRef:
    """Construct an in-memory DesignSystemRef — no DB touch required."""
    return DesignSystemRef(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        is_default=False,
        content=content,
        custom_content=custom,
        source_hash="h",
        extracted_at=datetime.now(UTC),
    )


# ── merge_for_serve ───────────────────────────────────────────────


def test_merge_returns_content_when_no_customisations() -> None:
    """No custom_content → bare extracted content, no divider injected."""
    ds = _row(custom=None)
    assert DesignSystemRefRepository.merge_for_serve(ds) == "extracted body"


def test_merge_appends_user_customisations_with_divider() -> None:
    """custom_content → extracted body + divider + heading + note + custom body."""
    ds = _row(content="extracted body", custom="override body")
    merged = DesignSystemRefRepository.merge_for_serve(ds)
    assert merged.startswith("extracted body")
    assert "---" in merged
    assert "## User Customizations" in merged
    # Note line tells the designer agent the section is authoritative —
    # ``designer.md`` keys off the exact heading.
    assert "Authoritative override layer" in merged
    assert merged.endswith("override body")


def test_merge_ignores_whitespace_only_custom_content() -> None:
    """A whitespace-only ``custom_content`` must not inject the divider.

    Guards the latent-bug surface: future raw-SQL writes that leave
    ``"   "`` in the column shouldn't pollute the served markdown with
    an empty customisation section. ``is_customised`` checks ``strip()``
    so ``merge_for_serve`` does too.
    """
    ds = _row(custom="   \n\t  ")
    assert ds.is_customised is False
    assert DesignSystemRefRepository.merge_for_serve(ds) == "extracted body"


# ── is_customised property ────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("\n\t", False),
        ("anything", True),
        ("  body  ", True),
    ],
)
def test_is_customised_property(value: str | None, expected: bool) -> None:
    """One canonical rule shared by repo, API, and tests."""
    assert _row(custom=value).is_customised is expected


# ── set_custom_content normalisation ──────────────────────────────


@pytest.mark.asyncio
async def test_set_custom_content_strips_and_keeps_body() -> None:
    """Real input is trimmed once and persisted; whitespace boundaries gone."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    repo = DesignSystemRefRepository(db, org_id=uuid.uuid4())
    ds = _row(custom=None)

    await repo.set_custom_content(ds, "  override body  ")

    assert ds.custom_content == "override body"
    assert ds.is_customised is True


@pytest.mark.asyncio
async def test_set_custom_content_clears_on_empty_input() -> None:
    """Empty / whitespace-only input normalises to ``None`` so the
    ``is_customised`` flag stays truthful for downstream consumers."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    repo = DesignSystemRefRepository(db, org_id=uuid.uuid4())
    ds = _row(custom="prior body")

    await repo.set_custom_content(ds, "   \n   ")

    assert ds.custom_content is None
    assert ds.is_customised is False


@pytest.mark.asyncio
async def test_set_custom_content_clears_on_none() -> None:
    """``reset-customisations`` endpoint path: ``None`` → ``None``."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    repo = DesignSystemRefRepository(db, org_id=uuid.uuid4())
    ds = _row(custom="prior body")

    await repo.set_custom_content(ds, None)

    assert ds.custom_content is None
    assert ds.is_customised is False
