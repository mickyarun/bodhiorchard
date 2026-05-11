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

"""Sandbox port of ``app.services.merge_writer.promote_synth_to_ki``.

Single writer of ``xlm_knowledge_item`` rows. Given one synth row this
function:

1. If an active ``xlm_knowledge_item`` with the same title already
   exists, attach the synth row's repo to it and stamp the synth row
   ``MERGED_INTO``. Defends against title-twin uniqueness violations.
2. Otherwise create a fresh ``xlm_knowledge_item``, link its junction
   to the synth row's repo, back-fill ``synth.knowledge_item_id``, and
   stamp the synth row ``CANONICAL``.

Caller controls transaction boundaries.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from experiments.cross_layer_merge.schema import (
    XLMKnowledgeItem,
    XLMKnowledgeRepoLink,
    XLMMergeOutcome,
    XLMSynthesizedFeature,
)

log = structlog.get_logger(__name__)


_FEATURE_CATEGORY = "feature_registry"


async def promote_synth_to_ki(
    *,
    session: AsyncSession,
    synth: XLMSynthesizedFeature,
) -> XLMKnowledgeItem:
    """Promote one synth row to a canonical KI (or attach to a same-title twin).

    The function is idempotent: running it twice on the same synth row
    is safe — the second call sees ``merge_outcome=CANONICAL`` and
    returns the already-promoted KI without writing.
    """
    if synth.merge_outcome == XLMMergeOutcome.CANONICAL and synth.knowledge_item_id is not None:
        ki = await session.get(XLMKnowledgeItem, synth.knowledge_item_id)
        if ki is not None:
            return ki
    if synth.merge_outcome == XLMMergeOutcome.MERGED_INTO and synth.knowledge_item_id is not None:
        ki = await session.get(XLMKnowledgeItem, synth.knowledge_item_id)
        if ki is not None:
            return ki

    existing = await _find_active_same_title(session, synth.org_id, synth.feature_title)
    if existing is not None:
        await _ensure_link(session, existing.id, synth.repo_id, synth.code_locations)
        synth.knowledge_item_id = existing.id
        synth.merge_outcome = XLMMergeOutcome.MERGED_INTO
        synth.merged_into_id = None
        log.info(
            "promote.attach_existing",
            synth_id=str(synth.id),
            ki_id=str(existing.id),
            title=synth.feature_title,
        )
        return existing

    ki = XLMKnowledgeItem(
        id=uuid.uuid4(),
        org_id=synth.org_id,
        category=_FEATURE_CATEGORY,
        title=synth.feature_title,
        content=synth.description,
        tags=list(synth.tags or []) or None,
        embedding=synth.embedding,
        is_active=True,
        source_ref=None,
    )
    session.add(ki)
    await session.flush()

    await _ensure_link(session, ki.id, synth.repo_id, synth.code_locations)

    synth.knowledge_item_id = ki.id
    synth.merge_outcome = XLMMergeOutcome.CANONICAL
    synth.merged_into_id = None

    log.info(
        "promote.new_canonical",
        synth_id=str(synth.id),
        ki_id=str(ki.id),
        title=synth.feature_title,
    )
    return ki


async def _find_active_same_title(
    session: AsyncSession,
    org_id: uuid.UUID,
    title: str,
) -> XLMKnowledgeItem | None:
    """Return an active feature_registry KI with this title, if any."""
    return (
        await session.execute(
            select(XLMKnowledgeItem).where(
                XLMKnowledgeItem.org_id == org_id,
                XLMKnowledgeItem.category == _FEATURE_CATEGORY,
                XLMKnowledgeItem.title == title,
                XLMKnowledgeItem.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def _ensure_link(
    session: AsyncSession,
    ki_id: uuid.UUID,
    repo_id: uuid.UUID,
    code_locations: dict[str, Any] | None,
) -> None:
    """Create the (ki, repo) junction row if not already present.

    Mirrors prod's ``ki_repo.link_to_repo`` idempotent semantics so
    re-running ``promote_synth_to_ki`` on the same synth row doesn't
    duplicate junctions.
    """
    existing = (
        await session.execute(
            select(XLMKnowledgeRepoLink).where(
                XLMKnowledgeRepoLink.knowledge_id == ki_id,
                XLMKnowledgeRepoLink.repo_id == repo_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        XLMKnowledgeRepoLink(
            knowledge_id=ki_id,
            repo_id=repo_id,
            code_locations=code_locations or None,
        )
    )
    await session.flush()
