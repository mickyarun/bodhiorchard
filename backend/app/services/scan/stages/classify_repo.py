# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-repo stage that classifies the repo's architectural role.

Runs after :mod:`ingest` (so the worktree exists on disk) and before
:mod:`extract`. Inspects ``ctx.repo_path`` via
:func:`app.services.scan.repo_classify.classify` and writes the
``repo_layer``, ``tech_stack``, and ``db_flavor`` columns on the
``tracked_repositories`` row.

Cheap (file-glob only, ~ms) and idempotent — runs on every scan so a
repo whose framework changes between scans gets re-classified. The
downstream :mod:`backend_link` stage reads ``repo_layer`` to decide
whether a repo participates as a backend index target or as a frontend
whose features should be linked.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog

from app.repositories.tracked_repository import TrackedRepoRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.repo_classify import classify
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import resolve_runtime_context

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Classify the repo and persist (layer, tech_stack, db_flavor).

    Returns the classification in ``extras`` so the chip popover can
    surface it; ``communities`` and ``dropped`` stay empty since this
    stage is not part of the cluster reduction chain.
    """
    runtime = resolve_runtime_context(config)
    repo_id_raw = config.get("repo_id")
    if runtime is None or repo_id_raw is None:
        logger.info("scan_classify_repo_skipped_no_runtime_context", repo=ctx.repo_name)
        return StageOutput(communities=[], dropped=[], extras={"skipped": True})

    repo_id = uuid.UUID(str(repo_id_raw))
    # Prefer the freshly-ingested worktree (matches what ``backend_link``
    # will index later); fall back to the canonical repo path.
    worktree_path = config.get("v2_worktree_path") or ctx.repo_path
    classification = classify(ctx.repo_name, str(worktree_path))

    async with with_session(runtime.org_id) as db:
        await TrackedRepoRepository(db, org_id=runtime.org_id).set_classification(
            repo_id,
            layer=classification.layer,
            tech_stack=classification.tech_stack,
            db_flavor=classification.db_flavor,
        )
        await db.commit()

    extras: dict[str, Any] = {
        "repo_layer": classification.layer.value,
        "tech_stack": classification.tech_stack,
        "db_flavor": classification.db_flavor,
        "input_count": 1,
        "kept_count": 1,
        "io_label": "repo → classified",
    }
    logger.info(
        "scan_classify_repo_done",
        repo=ctx.repo_name,
        layer=classification.layer.value,
        tech_stack=classification.tech_stack,
        db_flavor=classification.db_flavor,
    )
    return StageOutput(communities=[], dropped=[], extras=extras)


def detect_layer(worktree_path: str | Path, repo_name: str) -> str | None:
    """Module-level helper for tests / ad-hoc CLI use.

    Returns the layer enum value (``frontend``/``backend``/…) or
    ``None`` if the classifier had no opinion. Wraps :func:`classify`
    without touching the database.
    """
    return classify(repo_name, str(worktree_path)).layer.value
