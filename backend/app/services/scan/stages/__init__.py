# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage registry. New reduction stages register themselves here.

A stage is a coroutine ``(ctx, communities, config) -> StageOutput``. Stage 0
(``ingest``) is special — it has no input communities; it produces the
ingest extras (HEAD SHA, meta.json stats) used by Stage 1's extract.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

from app.schemas.scan import Community


class StageOutput(NamedTuple):
    """What every stage returns to the workflow.

    ``communities`` is the kept set passed to the next stage. ``dropped``
    are recorded for the UI but do not flow downstream. ``extras`` is
    persisted alongside the StageResult and is free-form per stage
    (e.g. ingest stores HEAD SHA + gitnexus stats here).
    """

    communities: list[Community]
    dropped: list[Community]
    extras: dict[str, Any]


class StageContext(NamedTuple):
    """Read-only context handed to every stage.

    ``repo_path`` and ``repo_name`` are resolved by the workflow once and
    reused across stages so each stage doesn't re-derive them.
    """

    run_id: str
    repo_path: str
    repo_name: str


StageFn = Callable[[StageContext, list[Community], dict[str, Any]], Awaitable[StageOutput]]


# Lazy import to avoid circular imports — stage modules import from this file.
def _build_registry() -> dict[str, StageFn]:
    from app.services.scan.stages import (
        audit,
        backend_link,
        classify_repo,
        design_system,
        extract,
        extract_routes,
        filter_infra,
        hierarchical,
        ingest,
        merge_labels,
        persist_results,
        repo_setup,
        size_floor,
        skill_extraction,
        skill_remap,
        synthesize,
        top_n,
    )

    return {
        "repo_setup": repo_setup.run,
        "ingest": ingest.run,
        "classify_repo": classify_repo.run,
        "extract": extract.run,
        "merge_labels": merge_labels.run,
        "filter_infra": filter_infra.run,
        "hierarchical": hierarchical.run,
        "size_floor": size_floor.run,
        "top_n": top_n.run,
        "synthesize": synthesize.run,
        "extract_routes": extract_routes.run,
        "skill_extraction": skill_extraction.run,
        "design_system": design_system.run,
        "skill_remap": skill_remap.run,
        # ``backend_link`` is the GLOBAL stage; it's not in the per-repo
        # workflow (see ``DEFAULT_PER_REPO_STAGES`` in app/schemas/scan.py)
        # but is dispatched from ``GLOBAL_PHASE_ORDER``.
        "backend_link": backend_link.run,
        "persist_results": persist_results.run,
        "audit": audit.run,
    }


_STAGE_REGISTRY: dict[str, StageFn] | None = None


def get_stage(name: str) -> StageFn:
    """Lookup a registered stage by name. Raises ``KeyError`` when unknown."""
    global _STAGE_REGISTRY
    if _STAGE_REGISTRY is None:
        _STAGE_REGISTRY = _build_registry()
    if name not in _STAGE_REGISTRY:
        raise KeyError(f"Unknown stage: {name!r}. Known: {sorted(_STAGE_REGISTRY)}")
    return _STAGE_REGISTRY[name]


def known_stages() -> list[str]:
    """List of registered stage names — useful for API validation."""
    global _STAGE_REGISTRY
    if _STAGE_REGISTRY is None:
        _STAGE_REGISTRY = _build_registry()
    return sorted(_STAGE_REGISTRY)
