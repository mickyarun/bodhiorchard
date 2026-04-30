# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Apply structured merge ops produced by the cross-repo merge prompt.

Each op identifies a canonical feature (NEW from this scan via
``canonical_synth_id``, or EXISTING from a prior scan via
``canonical_knowledge_id``) and any features it absorbs (NEW via
``absorb_synth_ids`` and/or EXISTING via ``absorb_knowledge_ids``).

Validation rules enforced before any DB write:

1. **canonical_synth_id XOR canonical_knowledge_id** — exactly one of
   the two id types must be set per op.
2. **action ∈ {merge, link, create}**.
3. **No id appears as both canonical and absorb** (within a single op
   or across the batch).
4. **No duplicate canonical id** across ops (would create conflicting
   audit rows).
5. **Org/category ownership** — every KI id belongs to this org and
   ``category='feature_registry'``; every synth id is unsuperseded
   and owned by this org.

Execution is delegated to ``app.services.merge_writer.apply_merge_op``;
the handler stays focused on shape validation and transaction framing.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.synthesized_feature import SynthesizedFeatureRepository
from app.services.merge_writer import apply_merge_op

logger = structlog.get_logger(__name__)

_ALLOWED_ACTIONS = frozenset({"merge", "link", "create"})


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    """Parse ``value`` as a UUID, returning None on any failure."""
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _coerce_uuid_list(values: Any) -> list[uuid.UUID] | None:
    """Parse a list of UUIDs, returning None on any malformed entry."""
    if values is None:
        return []
    if not isinstance(values, list):
        return None
    out: list[uuid.UUID] = []
    for v in values:
        parsed = _coerce_uuid(v)
        if parsed is None:
            return None
        out.append(parsed)
    return out


class _OpValidationError(Exception):
    """Raised when a single op fails validation; carries the index + reason."""

    def __init__(self, index: int, reason: str) -> None:
        super().__init__(f"op[{index}]: {reason}")
        self.index = index
        self.reason = reason


def _validate_op_shape(idx: int, op: Any) -> dict[str, Any]:
    """Validate a single op's primitive shape; returns the parsed dict."""
    if not isinstance(op, dict):
        raise _OpValidationError(idx, "op must be an object")

    action = op.get("action")
    if action not in _ALLOWED_ACTIONS:
        raise _OpValidationError(idx, f"action must be one of {sorted(_ALLOWED_ACTIONS)}")

    canonical_synth_id = _coerce_uuid(op.get("canonical_synth_id"))
    canonical_knowledge_id = _coerce_uuid(op.get("canonical_knowledge_id"))
    if (canonical_synth_id is None) == (canonical_knowledge_id is None):
        raise _OpValidationError(
            idx,
            "exactly one of canonical_synth_id or canonical_knowledge_id must be set",
        )

    absorb_synth_ids = _coerce_uuid_list(op.get("absorb_synth_ids"))
    if absorb_synth_ids is None:
        raise _OpValidationError(idx, "absorb_synth_ids must be a list of UUID strings")

    absorb_knowledge_ids = _coerce_uuid_list(op.get("absorb_knowledge_ids"))
    if absorb_knowledge_ids is None:
        raise _OpValidationError(idx, "absorb_knowledge_ids must be a list of UUID strings")

    repo_ids = _coerce_uuid_list(op.get("repo_ids"))
    if repo_ids is None:
        raise _OpValidationError(idx, "repo_ids must be a list of UUID strings")

    if canonical_synth_id is not None and canonical_synth_id in absorb_synth_ids:
        raise _OpValidationError(idx, "canonical_synth_id cannot appear in absorb_synth_ids")
    if canonical_knowledge_id is not None and canonical_knowledge_id in absorb_knowledge_ids:
        raise _OpValidationError(
            idx, "canonical_knowledge_id cannot appear in absorb_knowledge_ids"
        )

    if action == "merge" and not absorb_synth_ids and not absorb_knowledge_ids:
        raise _OpValidationError(
            idx, "merge action requires at least one absorb id (synth or knowledge)"
        )

    return {
        "action": action,
        "canonical_synth_id": canonical_synth_id,
        "canonical_knowledge_id": canonical_knowledge_id,
        "absorb_synth_ids": absorb_synth_ids,
        "absorb_knowledge_ids": absorb_knowledge_ids,
        "repo_ids": repo_ids,
    }


def _validate_no_duplicate_canonicals(parsed_ops: list[dict[str, Any]]) -> str | None:
    """Reject batches where two ops claim the same canonical."""
    synth_canonicals = [op["canonical_synth_id"] for op in parsed_ops if op["canonical_synth_id"]]
    if len(set(synth_canonicals)) != len(synth_canonicals):
        return "duplicate canonical_synth_id across ops"
    ki_canonicals = [
        op["canonical_knowledge_id"] for op in parsed_ops if op["canonical_knowledge_id"]
    ]
    if len(set(ki_canonicals)) != len(ki_canonicals):
        return "duplicate canonical_knowledge_id across ops"
    return None


def _validate_canonical_absorb_overlap(parsed_ops: list[dict[str, Any]]) -> str | None:
    """Reject batches where a canonical id also appears as an absorb."""
    all_synth_canonicals = {
        op["canonical_synth_id"] for op in parsed_ops if op["canonical_synth_id"]
    }
    all_synth_absorbs = {sid for op in parsed_ops for sid in op["absorb_synth_ids"]}
    if all_synth_canonicals & all_synth_absorbs:
        offenders = sorted(str(s) for s in (all_synth_canonicals & all_synth_absorbs))
        return f"synth id(s) appear as both canonical and absorb: {offenders}"

    all_ki_canonicals = {
        op["canonical_knowledge_id"] for op in parsed_ops if op["canonical_knowledge_id"]
    }
    all_ki_absorbs = {kid for op in parsed_ops for kid in op["absorb_knowledge_ids"]}
    if all_ki_canonicals & all_ki_absorbs:
        offenders = sorted(str(k) for k in (all_ki_canonicals & all_ki_absorbs))
        return f"knowledge id(s) appear as both canonical and absorb: {offenders}"
    return None


async def _validate_ki_ownership(
    ki_repo: KnowledgeItemRepository,
    *,
    org_id: uuid.UUID,
    ki_ids: set[uuid.UUID],
) -> dict[uuid.UUID, Any]:
    """Confirm every referenced KI exists, is in this org, and is feature_registry."""
    if not ki_ids:
        return {}
    found = await ki_repo.get_by_ids(ki_ids)
    missing = ki_ids - set(found.keys())
    if missing:
        raise ValueError(f"unknown knowledge_item id(s): {sorted(str(i) for i in missing)}")
    for kid, ki in found.items():
        if ki.org_id != org_id:
            raise ValueError(f"knowledge_item {kid} belongs to a different organization")
        if ki.category != "feature_registry":
            raise ValueError(f"knowledge_item {kid} is not in category 'feature_registry'")
    return found


async def _validate_synth_ownership(
    synth_repo: SynthesizedFeatureRepository,
    synth_ids: set[uuid.UUID],
) -> None:
    """Confirm every referenced synth row exists in this org and is current."""
    for sid in synth_ids:
        row = await synth_repo.get_by_id(sid)
        if row is None:
            raise ValueError(f"unknown synthesized_feature id: {sid}")
        if row.superseded_at is not None:
            raise ValueError(f"synthesized_feature {sid} is superseded")


async def _validate_repo_ownership(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_ids: set[uuid.UUID],
) -> None:
    """Confirm every referenced tracked repo exists and is in this org."""
    for rid in repo_ids:
        tracked = await db.get(TrackedRepository, rid)
        if tracked is None or tracked.org_id != org_id:
            raise ValueError(f"unknown tracked_repository id: {rid}")


async def handle_apply_feature_merge_plan(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Apply an ordered batch of structured merge ops in one transaction.

    Validation runs up front; any failure raises out so the caller's
    session rolls back the whole batch. ``flush()`` is called per op so
    later ops see in-progress link transfers.
    """
    raw_ops = params.get("ops")
    if not isinstance(raw_ops, list) or not raw_ops:
        return {"success": False, "error": "`ops` must be a non-empty array"}

    parsed_ops: list[dict[str, Any]] = []
    try:
        for idx, raw in enumerate(raw_ops):
            parsed_ops.append(_validate_op_shape(idx, raw))
    except _OpValidationError as exc:
        logger.warning("apply_feature_merge_plan_invalid_op", reason=exc.reason)
        return {"success": False, "error": str(exc)}

    dup_msg = _validate_no_duplicate_canonicals(parsed_ops)
    if dup_msg:
        return {"success": False, "error": dup_msg}

    overlap_msg = _validate_canonical_absorb_overlap(parsed_ops)
    if overlap_msg:
        return {"success": False, "error": overlap_msg}

    all_ki_ids: set[uuid.UUID] = set()
    for op in parsed_ops:
        if op["canonical_knowledge_id"]:
            all_ki_ids.add(op["canonical_knowledge_id"])
        all_ki_ids.update(op["absorb_knowledge_ids"])

    all_synth_ids: set[uuid.UUID] = set()
    for op in parsed_ops:
        if op["canonical_synth_id"]:
            all_synth_ids.add(op["canonical_synth_id"])
        all_synth_ids.update(op["absorb_synth_ids"])

    all_repo_ids: set[uuid.UUID] = {r for op in parsed_ops for r in op["repo_ids"]}

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    try:
        ki_map = await _validate_ki_ownership(ki_repo, org_id=org.id, ki_ids=all_ki_ids)
        await _validate_synth_ownership(synth_repo, all_synth_ids)
        await _validate_repo_ownership(db, org.id, all_repo_ids)
    except ValueError as exc:
        logger.warning("apply_feature_merge_plan_validation_failed", reason=str(exc))
        return {"success": False, "error": str(exc)}

    summary = {"merged_features": 0, "repo_links_added": 0, "ops_applied": 0}

    for op in parsed_ops:
        op_summary = await apply_merge_op(db=db, org=org, op=op, ki_map=ki_map)
        summary["merged_features"] += op_summary["merged_features"]
        summary["repo_links_added"] += op_summary["repo_links_added"]
        summary["ops_applied"] += 1
        await ki_repo.flush()

    logger.info(
        "apply_feature_merge_plan",
        org_id=str(org.id),
        op_count=len(parsed_ops),
        **summary,
    )
    return {"success": True, **summary}
