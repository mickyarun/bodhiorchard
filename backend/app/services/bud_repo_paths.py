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

from app.models.bud import BUDDocument

__all__ = ["confirmed_repo_paths"]


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
