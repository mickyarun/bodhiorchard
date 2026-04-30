# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Background fanout for the v2 scan pipeline.

Holds the strong-reference table for in-flight scan tasks, schedules
the per-repo workflow loop bounded by ``gather_repos``, and runs the
global phases once every per-repo workflow has completed. Public
surface (``start_v2_scan`` / ``resume_v2_scan`` / ``cancel_v2_scan``)
lives in ``runner.py``; this module is the implementation detail those
entry points dispatch into.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.models.scan import Scan, ScanAggregateStatus
from app.repositories.scan_run import ScanRunRepository
from app.scan.session import gather_repos, with_session
from app.schemas.scan import RunConfig
from app.services.scan.global_phases import run_global_phases
from app.services.scan.observers import DBTimelineObserver
from app.services.scan.runner_config import load_scan_cfg, mint_mcp_credentials
from app.services.scan.setup import RepoDescriptor
from app.services.scan.soft_delete_hook import (
    rollback_soft_deleted,
    soft_delete_changed_repos,
)
from app.services.scan.workflow import start_run

logger = structlog.get_logger(__name__)

# Hold strong references so background tasks aren't GC'd mid-flight,
# keyed by ``scan_id`` so a cancel-scan request can find and cancel the
# in-flight task instead of just flipping the DB row.
_BACKGROUND_SCANS: dict[uuid.UUID, asyncio.Task[None]] = {}


def cancel_background_task(scan_id: uuid.UUID) -> bool:
    """Cancel the in-flight asyncio task for ``scan_id`` if any.

    Returns True iff a task was found and ``cancel()`` was issued. The
    cancelled task's ``CancelledError`` handlers in
    ``workflow._execute_run`` are responsible for stamping per-repo
    terminal state — this helper only triggers cancellation.
    """
    task = _BACKGROUND_SCANS.get(scan_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


async def await_background_task(scan_id: uuid.UUID, *, timeout: float) -> None:
    """Block until the in-flight task for ``scan_id`` finishes (or timeout).

    No-op when no task is registered (e.g. after a backend restart).
    Two outcomes are silent — a cancelled task (expected on every cancel
    handshake) and a stuck task hitting the timeout — both leave the
    task no longer producing writes, so the cascade is safe.

    Anything else (a programmer error during teardown, a bug inside
    ``asyncio.wait_for``) is logged at WARN with traceback so it
    doesn't disappear; the cascade still proceeds because the task is
    no longer producing writes regardless of what blew up.
    """
    task = _BACKGROUND_SCANS.get(scan_id)
    if task is None or task.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        # Expected on every cancel handshake.
        pass
    except Exception:
        logger.exception("scan_await_task_unexpected", scan_id=str(scan_id))


def spawn_background_scan(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    repo_descriptors: list[RepoDescriptor],
    config: RunConfig,
) -> None:
    """Schedule the per-repo fanout and hold a strong task reference."""
    task = asyncio.create_task(
        _execute_scan(
            org_id=org_id,
            scan_id=scan_id,
            repo_descriptors=repo_descriptors,
            config=config,
        )
    )
    _BACKGROUND_SCANS[scan_id] = task

    def _on_done(_completed: asyncio.Task[None]) -> None:
        _BACKGROUND_SCANS.pop(scan_id, None)

    task.add_done_callback(_on_done)


async def _execute_scan(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    repo_descriptors: list[RepoDescriptor],
    config: RunConfig,
) -> None:
    """Background body — fans the workflow out across repos."""
    if not repo_descriptors:
        await _mark_scan_terminal(
            org_id=org_id, scan_id=scan_id, status=ScanAggregateStatus.COMPLETED
        )
        return

    repo_paths = [d.repo_path for d in repo_descriptors]

    # Match the legacy pipeline's data-safety invariant: deactivate
    # changed-repo features before fanout so fresh synthesis writes
    # under the same titles, then keep the deactivated id list for
    # rollback on orchestration failure.
    deactivated_ids = await soft_delete_changed_repos(
        org_id=org_id,
        scan_id=scan_id,
        repo_paths=repo_paths,
        full_rescan=config.full_rescan,
    )

    # Mint MCP credentials once per scan so the synthesize stage can
    # spawn Claude Code with a backend-callable MCP token.
    mcp_credentials = mint_mcp_credentials(org_id=org_id)

    # Pull the org's Scan-tuning settings (Settings → Code → Scan tuning
    # in the UI) once at fanout setup. The synthesize stage reads
    # ``timeout_seconds`` / ``max_turns`` from its config dict and
    # ``feature_merge`` reads ``scan_cfg.merge_timeout_seconds``, so we
    # both flatten the keys into ``runtime_overrides`` AND nest them
    # under ``scan_cfg``.
    scan_cfg_overrides = await load_scan_cfg(org_id)

    async def _run_one(descriptor: RepoDescriptor) -> None:
        observer = DBTimelineObserver(org_id=org_id, scan_id=scan_id, repo_id=descriptor.repo_id)
        # Per-stage skip predicates own the "is this work already
        # current?" decision. The runner only threads ``v2_full_rescan``
        # so the bypassable predicates can flip themselves off when the
        # user requests a Reset / Full Rescan.
        runtime_overrides: dict[str, Any] = {
            "v2_org_id": str(org_id),
            "v2_scan_id": str(scan_id),
            "v2_repo_id": str(descriptor.repo_id),
            "v2_repo_paths": repo_paths,
            "v2_full_rescan": bool(config.full_rescan),
            "scan_cfg": scan_cfg_overrides,
            **scan_cfg_overrides,
            **mcp_credentials,
        }
        try:
            # ``await_completion=True`` is critical: the scan must not
            # advance to ``run_global_phases`` / mark the Scan terminal
            # until each repo's full stage walk — including the Claude
            # synthesis subprocess — has actually returned.
            await start_run(
                repo_path=descriptor.repo_path,
                repo_name=descriptor.repo_name,
                config=config,
                observer=observer,
                runtime_overrides=runtime_overrides,
                await_completion=True,
            )
        except asyncio.CancelledError:
            # Worker was cancelled (process shutdown / dev-server
            # reload mid-scan). ``except Exception`` would not catch
            # this — CancelledError is a BaseException — so the
            # ``scan_repo_runs`` row would otherwise be left ``RUNNING``
            # forever. Mirror the cancellation into the row before
            # re-raising so the framework still tears the task down.
            logger.warning(
                "scan_repo_cancelled",
                scan_id=str(scan_id),
                repo_id=str(descriptor.repo_id),
            )
            await observer.on_run_failed(error="Worker cancelled before completion")
            raise
        except Exception as exc:
            logger.exception(
                "scan_repo_failed",
                scan_id=str(scan_id),
                repo_id=str(descriptor.repo_id),
            )
            await observer.on_run_failed(error=f"{type(exc).__name__}: {exc}"[:500])

    try:
        await gather_repos([_run_one(d) for d in repo_descriptors])
    except Exception:
        logger.exception("scan_orchestration_failed", scan_id=str(scan_id))
        await rollback_soft_deleted(
            org_id=org_id, scan_id=scan_id, deactivated_ids=deactivated_ids
        )
        await _mark_scan_terminal(
            org_id=org_id, scan_id=scan_id, status=ScanAggregateStatus.FAILED
        )
        return

    # Global phases run once across the whole scan, after every per-repo
    # workflow has finished. Use the *full* repo set for the scan, not
    # just the descriptors we were spawned with — on a Resume,
    # ``repo_descriptors`` only carries the re-executed repos but
    # feature_merge / skill_remap / persist_results need every repo so
    # ``tracked_repositories.head_sha`` lands for everyone.
    all_repo_paths = await _load_all_repo_paths_for_scan(org_id=org_id, scan_id=scan_id)
    if not all_repo_paths:
        all_repo_paths = repo_paths
    await run_global_phases(
        org_id=org_id,
        scan_id=scan_id,
        repo_paths=all_repo_paths,
        scan_mode="full" if config.full_rescan else "incremental",
    )
    await _mark_scan_terminal(org_id=org_id, scan_id=scan_id, status=ScanAggregateStatus.COMPLETED)


async def _load_all_repo_paths_for_scan(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
) -> list[str]:
    """Tracked-repo paths registered against this scan (incl. resumed runs)."""
    try:
        async with with_session(org_id) as db:
            return await ScanRunRepository(db, org_id=org_id).list_repo_paths_for_scan(
                scan_id=scan_id,
            )
    except Exception:
        logger.exception("scan_load_repo_paths_failed", scan_id=str(scan_id))
        return []


async def _mark_scan_terminal(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    status: ScanAggregateStatus,
) -> None:
    """Stamp the Scan row with the aggregate terminal state."""
    try:
        async with with_session(org_id) as db:
            scan = await db.get(Scan, scan_id)
            if scan is None:
                return
            scan.status = status.value
            scan.updated_at = datetime.now(UTC)
            await db.commit()
    except Exception:
        logger.exception("scan_terminal_write_failed")
