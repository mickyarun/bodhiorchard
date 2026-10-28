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

"""Where a repo's sandbox scan worktrees live.

Each tracked repo gets its own folder,
``<data_dir>/scan-worktrees/<org_id>/<repo_id>``, so two orgs (or two
repos in one org) with the same repo name never share a worktree. Keying
by the repo's basename used to let org B reuse org A's worktree and
index A's code.

Sandbox runs without an org or repo id fall back to
``<data_dir>/scan-worktrees/unscoped/<digest>``, where the digest comes
from the repo's resolved path, which is unique per repo on this host.

Folders from the old basename layout are not deleted here: the ingest
stage drops a repo's old worktree through ``git worktree remove`` when it
next rebuilds that repo's worktree, and anything left belongs to a repo
this code can't attribute.
"""

from __future__ import annotations

import hashlib
import os.path
import uuid
from pathlib import Path

from app.config import settings

SCAN_WORKTREES_DIRNAME = "scan-worktrees"
UNSCOPED_DIRNAME = "unscoped"
_DIGEST_LENGTH = 32


def scan_worktrees_root() -> Path:
    """``<data_dir>/scan-worktrees``, read at call time so tests can override it."""
    return Path(settings.storage.data_dir) / SCAN_WORKTREES_DIRNAME


def scan_worktree_parent(
    repo_path: str,
    *,
    org_id: uuid.UUID | None,
    repo_id: uuid.UUID | None,
) -> Path:
    """Return the folder holding this repo's sandbox worktrees.

    Both ids are UUIDs, so the folder names can't carry path syntax.
    """
    root = scan_worktrees_root()
    if org_id is not None and repo_id is not None:
        return root / str(org_id) / str(repo_id)
    resolved = os.path.realpath(repo_path).encode("utf-8", "surrogateescape")
    digest = hashlib.sha256(resolved).hexdigest()[:_DIGEST_LENGTH]
    return root / UNSCOPED_DIRNAME / digest
