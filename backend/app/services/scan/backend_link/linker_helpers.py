# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pure helpers used by the global ``backend_link`` phase.

These functions only manipulate paths, dicts, and the in-memory
:class:`BackendIndex`. They have no DB, IO, or session dependencies, so
they live alongside the regex / extractor modules in this package
rather than inside ``phase_impls``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.services.scan.backend_link.backend_indexer import BackendIndex

_SEED_FILE_EXTS = (".ts", ".tsx", ".js", ".mjs", ".vue")


@dataclass(frozen=True)
class BackendBucket:
    """One backend repo's slice of a feature's cross-layer link.

    Produced by :func:`bucket_per_repo`; consumed by
    :func:`replace_backend_links` to populate one BACKEND
    ``feature_to_repo`` row.

    * ``api_paths`` — sorted, deduped normalised routes the feature
      calls that this backend declares. Stored on
      ``feature_to_repo.api_paths``.
    * ``code_locations`` — the backend source files that declared those
      routes, in the same JSON shape the PRIMARY junction uses
      (``{"backend": [...]}``). Stored on
      ``feature_to_repo.code_locations`` so a single read of one
      junction row answers "which backend file(s) does this feature
      touch in this repo?".
    """

    api_paths: list[str]
    code_locations: dict[str, list[str]]


def resolve_seed_paths(repo_root: Path, code_locations: dict[str, list[str]] | None) -> list[Path]:
    """Expand a feature's ``code_locations`` blob to concrete source files.

    Synth output mixes file paths and directory paths (with or without a
    trailing slash). Directories expand to their TS/JS/Vue contents so a
    feature whose seed lists ``services/user/`` instead of every file
    inside it still gets every relevant file walked.
    """
    if not isinstance(code_locations, dict):
        return []
    out: list[Path] = []
    for entries in code_locations.values():
        if not isinstance(entries, list):
            continue
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


def bucket_per_repo(
    api_paths: Iterable[str],
    index: BackendIndex,
) -> dict[uuid.UUID, BackendBucket]:
    """Group matched API paths AND their declaring files by backend repo.

    A path declared by two backends ends up in both buckets — the link
    is a fact about the feature → repo edge, and both edges are real.
    Empty buckets are dropped because :func:`replace_backend_links`
    raises on them by contract.

    The file-side of each bucket comes from :class:`BackendIndex`'s
    lookup result tuples ``(repo_id, file_path)`` — these are the
    backend source files that declare the matched routes, exactly the
    "this is where the feature lives in the backend" answer the future
    Feature tab needs.
    """
    paths_per_repo: dict[uuid.UUID, list[str]] = defaultdict(list)
    files_per_repo: dict[uuid.UUID, set[str]] = defaultdict(set)
    for api_path in api_paths:
        for repo_id, file_path in index.lookup(api_path):
            if api_path not in paths_per_repo[repo_id]:
                paths_per_repo[repo_id].append(api_path)
            files_per_repo[repo_id].add(file_path)
    buckets: dict[uuid.UUID, BackendBucket] = {}
    for repo_id, paths in paths_per_repo.items():
        if not paths:
            continue
        buckets[repo_id] = BackendBucket(
            api_paths=sorted(paths),
            code_locations={"backend": sorted(files_per_repo[repo_id])},
        )
    return buckets
