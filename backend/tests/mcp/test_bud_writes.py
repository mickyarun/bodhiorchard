# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Guard-rejection invariants for the BYO-AI write surface.

These pin the four behaviours that make the MCP write path safe from
prompt-injection scenarios:

1. ``update_bud`` rejects calls where the token's user isn't the BUD's
   assignee, even when the BUD belongs to the token's org.
2. ``update_bud`` rejects calls against terminal-status BUDs so a
   closed/discarded BUD can't be edited back to life via MCP.
3. ``update_bud`` rejects calls when the current phase isn't in the
   ``_MCP_EDITABLE_PHASES`` allowlist (TESTING, CODE_REVIEW, DEVELOPMENT,
   UAT, PROD) — eliminates an entire class of "write the wrong field
   via MCP" injection and keeps PR/evidence-gated phases UI-only.
4. ``create_bud`` requires a per-user token; org-level tokens are
   rejected so we never produce a BUD with no assignee-of-record.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.auth import MCPAuthResult
from app.mcp.handlers_bud_writes import (
    handle_create_bud,
    handle_get_bud_by_id,
    handle_update_bud,
)
from app.models.bud import BUDStatus
from app.repositories.bud import BUDRepository


def _auth(user_id: uuid.UUID | None = None) -> MCPAuthResult:
    org = MagicMock(id=uuid.uuid4())
    if user_id is None:
        return MCPAuthResult(org=org)
    user = MagicMock(id=user_id)
    return MCPAuthResult(org=org, user=user, token_id=uuid.uuid4())


def _fake_bud(
    *,
    status: BUDStatus = BUDStatus.BUD,
    assignee_id: uuid.UUID | None = None,
) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        bud_number=42,
        title="Demo",
        status=status,
        assignee_id=assignee_id,
        requirements_md="body",
        tech_spec_md=None,
        test_plan_md=None,
        code_review_comments=None,
        auto_generate_phases=None,
    )


@pytest.mark.asyncio
async def test_update_bud_rejects_non_assignee(monkeypatch: Any) -> None:
    user_id = uuid.uuid4()
    other = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(assignee_id=other)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(), auth, {"bud_id": str(bud.id), "content": "new body"}
    )
    assert result["success"] is False
    assert result["code"] == "not_assignee"


@pytest.mark.asyncio
async def test_update_bud_rejects_terminal_status(monkeypatch: Any) -> None:
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.CLOSED, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(), auth, {"bud_id": str(bud.id), "content": "anything"}
    )
    assert result["success"] is False
    assert result["code"] == "terminal_status"


@pytest.mark.parametrize(
    "blocked_phase",
    [
        BUDStatus.DEVELOPMENT,
        BUDStatus.TESTING,
        BUDStatus.CODE_REVIEW,
        BUDStatus.UAT,
        BUDStatus.PROD,
    ],
)
@pytest.mark.asyncio
async def test_update_bud_rejects_non_creative_phases(
    monkeypatch: Any, blocked_phase: BUDStatus
) -> None:
    """Only BUD / DESIGN / TECH_ARCH are MCP-writable — every other live
    phase rejects with ``phase_not_writable``."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=blocked_phase, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(), auth, {"bud_id": str(bud.id), "content": "anything"}
    )
    assert result["success"] is False
    assert result["code"] == "phase_not_writable"
    assert result["current_status"] == blocked_phase.value


@pytest.mark.asyncio
async def test_update_bud_writes_only_owning_field(monkeypatch: Any) -> None:
    """When the BUD is in TECH_ARCH, ``content`` lands in tech_spec_md —
    requirements_md must stay untouched even if the caller asks for it."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    original_requirements = "original body"
    bud = _fake_bud(status=BUDStatus.TECH_ARCH, assignee_id=user_id)
    bud.requirements_md = original_requirements

    snapshots: list[dict[str, Any]] = []

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    async def _snapshot(db: Any, **kw: Any) -> Any:
        snapshots.append(kw)
        return MagicMock()

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)
    monkeypatch.setattr("app.mcp.handlers_bud_writes.bud_version_repo.insert_snapshot", _snapshot)

    db = MagicMock(flush=AsyncMock())

    result = await handle_update_bud(
        db,
        auth,
        {"bud_id": str(bud.id), "content": "NEW SPEC", "expected_phase": "tech_arch"},
    )
    assert result["success"] is True
    assert result["field"] == "tech_spec_md"
    assert bud.tech_spec_md == "NEW SPEC"
    assert bud.requirements_md == original_requirements
    assert len(snapshots) == 1
    assert snapshots[0]["source"].value == "mcp"


@pytest.mark.asyncio
async def test_update_bud_rejects_phase_mismatch(monkeypatch: Any) -> None:
    """When the caller declares ``expected_phase`` and the BUD has
    moved since the pre-flight read, the server must reject loudly
    rather than silently writing content composed for the wrong
    phase. This is the safety net against design HTML landing in
    requirements_md when the BUD's status changes mid-conversation."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.BUD, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(),
        auth,
        {
            "bud_id": str(bud.id),
            "content": "<div>some wireframe HTML</div>",
            "expected_phase": "design",  # caller thinks DESIGN, BUD is BUD
        },
    )
    assert result["success"] is False
    assert result["code"] == "phase_mismatch"
    assert result["current_status"] == "bud"
    assert result["expected_phase"] == "design"


@pytest.mark.asyncio
async def test_update_bud_rejects_missing_expected_phase(monkeypatch: Any) -> None:
    """Without ``expected_phase`` the safety check can't fire — the
    LLM must declare its intent. Older clients with stale schema
    caches surface here so the user is prompted to restart."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.BUD, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(),
        auth,
        {"bud_id": str(bud.id), "content": "body"},  # no expected_phase
    )
    assert result["success"] is False
    assert result["code"] == "missing_expected_phase"


@pytest.mark.asyncio
async def test_update_bud_design_phase_requires_repo_id(monkeypatch: Any) -> None:
    """Design writes must target a specific repo's wireframe row so the
    UI tab labels match what the design agent would produce. Omitting
    repo_id is rejected before any side effect."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.DESIGN, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_update_bud(
        MagicMock(),
        auth,
        {
            "bud_id": str(bud.id),
            "content": "<div>x</div>",
            "expected_phase": "design",
        },
    )
    assert result["success"] is False
    assert result["code"] == "missing_repo_id"


@pytest.mark.asyncio
async def test_update_bud_design_phase_rejects_cross_org_repo(monkeypatch: Any) -> None:
    """The validation defends multi-tenancy — passing a repo_id that
    isn't a tracked repo in the caller's org returns repo_not_found."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.DESIGN, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    async def _repo_lookup(self: Any, repo_id: uuid.UUID) -> Any:
        return None  # repo absent / belongs to another org

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)
    monkeypatch.setattr(
        "app.repositories.tracked_repository.TrackedRepoRepository.get_by_id",
        _repo_lookup,
    )

    result = await handle_update_bud(
        MagicMock(),
        auth,
        {
            "bud_id": str(bud.id),
            "content": "<div>x</div>",
            "expected_phase": "design",
            "repo_id": str(uuid.uuid4()),
        },
    )
    assert result["success"] is False
    assert result["code"] == "repo_not_found"


@pytest.mark.asyncio
async def test_update_bud_design_phase_routes_to_repo_upsert(monkeypatch: Any) -> None:
    """Happy path: DESIGN-phase writes upsert ``(bud_id, repo_id)`` —
    not a BUD-level slot. Snapshot records both the prior HTML and the
    repo id so revert can target the same row."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.DESIGN, assignee_id=user_id)
    target_repo = uuid.uuid4()
    prior_design = MagicMock(repo_id=target_repo, design_html="<old>OLD</old>")
    new_design = MagicMock(id=uuid.uuid4())

    snapshots: list[dict[str, Any]] = []
    upsert_calls: list[dict[str, Any]] = []

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    async def _list_for_bud(self: Any, bud_id: uuid.UUID) -> list[Any]:
        return [prior_design]

    async def _upsert(self: Any, bud_id: uuid.UUID, repo_id: Any, **kw: Any) -> MagicMock:
        upsert_calls.append({"bud_id": bud_id, "repo_id": repo_id, **kw})
        return new_design

    async def _commit_snapshot(db: Any, **kw: Any) -> Any:
        snapshots.append(kw)
        return MagicMock()

    async def _repo_lookup(self: Any, repo_id: uuid.UUID) -> Any:
        return MagicMock(id=target_repo)

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)
    monkeypatch.setattr("app.repositories.bud.BUDDesignRepository.list_for_bud", _list_for_bud)
    monkeypatch.setattr("app.repositories.bud.BUDDesignRepository.upsert", _upsert)
    monkeypatch.setattr(
        "app.mcp.handlers_bud_writes.bud_version_repo.commit_snapshot", _commit_snapshot
    )
    monkeypatch.setattr(
        "app.repositories.tracked_repository.TrackedRepoRepository.get_by_id",
        _repo_lookup,
    )

    db = MagicMock(flush=AsyncMock())
    result = await handle_update_bud(
        db,
        auth,
        {
            "bud_id": str(bud.id),
            "content": "<div>NEW WIREFRAME</div>",
            "expected_phase": "design",
            "repo_id": str(target_repo),
        },
    )

    assert result["success"] is True
    assert result["field"] == "design_html"
    assert result["design_id"] == str(new_design.id)
    assert result["repo_id"] == str(target_repo)
    assert len(upsert_calls) == 1
    # The design upsert MUST target the chosen repo, not the BUD-
    # level (None) slot.
    assert upsert_calls[0]["repo_id"] == target_repo
    # Snapshot remembers the repo so revert can write back to the
    # same row.
    assert snapshots[0]["snapshot"]["__design_repo_id"] == str(target_repo)
    assert "NEW WIREFRAME" in upsert_calls[0]["design_html"]
    # The pre-edit design HTML was captured in the snapshot under the
    # sentinel key, so revert can roll BOTH the BUD columns and the
    # design row back to v1.
    assert len(snapshots) == 1
    assert snapshots[0]["snapshot"]["__design_html"] == "<old>OLD</old>"


@pytest.mark.asyncio
async def test_update_bud_wires_linked_feature_ids(monkeypatch: Any) -> None:
    """``update_bud`` must call ``link_features`` with the caller's
    explicit UUID array — that's the whole point of the new
    ``linked_feature_ids`` param vs the old JSON-fence parsing."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.BUD, assignee_id=user_id)
    bud.requirements_md = "old text"
    feature_a = uuid.uuid4()
    feature_b = uuid.uuid4()

    link_calls: list[dict[str, Any]] = []

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    async def _snapshot(db: Any, **kw: Any) -> Any:
        return MagicMock()

    async def _link_features(
        self: Any, bud_id: Any, feature_ids: list[Any], **kw: Any
    ) -> list[Any]:
        link_calls.append({"bud_id": bud_id, "feature_ids": feature_ids, **kw})
        return feature_ids  # all accepted

    async def _embed(text: str) -> list[float]:
        return [0.0] * 384

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)
    monkeypatch.setattr("app.mcp.handlers_bud_writes.bud_version_repo.insert_snapshot", _snapshot)
    monkeypatch.setattr(
        "app.repositories.bud_feature_link.BUDFeatureLinkRepository.link_features",
        _link_features,
    )
    monkeypatch.setattr("app.mcp.handlers_bud_writes.embedding_service.embed", _embed)

    db = MagicMock(flush=AsyncMock())
    result = await handle_update_bud(
        db,
        auth,
        {
            "bud_id": str(bud.id),
            "content": "new text",
            "expected_phase": "bud",
            "linked_feature_ids": [str(feature_a), str(feature_b)],
        },
    )

    assert result["success"] is True
    assert result["linked_features"]["linked_count"] == 2
    assert len(link_calls) == 1
    assert set(link_calls[0]["feature_ids"]) == {feature_a, feature_b}
    # Source must be MANUAL so the audit + activity log separate MCP
    # writes from agent-driven links.
    assert link_calls[0]["source"].value == "manual"


@pytest.mark.asyncio
async def test_update_bud_logs_dropped_invalid_uuids(monkeypatch: Any) -> None:
    """Garbage entries in linked_feature_ids must be dropped (not crash
    the write) and surfaced in the response so the LLM can fix its
    output on the next call."""
    user_id = uuid.uuid4()
    auth = _auth(user_id)
    bud = _fake_bud(status=BUDStatus.BUD, assignee_id=user_id)

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    async def _snapshot(db: Any, **kw: Any) -> Any:
        return MagicMock()

    async def _link_features(
        self: Any, bud_id: Any, feature_ids: list[Any], **kw: Any
    ) -> list[Any]:
        return []

    async def _embed(text: str) -> list[float]:
        return [0.0] * 384

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)
    monkeypatch.setattr("app.mcp.handlers_bud_writes.bud_version_repo.insert_snapshot", _snapshot)
    monkeypatch.setattr(
        "app.repositories.bud_feature_link.BUDFeatureLinkRepository.link_features",
        _link_features,
    )
    monkeypatch.setattr("app.mcp.handlers_bud_writes.embedding_service.embed", _embed)

    db = MagicMock(flush=AsyncMock())
    result = await handle_update_bud(
        db,
        auth,
        {
            "bud_id": str(bud.id),
            "content": "text",
            "expected_phase": "bud",
            "linked_feature_ids": ["not-a-uuid", "also bad"],
        },
    )

    assert result["success"] is True
    assert result["linked_features"]["dropped"] == ["not-a-uuid", "also bad"]
    assert result["linked_features"]["linked_count"] == 0


@pytest.mark.asyncio
async def test_create_bud_requires_user_token() -> None:
    auth = _auth(user_id=None)
    result = await handle_create_bud(MagicMock(), auth, {"title": "T", "requirements_md": "B"})
    assert result["success"] is False
    assert result["code"] == "user_token_required"


@pytest.mark.asyncio
async def test_get_bud_by_id_org_scoped(monkeypatch: Any) -> None:
    """get_bud_by_id is read-only and works for any org member."""
    auth = _auth(uuid.uuid4())
    bud = _fake_bud()

    async def _get(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return bud

    monkeypatch.setattr(BUDRepository, "get_by_id", _get)

    result = await handle_get_bud_by_id(MagicMock(), auth, {"bud_id": str(bud.id)})
    assert result["bud_number"] == 42
    assert result["status"] == "bud"
    # caller_user_id always echoes the token's user so the LLM can
    # cross-check against assignee_id without a separate whoami call.
    assert result["caller_user_id"] == str(auth.user.id)


@pytest.mark.asyncio
async def test_get_bud_by_id_is_assignee_flag(monkeypatch: Any) -> None:
    """``is_assignee`` derived flag matches a real assignee match and
    reflects mismatches so the LLM can stop before composing."""
    user_id = uuid.uuid4()
    other = uuid.uuid4()
    auth = _auth(user_id)
    matched = _fake_bud(assignee_id=user_id)
    mismatched = _fake_bud(assignee_id=other)

    async def _get_matched(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return matched

    async def _get_mismatched(self: Any, bud_id: uuid.UUID) -> MagicMock:
        return mismatched

    monkeypatch.setattr(BUDRepository, "get_by_id", _get_matched)
    result = await handle_get_bud_by_id(MagicMock(), auth, {"bud_id": str(matched.id)})
    assert result["is_assignee"] is True

    monkeypatch.setattr(BUDRepository, "get_by_id", _get_mismatched)
    result = await handle_get_bud_by_id(MagicMock(), auth, {"bud_id": str(mismatched.id)})
    assert result["is_assignee"] is False
    assert result["assignee_id"] == str(other)
    assert result["caller_user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_get_bud_by_id_rejects_bad_uuid() -> None:
    auth = _auth(uuid.uuid4())
    result = await handle_get_bud_by_id(MagicMock(), auth, {"bud_id": "not-a-uuid"})
    assert result["success"] is False
    assert result["code"] == "bad_bud_id"
