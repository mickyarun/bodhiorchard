# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage B3 — Cross-repo feature merge (global, runs once per scan).

Wraps ``app.services.scan.phase_impls.feature_merge.phase_b3_merge``. Lists every
synthesised feature for an LLM and lets it call the ``merge_features``
MCP tool to consolidate duplicates across repos.

Called from :mod:`scan_runner._run_global_phases` after every per-repo
workflow has finished. Failures are best-effort — a failed merge
leaves per-repo features intact.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._v2_context import resolve_v2_context, skipped_v2_output

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Cross-repo feature merge. Pass ``communities`` through unchanged."""
    v2 = resolve_v2_context(config)
    if v2 is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_v2_output())

    repo_paths_raw = config.get("v2_repo_paths") or [ctx.repo_path]
    repo_paths = list(repo_paths_raw) if isinstance(repo_paths_raw, list) else [ctx.repo_path]
    scan_cfg = dict(config.get("scan_cfg", {}))
    pre_merge_count = await _count_pre_merge_features(v2.org_id, v2.scan_id)

    from app.repositories.knowledge_item import KnowledgeItemRepository
    from app.services.scan.phase_impls.feature_merge import phase_b3_merge

    try:
        async with with_session(v2.org_id) as db:
            ki_repo = KnowledgeItemRepository(db, org_id=v2.org_id)
            merge_outcome = await phase_b3_merge(
                db=db,
                org_id=v2.org_id,
                repo_paths=repo_paths,
                scan_cfg=scan_cfg,
                scan_id=str(v2.scan_id),
                ki_repo=ki_repo,
            )
            # phase_b3_merge commits internally; no second commit here.
    except Exception as exc:
        logger.exception(
            "scan_feature_merge_failed",
            scan_id=str(v2.scan_id),
            repo_count=len(repo_paths),
        )
        return StageOutput(
            communities=communities,
            dropped=[],
            extras={
                "merged": False,
                "error": str(exc)[:300],
                "input_count": pre_merge_count,
                "kept_count": pre_merge_count,
                "dropped_count": 0,
                "io_label": "features → canonical features",
            },
        )

    canonical_count, merged_count = await _count_post_merge(v2.org_id, v2.scan_id)
    extras = {
        "merged": True,
        "outcome": _summarise_outcome(merge_outcome),
        "input_count": pre_merge_count,
        "kept_count": canonical_count,
        "dropped_count": merged_count,
        "io_label": "features → canonical features",
    }
    logger.info(
        "scan_feature_merge_done",
        scan_id=str(v2.scan_id),
        repo_count=len(repo_paths),
        pre_merge=pre_merge_count,
        canonical=canonical_count,
        merged=merged_count,
    )
    return StageOutput(communities=communities, dropped=[], extras=extras)


def _summarise_outcome(outcome: Any) -> dict[str, Any]:
    """Trim the legacy merge return-dict to JSONable extras for the timeline."""
    if not isinstance(outcome, dict):
        return {}
    return {k: v for k, v in outcome.items() if isinstance(v, int | str | bool | float)}


async def _count_pre_merge_features(org_id: Any, scan_id: Any) -> int:
    """Count synthesized rows for this scan before merge runs.

    Reads from the immutable ``synthesized_features`` table — the same
    rows the synthesize stage just wrote. Returns 0 on any failure so
    the chip falls back gracefully instead of marking the merge failed.
    """
    from sqlalchemy import func, select

    from app.models.synthesized_feature import SynthesizedFeature

    try:
        async with with_session(org_id) as db:
            stmt = (
                select(func.count())
                .select_from(SynthesizedFeature)
                .where(
                    SynthesizedFeature.org_id == org_id,
                    SynthesizedFeature.scan_id == scan_id,
                    SynthesizedFeature.superseded_at.is_(None),
                )
            )
            return int((await db.execute(stmt)).scalar_one() or 0)
    except Exception:
        logger.exception("scan_feature_merge_pre_count_failed")
        return 0


async def _count_post_merge(org_id: Any, scan_id: Any) -> tuple[int, int]:
    """Return (canonical_count, merged_count) after merge has updated outcomes."""
    from sqlalchemy import func, select

    from app.models.scan_phase import MergeOutcome
    from app.models.synthesized_feature import SynthesizedFeature

    try:
        async with with_session(org_id) as db:
            base = (
                select(func.count())
                .select_from(SynthesizedFeature)
                .where(
                    SynthesizedFeature.org_id == org_id,
                    SynthesizedFeature.scan_id == scan_id,
                    SynthesizedFeature.superseded_at.is_(None),
                )
            )
            canonical = int(
                (
                    await db.execute(
                        base.where(SynthesizedFeature.merge_outcome == MergeOutcome.CANONICAL)
                    )
                ).scalar_one()
                or 0
            )
            merged = int(
                (
                    await db.execute(
                        base.where(SynthesizedFeature.merge_outcome == MergeOutcome.MERGED_INTO)
                    )
                ).scalar_one()
                or 0
            )
            return canonical, merged
    except Exception:
        logger.exception("scan_feature_merge_post_count_failed")
        return 0, 0
