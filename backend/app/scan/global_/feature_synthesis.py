# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Phase B2 — parallel feature synthesis via Claude Code.

Per-repo body wrapped in a global gather. The body itself runs three
steps in order:

1. **B2 queue self-heal.** On resume, prior attempts may have
   synthesised some clusters already. Diff the in-memory queue against
   ``synthesized_features.cluster_names_for_repo`` and trim. If
   nothing is left, skip the subprocess.
2. **Claude subprocess.** ``run_claude_code`` with the synthesis
   prompt; tool_use events flow through ``make_scan_progress_logger``
   so each ``write_feature_registry`` call lands in ``bodhi.log``.
3. **``verify_repo_links`` audit.** Belt-and-braces against orphan
   knowledge_items: auto-repair what can be linked, raise
   ``OrphanFeaturesError`` on anything unfixable so the per-repo
   checkpoint lands FAILED with ``error_code='orphan_feature'``.

The gather is **bounded** via ``app.scan.session.gather_repos`` — async
SQLAlchemy on asyncpg has a default pool size around 10, and 20
concurrent ``_synthesize_repo`` tasks (each opening 2-3 connections)
will trip ``InvalidRequestError`` even with per-task sessions. Capping
at 4 keeps headroom. This is the single most important invariant
preventing the "18 of 20 repos returned 0 features" failure mode.
"""

from __future__ import annotations

import time
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_item import KnowledgeItemRepository
from app.scan.session import gather_repos, with_session
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    MCPServerConfig,
    run_claude_code,
)
from app.services.scan_checkpoints import OrphanFeaturesError

logger = structlog.get_logger(__name__)


async def phase_b2_synthesis(
    db: AsyncSession,
    org_id: uuid.UUID,
    pending_synthesis: list[dict],
    is_workspace: bool,
    scan_cfg: dict,
    scan_id: str,
    ki_repo: KnowledgeItemRepository,
) -> int:
    """Phase B2: Parallel feature synthesis via Claude Code.

    Args:
        db: Async database session (used only for the initial pre-flight
            commit + final ``ki_repo.count_active``; the per-repo body
            uses its own ``with_session`` blocks).
        org_id: Organization UUID.
        pending_synthesis: List of synthesis task dicts. Each must
            include ``repo_id`` — ``build_pending_synthesis`` skips
            untracked repos.
        is_workspace: Whether this is a multi-repo workspace scan.
        scan_cfg: Scan configuration dict from org config.
        scan_id: Scan identifier for progress tracking.
        ki_repo: Knowledge item repository instance (counts after gather).

    Returns:
        Total features synthesized (from DB count).
    """
    if not pending_synthesis:
        return 0

    from app.services.scan_pipeline import build_synthesis_prompt
    from app.services.scan_progress import get_scan_progress, update_scan_progress

    await update_scan_progress(scan_id, status="synthesizing_features", progress_pct=65)

    # Commit so MCP callbacks don't block on our locks
    await db.commit()

    async def _synthesize_repo(task: dict) -> dict:
        """Run synthesis for one repo. Returns result dict."""
        from app.config import settings as app_settings
        from app.mcp.auth import create_internal_mcp_token
        from app.mcp.server import (
            clear_synthesis_queue,
            get_queue_remaining,
        )
        from app.mcp.synthesis_queue import set_synthesis_queue
        from app.repositories.knowledge_item_scan import KnowledgeItemScanRepository
        from app.repositories.synthesized_feature import SynthesizedFeatureRepository
        from app.services.scan_phases import make_scan_progress_logger

        rname = task["repo_name"]
        repo_id_for_task: uuid.UUID = task["repo_id"]
        t0 = time.monotonic()

        # B2 queue self-heal — see module docstring step 1.
        if not task.get("direct_scan"):
            current_queue = get_queue_remaining(str(org_id), queue_key=task["queue_key"])
            async with with_session(org_id) as task_db:
                synth_repo = SynthesizedFeatureRepository(task_db, org_id=org_id)
                done_clusters = await synth_repo.cluster_names_for_repo(repo_id_for_task)
            pending_queue = [c for c in current_queue if c.get("name") not in done_clusters]
            if len(pending_queue) != len(current_queue):
                logger.info(
                    "b2_queue_self_heal",
                    repo=rname,
                    prior_size=len(current_queue),
                    done_skipped=len(current_queue) - len(pending_queue),
                    pending_size=len(pending_queue),
                )
                clear_synthesis_queue(str(org_id), queue_key=task["queue_key"])
                task["queue_key"] = set_synthesis_queue(
                    str(org_id), pending_queue, repo_name=rname
                )
            if not pending_queue:
                logger.info(
                    "b2_synthesis_skipped_queue_empty",
                    repo=rname,
                    message="all clusters already synthesised",
                )
                elapsed = round(time.monotonic() - t0, 1)
                return {
                    "repo_name": rname,
                    "result": None,
                    "remaining": [],
                    "elapsed_s": elapsed,
                    "skipped_no_pending": True,
                }

        if task.get("direct_scan"):
            from app.services.scan_pipeline import build_direct_scan_prompt

            prompt = build_direct_scan_prompt(rname, task["overview"], task["file_tree"])
        else:
            prompt = build_synthesis_prompt(rname, task["overview"], is_workspace)

        token = create_internal_mcp_token(org_id)
        synth_config = ClaudeRunnerConfig(
            max_turns=scan_cfg.get("max_turns", 40),
            timeout_seconds=scan_cfg.get("timeout_seconds", 300),
            output_format="json",
            mcp=MCPServerConfig(
                backend_url=app_settings.mcp_backend_url,
                mcp_token=token,
            ),
        )
        result = await run_claude_code(
            prompt=prompt,
            working_dir=task["repo_path"],
            config=synth_config,
            progress_callback=make_scan_progress_logger(
                scan_id=scan_id,
                phase="feature_synthesis",
                repo_name=rname,
            ),
        )

        if task.get("direct_scan"):
            remaining: list = []
        else:
            remaining = get_queue_remaining(str(org_id), queue_key=task["queue_key"])
            clear_synthesis_queue(str(org_id), queue_key=task["queue_key"])

        # verify_repo_links audit — see module docstring step 3.
        if result and result.success:
            async with with_session(org_id) as task_db:
                ki_scan = KnowledgeItemScanRepository(task_db, org_id=org_id)
                orphans = await ki_scan.find_items_missing_repo_link(repo_id_for_task)
                if orphans:
                    repaired = await ki_scan.insert_missing_links(
                        orphans, repo_id=repo_id_for_task
                    )
                    unfixed = [o for o in orphans if o not in repaired]
                    if unfixed:
                        raise OrphanFeaturesError(
                            f"Repo {rname!r}: {len(unfixed)} feature(s) remain "
                            "without a knowledge_to_repo link after auto-repair. "
                            "Retry synthesis for this repo.",
                        )
                    logger.info(
                        "b2_repo_links_repaired",
                        repo=rname,
                        repaired_count=len(repaired),
                    )

        elapsed = round(time.monotonic() - t0, 1)
        return {
            "repo_name": rname,
            "result": result,
            "remaining": remaining,
            "elapsed_s": elapsed,
        }

    # Bounded gather — see module docstring for the asyncpg-pool rationale.
    synthesis_outcomes = await gather_repos(
        [_synthesize_repo(t) for t in pending_synthesis],
    )

    for outcome in synthesis_outcomes:
        if isinstance(outcome, OrphanFeaturesError):
            logger.error("feature_synthesis_orphan", error=str(outcome))
            current = await get_scan_progress(scan_id)
            accumulated = (current.features_skipped if current else 0) + 1
            await update_scan_progress(
                scan_id,
                features_skipped=accumulated,
                synthesis_warning=str(outcome),
            )
            continue
        if isinstance(outcome, BaseException):
            logger.exception("feature_synthesis_exception", error=str(outcome))
            continue
        rname = outcome["repo_name"]
        result = outcome["result"]
        remaining = outcome["remaining"]
        if outcome.get("skipped_no_pending"):
            continue
        if result.success:
            logger.info(
                "feature_synthesis_complete",
                repo=rname,
                cost=result.cost_usd,
                elapsed_s=outcome["elapsed_s"],
                remaining_clusters=len(remaining),
            )
        else:
            skipped = len(remaining) if remaining else 1
            logger.warning(
                "feature_synthesis_failed",
                repo=rname,
                error=result.error,
                elapsed_s=outcome["elapsed_s"],
                remaining_clusters=skipped,
            )
            is_timeout = "Timed out" in (result.error or "")
            warning_msg = (
                (
                    f"{rname}: {skipped} feature(s) skipped "
                    "— timed out. Increase timeout in Settings."
                )
                if is_timeout
                else (f"{rname}: synthesis failed — features may be incomplete.")
            )
            current = await get_scan_progress(scan_id)
            accumulated = (current.features_skipped if current else 0) + skipped
            await update_scan_progress(
                scan_id,
                features_skipped=accumulated,
                synthesis_warning=warning_msg,
            )

    return await ki_repo.count_active(category="feature_registry")
