# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
