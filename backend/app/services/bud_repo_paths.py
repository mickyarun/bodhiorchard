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

"""Resolve the set of repo clone paths attached to a BUD.

The "what repos does this BUD touch on disk?" question is asked by several
agent-orchestration callers (pre-spawn token refresh, retry-path refresh,
future per-repo audits) and the answer always derives from the same
``bud.metadata_["confirmed_repos"]`` shape. Centralising the extraction
here keeps that metadata-shape knowledge in one place — a future schema
change (e.g. renaming the key or moving to a relation) only edits this
module, not every caller.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.repositories.tracked_repository import TrackedRepoRepository

__all__ = ["confirmed_repo_paths", "resolve_confirmed_repos"]


async def resolve_confirmed_repos(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_ids: set[str],
) -> list[dict[str, Any]]:
    """Map repo ids to the ``confirmed_repos`` metadata shape.

    Returns ``[{"repo_path", "repo_name"}, ...]`` for every id in
    ``repo_ids`` that resolves to an *active* tracked repository with a
    clone path. Ids that don't resolve (inactive, no path, unknown) are
    dropped — the caller decides whether an empty result is an error.

    Single source of truth for "which impacted repos can the code-review /
    testing agent actually run against", shared by the automatic
    PR-merge transition and the manual repo-selection endpoint so the two
    paths can't drift.
    """
    tr_repo = TrackedRepoRepository(db, org_id=org_id)
    triples = await tr_repo.get_active_id_path_name()
    return [
        {"repo_path": path, "repo_name": name}
        for rid, path, name in triples
        if str(rid) in repo_ids and path
    ]


def confirmed_repo_paths(
    bud: BUDDocument,
    fallback: str | None = None,
) -> list[str]:
    """Return the de-duplicated list of clone paths for ``bud``.

    Reads ``bud.metadata_["confirmed_repos"]`` and pulls out each entry's
    ``repo_path``. Empty / missing paths are skipped. The optional
    ``fallback`` (typically the prompt builder's ``working_dir``) is
    appended if it isn't already present — covers the rare path where a
    builder sets a working dir that isn't in ``confirmed_repos`` (e.g. a
    detached scratch clone).

    Order is preserved so the first-confirmed repo (which prompt builders
    use as ``working_dir``) stays first in the refresh loop — keeps logs
    aligned with the spawn's CWD.
    """
    meta = bud.metadata_ or {}
    raw_repos = meta.get("confirmed_repos", []) or []

    paths: list[str] = []
    for entry in raw_repos:
        if not isinstance(entry, dict):
            continue
        path = entry.get("repo_path")
        if isinstance(path, str) and path:
            paths.append(path)

    if fallback and fallback not in paths:
        paths.append(fallback)

    return list(dict.fromkeys(paths))
