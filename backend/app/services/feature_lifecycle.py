"""Feature lifecycle service — bridges BUDs to the feature registry.

Creates PLANNED feature_registry entries when BUDs are written,
transitions them through in_progress → implemented as work progresses,
and deactivates them when BUDs are wilted or deleted.
"""

import re
import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDStatus
from app.models.knowledge_item import KnowledgeItem
from app.repositories.knowledge_item import KnowledgeItemRepository
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
) -> KnowledgeItem:
    """Create a PLANNED feature_registry entry from a BUD.

    Upserts by source_ref to handle re-creation of BUDs with same number.
    Embeds the item inline for immediate semantic searchability.

    Args:
        db: The async database session.
        org_id: The organization UUID.
        bud_number: The BUD number for source_ref linking.
        title: The BUD title.
        requirements_md: The BUD markdown content.

    Returns:
        The created or updated KnowledgeItem.
    """
    summary = extract_feature_from_bud(title, requirements_md)
    bud_ref = f"BUD-{bud_number:03d}"
    content = _format_planned_content(summary, bud_ref)
    feature_title = f"Feature: {summary.name}"

    # Upsert by source_ref
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    item = await ki_repo.get_by_source_ref_and_category(bud_ref, "feature_registry")

    if item:
        item.title = feature_title
        item.content = content
        item.tags = summary.tags
        item.feature_status = "planned"
        item.is_active = True
    else:
        item = KnowledgeItem(
            org_id=org_id,
            category="feature_registry",
            title=feature_title,
            content=content,
            source="bud",
            source_ref=bud_ref,
            tags=summary.tags,
            feature_status="planned",
            is_active=True,
        )
        await ki_repo.add(item)

    await db.flush()

    # Embed inline — failure is non-fatal
    try:
        text = f"{item.title}\n{item.content or ''}"[:2000]
        item.embedding = await embedding_service.embed(text)
    except Exception:
        logger.warning("planned_feature_embed_failed", bud_ref=bud_ref)

    logger.info(
        "planned_feature_created",
        org_id=str(org_id),
        bud_ref=bud_ref,
        feature_title=feature_title,
    )
    return item


async def transition_feature_for_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_number: int,
    new_status: str | BUDStatus,
) -> None:
    """Transition a feature_registry item based on BUD status change.

    Args:
        db: The async database session.
        org_id: The organization UUID.
        bud_number: The BUD number to look up.
        new_status: The new BUD status (string or BUDStatus enum).
    """
    bud_ref = f"BUD-{bud_number:03d}"
    new_status_str = str(new_status)

    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    item = await ki_repo.get_by_source_ref_and_category(bud_ref, "feature_registry")
    if item is None:
        logger.debug("transition_feature_no_item", bud_ref=bud_ref)
        return

    if new_status_str == BUDStatus.DISCARDED:
        item.is_active = False
        item.embedding = None
        logger.info("feature_deactivated", bud_ref=bud_ref)
    elif new_status_str in (BUDStatus.TECH_ARCH, BUDStatus.DESIGN):
        # Still pre-development — keep as planned
        pass
    elif new_status_str == BUDStatus.DEVELOPMENT and item.feature_status == "planned":
        item.feature_status = "in_progress"
        logger.info("feature_in_progress", bud_ref=bud_ref)
    # Other statuses: no change (scan pipeline handles "implemented")
