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

"""Shared grounding context for BUD agent prompt builders.

Every BUD-stage prompt builder (PM, Designer, TechPlanner, Code Reviewer,
Tester) needs the same slice of "what existing features does this BUD
touch?" data so it can render ``code_locations`` and stop hallucinating
ungrounded content. This module provides:

* :class:`BudAgentContext` — the bundle each builder needs.
* :func:`load_bud_agent_context` — single async load with eager-loaded
  ``Feature.repo_links`` so ``code_locations`` ride along.
* :func:`format_code_locations_section` — common renderer the builders
  use to lay out the "existing code to read" block, so every stage's
  output looks consistent.

The loader is called once per agent task. Builders that don't use
linked features (e.g. the PM stage on a brand-new BUD with no links
yet) still pay one cheap join that returns an empty list.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.repositories.bud_feature_link import BUDFeatureLinkRepository


@dataclass(frozen=True, slots=True)
class BudAgentContext:
    """State shared across every BUD-stage prompt builder.

    Currently holds only the linked-feature list, but the shape is
    intentionally expandable — future grounding signals (repo
    summaries, recent BUD activity, etc.) belong here so the four
    builders stay in lockstep instead of each loading their own slice.
    """

    linked_features: list[Feature]


async def load_bud_agent_context(
    db: AsyncSession,
    *,
    bud_id: uuid.UUID,
    org_id: uuid.UUID,
) -> BudAgentContext:
    """Load the grounding context for one BUD agent task.

    The returned :class:`Feature` objects have their ``repo_links``
    eager-loaded via ``selectinload`` (see
    :meth:`BUDFeatureLinkRepository.list_features_for_bud`), so
    builders can render ``code_locations`` without firing N+1 queries.
    """
    link_repo = BUDFeatureLinkRepository(db, org_id=org_id)
    linked_features = await link_repo.list_features_for_bud(bud_id)
    return BudAgentContext(linked_features=linked_features)


def format_code_locations_section(
    features: Iterable[Feature],
    *,
    layers: Iterable[str] | None = None,
    heading: str = "## Existing code to read before planning",
    instruction: str | None = None,
    empty_text: str = "",
) -> str:
    """Render linked features + their PRIMARY-link code_locations.

    Each ``feature`` is expected to have ``repo_links`` already loaded.
    Only PRIMARY-role junctions carry ``code_locations`` per the
    synthesis pipeline — non-primary rows are skipped.

    Args:
        features: Linked features (typically from
            :attr:`BudAgentContext.linked_features`).
        layers: Which ``code_locations`` keys to render. ``None`` means
            "all layers found on the feature" — useful when the caller
            doesn't know in advance which layers exist.
        heading: Markdown heading for the section.
        instruction: Optional one-line instruction shown below the
            feature list (e.g. "call ``code_context`` on these symbols
            before planning").
        empty_text: Returned verbatim when ``features`` is empty. Pass
            ``""`` (default) to omit the section entirely.
    """
    feature_blocks: list[str] = []
    layer_filter = set(layers) if layers is not None else None
    for feature in features:
        primary = _primary_link(feature)
        if primary is None or not primary.code_locations:
            continue
        block_lines = [f"### {feature.feature_title}"]
        for layer, paths in primary.code_locations.items():
            if layer_filter is not None and layer not in layer_filter:
                continue
            if not paths:
                continue
            block_lines.append(f"- **{layer}**: {', '.join(paths)}")
        if len(block_lines) > 1:
            feature_blocks.append("\n".join(block_lines))

    if not feature_blocks:
        return empty_text

    section = f"{heading}\n\n" + "\n\n".join(feature_blocks)
    if instruction:
        section += f"\n\n{instruction}"
    return section + "\n"


def _primary_link(feature: Feature) -> FeatureToRepo | None:
    """Return the PRIMARY-role :class:`FeatureToRepo` row, if any."""
    for link in feature.repo_links:
        if link.role == FeatureToRepoRole.PRIMARY:
            return link
    return None
