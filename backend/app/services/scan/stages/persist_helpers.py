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

"""Side helpers for the ``persist_results`` stage.

* :func:`collect_head_shas` — runs ``git rev-parse HEAD`` across every
  scanned worktree and returns ``{repo_path: sha}``.
* :func:`load_org_config` — pulls the org's mutable config dict (the
  legacy persist phase mutates this in place).

Pulled out of ``persist_results.py`` so that file stays under the
size budget and only owns the wrapper-stage glue.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.organization import OrganizationRepository
from app.services.git_analyzer import get_head_sha

logger = structlog.get_logger(__name__)


async def collect_head_shas(repo_paths: list[str]) -> dict[str, str]:
    """``git rev-parse HEAD`` for every worktree, no-throw per path.

    Repos whose SHA can't be read are simply omitted from the dict;
    persist will treat them as unchanged (no SHA bump).
    """
    out: dict[str, str] = {}
    for path in repo_paths:
        try:
            sha = await get_head_sha(path)
        except Exception:
            logger.exception("scan_persist_head_sha_failed", path=path)
            continue
        if sha:
            out[path] = sha
    return out


async def load_org_config(db: AsyncSession, *, org_id: uuid.UUID) -> dict[str, Any]:
    """Return the org's config dict, defaulting to empty when missing."""
    org = await OrganizationRepository(db).get_by_id(org_id)
    if org is None:
        return {}
    raw = getattr(org, "config", None)
    if isinstance(raw, dict):
        return raw
    return {}
