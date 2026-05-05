# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""MCP-side helper for persisting synthesised features.

Called by ``write_feature_registry`` (legacy) and the v2 synthesis
prompt's ``write_synthesis_feature`` MCP tool. Each call writes two
rows in the same transaction:

* ``features``                — the immutable feature record.
* ``feature_to_repo``         — a PRIMARY junction row binding the
                                 feature to its synthesis source repo
                                 and capturing ``code_locations``.

The post-synthesis ``backend_link`` stage adds further BACKEND junction
rows once the route index for the org's backend repos is built.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.organization import Organization
from app.repositories.feature import FeatureRepository
from app.repositories.feature_to_repo import upsert_primary
from app.services.feature_content import try_embed

logger = structlog.get_logger(__name__)


async def persist_synth_feature(
    *,
    db: AsyncSession,
    org: Organization,
    repo_id: uuid.UUID,
    feature_title: str,
    description: str,
    capabilities: list[str],
    cluster_names: list[str],
    code_locations: dict[str, list[str]] | None,
    tags: list[str] | None = None,
) -> Feature:
    """Insert a ``features`` row + PRIMARY ``feature_to_repo`` junction row.

    Features are repo-scoped, not scan-scoped — the ``Feature`` row
    carries no scan binding. The synthesise stage wholesale-wipes the
    repo's features at the start of each not-skip pass, so the table
    arrives empty for ``repo_id`` and a fresh insert is always safe. The
    partial unique index ``ux_ftr_primary_title (repo_id, feature_title)
    WHERE role='primary'`` guards against a regression in the synthesis
    prompt that emits the same title twice in one run.
    """
    feature_repo = FeatureRepository(db, org_id=org.id)

    # Compute the embedding once at write-time. Persisting the vector
    # here saves recomputing it on every downstream pass and keeps the
    # row immutable. ``try_embed`` is fail-soft — returns None on any
    # error, in which case downstream consumers lazy-fill on first use.
    embedding = await try_embed(feature_title, description)

    feature = await feature_repo.insert(
        feature_title=feature_title,
        description=description,
        capabilities={"capabilities": list(capabilities)},
        cluster_names=list(cluster_names),
        tags=list(tags or []),
        embedding=embedding,
    )
    await upsert_primary(
        db,
        feature_id=feature.id,
        repo_id=repo_id,
        feature_title=feature_title,
        code_locations=dict(code_locations or {}),
    )
    return feature
