# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""``get_bud_context`` response shape.

The Slack feature-Q&A skill (``slack-feature-qa.md``) declares
``prod_p70_date``, ``current_phase_deadline`` and ``assignee_id`` in its
``answer`` JSON schema and instructs the agent to quote those fields
verbatim. Earlier the handler only returned ``id / bud_number / title /
status / requirements_md`` — so the agent saw nothing for the dates and
confabulated "no date is currently set" replies even when the BUD had a
P70 stamped against it (image-2 / BUD-020 in the bug report).

This pins both halves of the contract:

1. Date columns surface as ``YYYY-MM-DD`` strings (matching the skill
   examples and the user-facing Slack reply formatter).
2. ``None`` values round-trip as JSON ``null`` so the agent's
   fallback chain (P70 → phase deadline → "not set") still works.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.mcp.handlers_bud import handle_get_bud_context
from app.models.bud import BUDStatus
from app.repositories.bud import BUDRepository


def _fake_bud(
    *,
    prod_p70_date: datetime | None = None,
    current_phase_deadline: datetime | None = None,
    assignee_id: uuid.UUID | None = None,
) -> MagicMock:
    """Return a BUD-shaped mock with the columns the handler reads."""
    return MagicMock(
        id=uuid.uuid4(),
        bud_number=20,
        title="Remote Payments",
        status=BUDStatus.DEVELOPMENT,
        requirements_md="A long body that the handler truncates to 5000 chars.",
        prod_p70_date=prod_p70_date,
        current_phase_deadline=current_phase_deadline,
        assignee_id=assignee_id,
    )


@pytest.mark.asyncio
async def test_returns_date_and_assignee_fields(monkeypatch: Any) -> None:
    """When the columns are populated they surface as date-only strings."""
    assignee_id = uuid.uuid4()
    bud = _fake_bud(
        prod_p70_date=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
        current_phase_deadline=datetime(2026, 5, 30, 17, 0, tzinfo=UTC),
        assignee_id=assignee_id,
    )

    async def _list_buds(self: Any, **kw: Any) -> list[Any]:
        return [bud]

    monkeypatch.setattr(BUDRepository, "list_buds", _list_buds)

    result = await handle_get_bud_context(
        MagicMock(), MagicMock(id=uuid.uuid4()), {"query": "remote payments"}
    )

    assert len(result["buds"]) == 1
    row = result["buds"][0]
    assert row["prod_p70_date"] == "2026-06-12"
    assert row["current_phase_deadline"] == "2026-05-30"
    assert row["assignee_id"] == str(assignee_id)


@pytest.mark.asyncio
async def test_null_columns_round_trip_as_none(monkeypatch: Any) -> None:
    """Unset columns surface as ``None`` — the skill's fallback chain
    (P70 → phase deadline → "not set") relies on JSON-null, not on a
    missing key."""
    bud = _fake_bud()

    async def _list_buds(self: Any, **kw: Any) -> list[Any]:
        return [bud]

    monkeypatch.setattr(BUDRepository, "list_buds", _list_buds)

    result = await handle_get_bud_context(MagicMock(), MagicMock(id=uuid.uuid4()), {})

    row = result["buds"][0]
    assert row["prod_p70_date"] is None
    assert row["current_phase_deadline"] is None
    assert row["assignee_id"] is None
    # The pre-existing contract must not regress.
    for key in ("id", "bud_number", "title", "status", "requirements_md"):
        assert key in row
