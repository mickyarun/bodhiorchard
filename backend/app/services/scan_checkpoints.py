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

"""Checkpoint-wrapped phase execution for the resumable scan pipeline.

This module is the only piece of code that writes ``scan_phase_checkpoints``
rows during a live scan. It encapsulates three concerns:

1. **Skip-if-done and cross-scan SHA reuse** — consult prior checkpoints
   before running a phase. Phases listed in ``SHA_REUSABLE_PHASES`` copy
   their payload from an earlier DONE row when the repo HEAD SHA hasn't
   changed, so full re-scans on unchanged repos cost nothing.
2. **Error classification** — map exceptions raised by a phase body to
   one of the stable ``ScanErrorCode`` values so the UI can render
   actionable hints (§D.10 of the plan).
3. **WebSocket dedup** — the scan pipeline publishes status snapshots on
   every phase transition; ``publish_scan_status`` drops no-op publishes
   whose digest matches the previous snapshot for the same scan.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, ClassVar

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.scan_phase import (
    SHA_REUSABLE_PHASES,
    CheckpointStatus,
    ScanErrorCode,
    ScanPhase,
)
from app.repositories.scan_phase_checkpoint import ScanPhaseCheckpointRepository

logger = structlog.get_logger(__name__)

# Terminal checkpoint statuses that short-circuit ``run_checkpointed_phase``
# when they already exist for the current ``(scan_id, repo_id, phase)``.
_SKIP_STATUSES = (CheckpointStatus.DONE, CheckpointStatus.SKIPPED)


# ───────────────────────── Typed scan exceptions ─────────────────────────
#
# Phase bodies raise these when they detect a specific failure mode so the
# orchestrator can map them to a stable ``ScanErrorCode`` without parsing
# exception messages. Any other exception is classified as EXCEPTION.


class ScanPhaseError(Exception):
    """Base class for scan-phase failures with a classified error code."""

    code: ClassVar[ScanErrorCode] = ScanErrorCode.EXCEPTION


class MaxTurnsError(ScanPhaseError):
    """The Claude subprocess stopped because ``--max-turns`` was reached."""

    code = ScanErrorCode.MAX_TURNS


class ClaudeSubprocessError(ScanPhaseError):
    """The Claude subprocess exited non-zero without a structured error."""

    code = ScanErrorCode.CLAUDE_SUBPROCESS


class MCPError(ScanPhaseError):
    """An MCP tool call returned an error payload."""

    code = ScanErrorCode.MCP_ERROR


class PhaseTimeoutError(ScanPhaseError):
    """The phase exceeded its wall-clock budget."""

    code = ScanErrorCode.TIMEOUT


class OrphanFeaturesError(ScanPhaseError):
    """Post-synthesis audit found features lacking a ``knowledge_to_repo`` link."""

    code = ScanErrorCode.ORPHAN_FEATURE


class UnmatchedAuthorsError(ScanPhaseError):
    """``SKILL_EXTRACTION`` left git authors without a matching User row.

    Surfaced as a typed failure (rather than a quiet DONE checkpoint with
    ``unmatched_count > 0``) so the scan halts on the offending repo and
    the per-repo retry endpoint becomes the recovery path: the user adds
    a ``UserEmailAlias`` or creates the missing member, then retries
    ``skill_extraction`` for that ``repo_id``.

    The first few unmatched emails are inlined in the message so the
    timeline hint is actionable without opening the payload column.
    """

    code = ScanErrorCode.UNMATCHED_AUTHORS

    _PREVIEW_LIMIT: ClassVar[int] = 5

    def __init__(self, unmatched: list[str], repo_name: str) -> None:
        self.unmatched = unmatched
        self.repo_name = repo_name
        preview = ", ".join(unmatched[: self._PREVIEW_LIMIT])
        overflow = len(unmatched) - self._PREVIEW_LIMIT
        more = f" (+{overflow} more)" if overflow > 0 else ""
        super().__init__(
            f"Unmatched authors in {repo_name}: {preview}{more}. "
            "Add email aliases or create members, then retry this phase."
        )


# ───────────────────────── Error classification ─────────────────────────


def classify_scan_error(exc: BaseException) -> tuple[ScanErrorCode, str]:
    """Map an exception to a ``(code, message)`` pair for checkpoint write.

    Specific ``ScanPhaseError`` subclasses carry their own code. Other
    exceptions are sniffed against known shapes (timeout, cancellation)
    and otherwise default to ``EXCEPTION`` with the raw ``str(exc)``.

    The message is truncated to 2000 chars so a ballooning traceback
    cannot blow up the ``error_message`` column.
    """
    if isinstance(exc, ScanPhaseError):
        code = exc.code
    elif isinstance(exc, TimeoutError | asyncio.TimeoutError):
        code = ScanErrorCode.TIMEOUT
    else:
        code = ScanErrorCode.EXCEPTION

    message = str(exc).strip() or exc.__class__.__name__
    if len(message) > 2000:
        message = message[:1997] + "..."
    return code, message


# ───────────────────────── Dedicated checkpoint session ─────────────────


@asynccontextmanager
async def _checkpoint_tx(org_id: uuid.UUID) -> AsyncIterator[ScanPhaseCheckpointRepository]:
    """Yield a checkpoint repo on its own short-lived session.

    Every ``scan_phase_checkpoints`` write rides this helper instead of
    the pipeline's phase session. The phase session may roll back when
    a phase body raises — and prior to this helper, that rollback also
    discarded the FAILED transition that ``run_checkpointed_phase``
    wrote, leaving the row stuck in RUNNING. With a dedicated session,
    the WAL of phase transitions stays durable independent of whatever
    happens to the phase's own work.

    Commits on clean exit. Rolls back and re-raises on exception so the
    caller still sees the failure.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield ScanPhaseCheckpointRepository(session, org_id=org_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ───────────────────────── Checkpoint-wrapped execution ─────────────────


@dataclass(frozen=True)
class PhaseRunOutcome:
    """Result of a ``run_checkpointed_phase`` call.

    - ``payload`` — what the phase body produced, or what was retrieved
      from a reused checkpoint.
    - ``was_skipped`` — the phase did not run because it already had a
      DONE / SKIPPED checkpoint in the current scan.
    - ``was_reused`` — the phase body was skipped because a prior scan's
      DONE checkpoint with matching SHA was copied forward.
    """

    payload: dict[str, Any]
    was_skipped: bool
    was_reused: bool


PhaseFn = Callable[[], Awaitable[dict[str, Any] | None]]
TransitionHook = Callable[[], Awaitable[None]]


async def run_checkpointed_phase(
    *,
    db: AsyncSession,
    scan_id: uuid.UUID,
    org_id: uuid.UUID,
    phase: ScanPhase,
    phase_fn: PhaseFn,
    repo_id: uuid.UUID | None = None,
    sha: str | None = None,
    parent_scan_id: uuid.UUID | None = None,
    skip_if_done: bool = True,
    reuse_across_scans: bool = True,
    on_transition: TransitionHook | None = None,
) -> PhaseRunOutcome:
    """Execute ``phase_fn`` wrapped by checkpoint lookup + write.

    Every checkpoint read and write rides ``_checkpoint_tx`` — a fresh
    short-lived session that commits independently of the caller's
    ``db``. This is what makes the WAL of phase transitions durable
    when a phase body raises and the pipeline's outer session rolls
    back: the FAILED row landed in its own committed transaction, so
    rollback can't undo it.

    Args:
        db: Caller's pipeline session. Kept in the signature for
            backwards compatibility but **not used for checkpoint I/O**
            — the phase body still uses it for its own writes (features,
            skills, etc.).
        scan_id: Current scan UUID.
        org_id: Organisation UUID for tenant scoping.
        phase: Which phase is being run.
        phase_fn: Zero-arg coroutine factory returning the phase's
            payload dict (or ``None``, treated as ``{}``).
        repo_id: Repo UUID for PER_REPO phases; ``None`` for GLOBAL.
        sha: Repo HEAD SHA at the time of this run. Required for
            cross-scan SHA reuse; ignored for phases not in
            ``SHA_REUSABLE_PHASES``.
        parent_scan_id: Set on resume so the checkpoint tracks lineage.
        skip_if_done: When True (the normal case), a DONE / SKIPPED
            checkpoint for this (scan, repo, phase) short-circuits the
            call. Turn off for retries that must always re-run.
        reuse_across_scans: When True, DONE checkpoints from *earlier*
            scans with matching SHA are copied forward instead of
            running ``phase_fn``. Ignored for non-SHA-reusable phases.
        on_transition: Optional callback invoked after every checkpoint
            write so the caller can publish a WebSocket update.

    Returns:
        A ``PhaseRunOutcome`` describing what happened.
    """
    del db  # signature kept for back-compat; checkpoints use _checkpoint_tx

    # (1) Short-circuit: already terminal for this scan.
    if skip_if_done:
        async with _checkpoint_tx(org_id) as repo:
            existing = await repo.get_latest(scan_id, repo_id, phase)
            existing_status = existing.status if existing is not None else None
            existing_payload = dict(existing.payload or {}) if existing is not None else {}
        if existing_status in _SKIP_STATUSES:
            return PhaseRunOutcome(
                payload=existing_payload,
                was_skipped=True,
                was_reused=False,
            )

    # (2) Cross-scan SHA reuse.
    if (
        reuse_across_scans
        and sha is not None
        and repo_id is not None
        and phase in SHA_REUSABLE_PHASES
    ):
        async with _checkpoint_tx(org_id) as repo:
            prior = await repo.find_sha_reusable(repo_id, phase, sha)
            if prior is not None:
                prior_payload = dict(prior.payload or {})
                source_scan_id = prior.scan_id
                await repo.insert_reused(
                    scan_id=scan_id,
                    parent_scan_id=parent_scan_id,
                    repo_id=repo_id,
                    phase=phase,
                    payload=prior_payload,
                    sha_at_run=sha,
                )
            else:
                prior_payload = None
                source_scan_id = None
        if prior_payload is not None:
            logger.info(
                "checkpoint_reused_from_sha",
                scan_id=str(scan_id),
                repo_id=str(repo_id),
                phase=phase.value,
                source_scan_id=str(source_scan_id),
            )
            if on_transition is not None:
                await on_transition()
            return PhaseRunOutcome(
                payload=prior_payload,
                was_skipped=False,
                was_reused=True,
            )

    # (3) Insert the RUNNING row in its own committed transaction so a
    # crash mid-phase still leaves a durable trail for reconcile.
    async with _checkpoint_tx(org_id) as repo:
        checkpoint_id = await repo.start(
            scan_id=scan_id,
            repo_id=repo_id,
            phase=phase,
            parent_scan_id=parent_scan_id,
            sha_at_run=sha,
        )
    if on_transition is not None:
        await on_transition()

    try:
        result = await phase_fn()
    except asyncio.CancelledError:
        # Graceful shutdown / task cancellation — leave the checkpoint
        # in RUNNING state so a resume picks it up rather than seeing
        # a misleading permanent FAILED. Re-raise to honour the
        # cancellation contract.
        raise
    except Exception as exc:
        code, message = classify_scan_error(exc)
        async with _checkpoint_tx(org_id) as repo:
            await repo.finalize_by_id(
                checkpoint_id,
                status=CheckpointStatus.FAILED,
                error_code=code.value,
                error_message=message,
            )
        logger.warning(
            "scan_phase_failed",
            scan_id=str(scan_id),
            repo_id=str(repo_id) if repo_id else None,
            phase=phase.value,
            error_code=code.value,
            error=message,
        )
        if on_transition is not None:
            await on_transition()
        raise

    payload = dict(result or {})
    async with _checkpoint_tx(org_id) as repo:
        await repo.finalize_by_id(
            checkpoint_id,
            status=CheckpointStatus.DONE,
            payload=payload,
            sha_at_run=sha,
        )
    if on_transition is not None:
        await on_transition()
    return PhaseRunOutcome(payload=payload, was_skipped=False, was_reused=False)


# ───────────────────────── Publish dedup ─────────────────────────

# Per-process cache of the last-published digest per scan_id. Lives only
# for the duration of a scan and is cleared by ``clear_scan_publish_dedup``
# on terminal status. This is intentionally not in Redis: multi-worker
# deployments of the backend would each dedup independently, which is
# acceptable — the consumer (frontend) tolerates duplicate WS events.
_last_publish_digest: dict[str, str] = {}


def _snapshot_digest(snapshot: dict[str, Any]) -> str:
    """Stable SHA-256 digest of a JSON-serialisable snapshot."""
    serialised = json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


async def publish_scan_status(
    scan_id: uuid.UUID,
    snapshot: dict[str, Any],
    *,
    publisher: Callable[[str, dict[str, Any]], None] | None = None,
) -> bool:
    """Publish ``snapshot`` to the event bus, skipping no-op republishes.

    Args:
        scan_id: Scan identifier, used as the dedup key and the
            ``scan:{scan_id}`` topic.
        snapshot: The full ``ScanStatus`` payload (or any JSON-serialisable
            dict). Its digest is compared against the last publish for
            this scan; identical payloads are silently dropped.
        publisher: Optional override for dependency injection / testing.
            Defaults to ``app.services.event_bus.publish``.

    Returns:
        True if a publish fired, False if dedup suppressed it.
    """
    key = str(scan_id)
    digest = _snapshot_digest(snapshot)
    if _last_publish_digest.get(key) == digest:
        return False
    _last_publish_digest[key] = digest

    sink = publisher
    if sink is None:
        from app.services.event_bus import publish as _default_publisher

        sink = _default_publisher
    sink(f"scan:{scan_id}", snapshot)
    return True


def clear_scan_publish_dedup(scan_id: uuid.UUID) -> None:
    """Drop the dedup cache entry for a scan when it reaches a terminal state.

    Callers should invoke this from the scan pipeline's completion /
    failure branches so a subsequent scan with the same (unlikely but
    possible) scan_id starts with a fresh digest.
    """
    _last_publish_digest.pop(str(scan_id), None)
