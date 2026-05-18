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

"""Feature lifecycle service — bridges BUDs to the feature registry.

Creates PLANNED features when BUDs are written, transitions them
through in_progress → implemented as work progresses, and
soft-deletes them when BUDs are wilted or deleted.

BUD-authored features live in the same ``features`` table as
scan-authored ones but are tagged ``source='bud'`` and intentionally
have no PRIMARY ``feature_to_repo`` junction (they describe planned
work, not synthesised code). That missing-junction property is what
keeps BUD rows out of the reconciler's reach: ``bulk_load_for_reconcile``
INNER-JOINs on PRIMARY junctions, so BUD-authored rows are excluded
*structurally* — there is no ``source=`` predicate in the reconciler
itself. The orphan-feature audit is a separate code path and DOES
filter by ``source='scan'`` explicitly (see
``FeatureRepository.find_orphan_active_feature_ids``).

Identity for BUD-authored rows uses ``cluster_signature='bud:<ref>'``
so a future scan that picks up the same source_ref doesn't collide
on the structural-identity index.
"""

import re
import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDStatus
from app.models.feature import Feature
from app.repositories.feature import FeatureRepository
from app.services.embedding_service import embedding_service

logger = structlog.get_logger(__name__)

# Words filtered out when extracting tags from BUD titles
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "not",
        "no",
        "as",
        "if",
        "so",
    }
)

# Section headers that indicate acceptance criteria / capabilities
_CRITERIA_HEADERS = re.compile(
    r"^#{1,3}\s*(acceptance\s+criteria|requirements|capabilities|user\s+stories)",
    re.IGNORECASE,
)


@dataclass
class FeatureSummary:
    """Structured summary extracted from a BUD for feature registry."""

    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def extract_feature_from_bud(title: str, requirements_md: str) -> FeatureSummary:
    """Extract a feature summary from BUD title and markdown content.

    Pure text-parsing — no LLM calls. Designed to run in the request path.

    Args:
        title: The BUD title.
        requirements_md: The BUD markdown content.

    Returns:
        A FeatureSummary with name, description, capabilities, and tags.
    """
    # Name: strip common prefixes
    name = re.sub(r"^(BUD|PRD|Feature|RFC)\s*[:\-–—]\s*", "", title, flags=re.IGNORECASE).strip()
    if not name:
        name = title.strip()

    # Description: first non-heading, non-empty paragraph
    description = ""
    for line in requirements_md.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            continue
        description = stripped[:300]
        break

    # Capabilities: find acceptance criteria / requirements section, extract bullets
    capabilities: list[str] = []
    in_criteria_section = False
    for line in requirements_md.split("\n"):
        stripped = line.strip()
        if _CRITERIA_HEADERS.match(stripped):
            in_criteria_section = True
            continue
        if in_criteria_section:
            if stripped.startswith("#"):
                break  # Next section
            if stripped.startswith(("- ", "* ")):
                bullet_text = stripped[2:].strip()
                if bullet_text:
                    capabilities.append(bullet_text)
                    if len(capabilities) >= 6:
                        break

    # Tags: lowercase words from title, filter stop words
    words = re.findall(r"[a-zA-Z]+", name)
    tags = [w.lower() for w in words if w.lower() not in _STOP_WORDS][:5]

    return FeatureSummary(name=name, description=description, capabilities=capabilities, tags=tags)


def _format_planned_content(summary: FeatureSummary, bud_ref: str) -> str:
    """Format content for a PLANNED feature registry entry.

    Args:
        summary: The extracted feature summary.
        bud_ref: BUD reference string (e.g. "BUD-042").

    Returns:
        Formatted plain-text content optimized for embedding and agent reading.
    """
    lines = [summary.description, ""]
    lines.append("Status: PLANNED")
    lines.append(f"Source: {bud_ref}")

    if summary.capabilities:
        lines.append("")
        lines.append("Capabilities:")
        for cap in summary.capabilities:
            lines.append(f"- {cap}")

    return "\n".join(lines)


async def create_planned_feature(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_number: int,
    title: str,
    requirements_md: str,
) -> Feature:
    """Create or refresh a PLANNED ``Feature`` row from a BUD.

    Upserts by ``source_ref`` (``BUD-XXX``) to handle re-creation of
    BUDs with the same number. Embeds inline so the row is immediately
    semantic-searchable. No PRIMARY junction is created — BUD-authored
    rows are repo-agnostic by design.
    """
    summary = extract_feature_from_bud(title, requirements_md)
    bud_ref = f"BUD-{bud_number:03d}"
    content = _format_planned_content(summary, bud_ref)
    feature_title = f"Feature: {summary.name}"

    feat_repo = FeatureRepository(db, org_id=org_id)
    existing = await feat_repo.get_by_source_ref(bud_ref, source="bud")

    embedding: list[float] | None = None
    try:
        text = f"{feature_title}\n{content}"[:2000]
        embedding = await embedding_service.embed(text)
    except Exception:
        logger.warning("planned_feature_embed_failed", bud_ref=bud_ref)

    if existing is not None:
        await feat_repo.update_in_place(
            existing.id,
            feature_title=feature_title,
            description=content,
            capabilities={"capabilities": list(summary.capabilities)},
            cluster_names=[],
            cluster_signature=existing.cluster_signature,
            tags=list(summary.tags),
            embedding=embedding,
            last_seen_sha=existing.last_seen_sha,
            feature_status="planned",
        )
        if not existing.is_active:
            await feat_repo.revive(existing.id, last_seen_sha=existing.last_seen_sha)
        await db.flush()
        await db.refresh(existing)
        logger.info(
            "planned_feature_updated",
            org_id=str(org_id),
            bud_ref=bud_ref,
            feature_title=feature_title,
        )
        return existing

    feature = await feat_repo.insert(
        feature_title=feature_title,
        description=content,
        capabilities={"capabilities": list(summary.capabilities)},
        cluster_names=[],
        cluster_signature=f"bud:{bud_ref}",
        tags=list(summary.tags),
        embedding=embedding,
        source="bud",
        source_ref=bud_ref,
        feature_status="planned",
    )
    logger.info(
        "planned_feature_created",
        org_id=str(org_id),
        bud_ref=bud_ref,
        feature_title=feature_title,
    )
    return feature


async def transition_feature_for_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_number: int,
    new_status: str | BUDStatus,
) -> None:
    """Transition a BUD-authored feature based on BUD status change."""
    bud_ref = f"BUD-{bud_number:03d}"
    new_status_str = str(new_status)

    feat_repo = FeatureRepository(db, org_id=org_id)
    feature = await feat_repo.get_by_source_ref(bud_ref, source="bud")
    if feature is None:
        logger.debug("transition_feature_no_item", bud_ref=bud_ref)
        return

    if new_status_str == BUDStatus.DISCARDED:
        await feat_repo.mark_inactive([feature.id])
        logger.info("feature_deactivated", bud_ref=bud_ref)
        return
    if new_status_str in (BUDStatus.TECH_ARCH, BUDStatus.DESIGN):
        # Still pre-development — keep as planned.
        return
    if new_status_str == BUDStatus.DEVELOPMENT and feature.feature_status == "planned":
        await feat_repo.update_in_place(
            feature.id,
            feature_title=feature.feature_title,
            description=feature.description,
            capabilities=feature.capabilities or {},
            cluster_names=list(feature.cluster_names or []),
            cluster_signature=feature.cluster_signature,
            tags=list(feature.tags or []),
            embedding=list(feature.embedding) if feature.embedding is not None else None,
            last_seen_sha=feature.last_seen_sha,
            feature_status="in_progress",
        )
        logger.info("feature_in_progress", bud_ref=bud_ref)
        return
    if new_status_str in (BUDStatus.PROD, BUDStatus.CLOSED):
        await _record_feature_learning(db, org_id, bud_number, bud_ref)
    # Other statuses: no change (scan pipeline handles "implemented")


async def _record_feature_learning(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_number: int,
    bud_ref: str,
) -> None:
    """Populate FeatureLearning with actual cycle time when a BUD completes.

    Seeds the historical calibration layer so future estimates improve.
    """
    from app.models.feature_learning import FeatureLearning
    from app.repositories.bud import BUDRepository

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_number(bud_number)
    if not bud:
        return

    # Skip if already recorded (PROD → CLOSED would call twice)
    from sqlalchemy import select

    existing = await db.execute(
        select(FeatureLearning).where(
            FeatureLearning.org_id == org_id,
            FeatureLearning.bud_id == bud.id,
        )
    )
    if existing.scalar_one_or_none():
        logger.debug("feature_learning_already_exists", bud_ref=bud_ref)
        return

    # Actual cycle time from created_at to now
    cycle_days = (bud.updated_at - bud.created_at).days if bud.created_at else None

    # Estimated days from original AI estimate (if it existed)
    estimated_days = None
    summary = (bud.estimated_dates or {}).get("_summary", {})
    if summary.get("prod_p70"):
        try:
            from datetime import datetime as dt

            p70 = dt.fromisoformat(summary["prod_p70"]).date()
            generated = dt.fromisoformat(summary["generated_at"]).date()
            estimated_days = float((p70 - generated).days)
        except (ValueError, KeyError, TypeError):
            pass

    qa_count = len(bud.qa_automation_cases or []) + len(bud.qa_manual_cases or [])

    learning = FeatureLearning(
        org_id=org_id,
        bud_id=bud.id,
        cycle_time_days=float(cycle_days) if cycle_days else None,
        estimated_days=estimated_days,
        bug_count=qa_count,
    )
    db.add(learning)
    await db.flush()
    logger.info("feature_learning_recorded", bud_ref=bud_ref, cycle_days=cycle_days)
