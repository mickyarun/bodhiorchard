# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Backend-link stage: populate ``backend_repo_ids`` and ``backend_api_paths``.

For every frontend ``XLMSynthesizedFeature`` row, scan its
``code_locations->'frontend'`` files for API URL paths, look those up in
the pre-built backend index, and write the matching repo ids + observed
paths back to the synth row.

This is a deterministic, zero-LLM pre-pass. Downstream stages (cluster
merge, pair verifier) can use the populated fields as a strong signal for
which backend repos a frontend feature is genuinely coupled to.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.backend_link.backend_indexer import (
    BackendIndex,
    build_index,
)
from experiments.cross_layer_merge.backend_link.endpoint_extractor import (
    build_url_constants_map,
    extract_api_paths,
)
from experiments.cross_layer_merge.backend_link.nuxt_autoimport import (
    build_store_map,
)
from experiments.cross_layer_merge.schema import (
    XLMRepoLayer,
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)

log = structlog.get_logger(__name__)

_SEED_FILE_EXTS = (".ts", ".tsx", ".js", ".mjs", ".vue")


def _resolve_seed_paths(repo_root: Path, entries: list[object]) -> list[Path]:
    """Expand each ``code_locations`` entry to concrete source files.

    Synth output mixes file paths and directory paths (with or without
    a trailing slash). Directories are expanded to their ``.ts/.tsx/
    .js/.mjs/.vue`` contents so a feature whose seed lists ``services/
    user/`` instead of every file inside it still gets every relevant
    file walked. Non-string entries and missing paths are skipped.
    """
    out: list[Path] = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        candidate = repo_root / entry
        if candidate.is_dir():
            for ext in _SEED_FILE_EXTS:
                out.extend(candidate.rglob(f"*{ext}"))
        elif candidate.is_file():
            out.append(candidate)
    return out


@dataclass
class BackendLinkSummary:
    """Counters surfaced to the CLI."""

    frontend_repos: int
    backend_repos_indexed: int
    indexed_routes: int
    frontend_features_processed: int
    features_linked: int


async def run_backend_link() -> BackendLinkSummary:
    """End-to-end: build index, walk frontend synth rows, write fields back."""
    async with AsyncSessionLocal() as session:
        repos = (await session.execute(select(XLMTrackedRepo))).scalars().all()

    frontend_repos = [r for r in repos if r.repo_layer == XLMRepoLayer.FRONTEND]
    backend_repos = [r for r in repos if r.repo_layer == XLMRepoLayer.BACKEND]
    log.info(
        "backend_link.repos",
        frontend=len(frontend_repos),
        backend=len(backend_repos),
    )

    index = build_index((r.id, Path(r.path)) for r in backend_repos if r.path is not None)
    log.info("backend_link.index_built", routes=len(index.paths))

    features_processed = 0
    features_linked = 0
    async with AsyncSessionLocal() as session:
        for repo in frontend_repos:
            if repo.path is None:
                log.warning("backend_link.frontend_no_path", repo=repo.name)
                continue
            repo_root = Path(repo.path)
            constants_map = build_url_constants_map(repo_root)
            store_map = build_store_map(repo_root)
            log.info(
                "backend_link.constants_map",
                repo=repo.name,
                constant_count=len(constants_map),
                store_count=len(store_map),
            )
            synth_rows = (
                (
                    await session.execute(
                        select(XLMSynthesizedFeature).where(
                            XLMSynthesizedFeature.repo_id == repo.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            for synth in synth_rows:
                features_processed += 1
                if _link_one(synth, repo_root, index, constants_map, store_map):
                    features_linked += 1
        await session.commit()

    summary = BackendLinkSummary(
        frontend_repos=len(frontend_repos),
        backend_repos_indexed=len(backend_repos),
        indexed_routes=len(index.paths),
        frontend_features_processed=features_processed,
        features_linked=features_linked,
    )
    log.info("backend_link.done", **summary.__dict__)
    return summary


def _link_one(
    synth: XLMSynthesizedFeature,
    repo_root: Path,
    index: BackendIndex,
    constants_map: dict[str, str],
    store_map: dict[str, Path],
) -> bool:
    """Populate ``synth.backend_repo_ids`` and ``synth.backend_api_paths``.

    Returns ``True`` if at least one backend repo matched.
    """
    frontend_files = (synth.code_locations or {}).get("frontend") or []
    if not isinstance(frontend_files, list):
        return False
    abs_paths = _resolve_seed_paths(repo_root, frontend_files)
    api_paths = extract_api_paths(
        abs_paths,
        constants_map=constants_map,
        repo_root=repo_root,
        store_map=store_map,
    )
    if not api_paths:
        synth.backend_api_paths = []
        synth.backend_repo_ids = []
        return False

    repo_hits: dict[UUID, int] = defaultdict(int)
    matched_paths: set[str] = set()
    for api_path in api_paths:
        for repo_id, _ in index.lookup(api_path):
            repo_hits[repo_id] += 1
            matched_paths.add(api_path)

    synth.backend_api_paths = sorted(api_paths)
    synth.backend_repo_ids = sorted(repo_hits, key=lambda rid: -repo_hits[rid])
    return bool(repo_hits)
