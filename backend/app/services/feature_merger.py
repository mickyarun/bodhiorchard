"""Feature deduplication and merge logic for scan pipeline.

Handles semantic duplicate detection via pgvector cosine similarity,
targeted merge prompt building, and post-merge deduplication of
concurrent MCP retries.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem
from app.repositories.knowledge_item import KnowledgeItemRepository

logger = structlog.get_logger(__name__)


async def find_semantic_duplicates(
    db: AsyncSession,
    org_id: uuid.UUID,
    threshold: float = 0.78,
    max_group_size: int = 6,
) -> list[list[KnowledgeItem]]:
    """Find features with different names but overlapping content.

    Uses strict pairwise matching — only items that are directly similar
    to each other are grouped. No transitive chaining (A~B and B~C does
    NOT imply A~C).  Groups larger than ``max_group_size`` are dropped
    as likely false positives from domain-similar features.

    Requires embeddings to exist (run after embedding phase).
    Returns groups of 2+ items that should be merged by Claude.
    """
    # Self-join on cosine distance across ALL active feature_registry items
    # (both cross-repo and intra-repo).  With <50 features this is cheap.
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    rows = await ki_repo.find_semantic_duplicates("feature_registry", threshold)

    if not rows:
        return []

    # Collect all involved IDs and load items
    id_set: set[uuid.UUID] = set()
    edges: list[tuple[uuid.UUID, uuid.UUID, float]] = []
    for a_id, b_id, sim in rows:
        id_set.add(a_id)
        id_set.add(b_id)
        edges.append((a_id, b_id, sim))

    item_map = await ki_repo.get_by_ids(id_set)

    # Greedy pairwise grouping: each item can join at most one group.
    # Unlike single-linkage clustering, this prevents transitive chaining
    # where A~B and B~C would merge A and C even if they're dissimilar.
    # Edges are processed highest-similarity-first so the best pairs form.
    edges.sort(key=lambda e: e[2], reverse=True)
    assigned: set[uuid.UUID] = set()
    groups_map: dict[uuid.UUID, list[uuid.UUID]] = {}

    for a_id, b_id, _sim in edges:
        a_group = next((g for g, members in groups_map.items() if a_id in members), None)
        b_group = next((g for g, members in groups_map.items() if b_id in members), None)

        if a_group is not None and b_group is not None:
            # Both already in groups — skip to avoid chaining
            continue
        elif a_group is not None:
            if len(groups_map[a_group]) < max_group_size and b_id not in assigned:
                groups_map[a_group].append(b_id)
                assigned.add(b_id)
        elif b_group is not None:
            if len(groups_map[b_group]) < max_group_size and a_id not in assigned:
                groups_map[b_group].append(a_id)
                assigned.add(a_id)
        else:
            # Neither assigned — start new group
            groups_map[a_id] = [a_id, b_id]
            assigned.add(a_id)
            assigned.add(b_id)

    result: list[list[KnowledgeItem]] = []
    for members in groups_map.values():
        if len(members) >= 2:
            group = [item_map[uid] for uid in members if uid in item_map]
            if len(group) >= 2:
                result.append(group)

    if result:
        logger.info(
            "semantic_duplicates_found",
            groups=len(result),
            sizes=[len(g) for g in result],
            threshold=threshold,
        )

    return result


def _merge_group_code_locations(group: list[KnowledgeItem]) -> dict[str, list[str]]:
    """Compute merged code_locations from all items in a duplicate group.

    Reads code_locations from junction links (KnowledgeRepoLink) since
    the field was removed from KnowledgeItem.
    """
    from app.services.scan_helpers import merge_code_locations

    merged: dict[str, list[str]] = {}
    for item in group:
        for link in getattr(item, "repo_links", []):
            merged = merge_code_locations(merged, link.code_locations)
    return merged


def build_targeted_merge_prompt(
    groups: list[list[KnowledgeItem]],
) -> str:
    """Build a merge prompt with specific duplicate pairs and inline content.

    Pre-computes merged code_locations from source features so merged
    features are born with valid paths (Bug 4 fix).
    """
    sections: list[str] = []
    for i, group in enumerate(groups, 1):
        parts: list[str] = [f"## Merge Task {i}\n"]
        titles: list[str] = []
        for item in group:
            parts.append(f"**{item.title}**\n```\n{item.content or '(empty)'}\n```\n")
            titles.append(item.title)

        # Pre-compute merged code_locations from source features
        merged_locs = _merge_group_code_locations(group)
        parts.append(f"code_locations for write_feature_registry: {merged_locs}\n")

        parts.append("merge_source_titles for write_feature_registry: " + str(titles) + "\n")
        sections.append("\n".join(parts))

    task_block = "\n---\n".join(sections)

    return f"""You are merging overlapping features into unified descriptions.

{task_block}

## Instructions

For each merge task above:
1. Read the feature descriptions above (already provided inline)
2. Call `write_feature_registry` with:
   - feature_name: A unified name that covers the combined scope
   - description: Combined description (1-2 sentences)
   - capabilities: Merged list (deduplicate similar ones, keep up to 8)
   - code_locations: Use the pre-computed code_locations shown above for each task
   - tags: Combined and deduplicated (up to 5)
   - source_clusters: []
   - merge_source_titles: The titles listed above (deactivates the originals)"""


async def dedup_merged_features(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> int:
    """Remove duplicate feature items created by concurrent MCP calls.

    Claude CLI may retry ``write_feature_registry`` if the MCP bridge is slow,
    creating multiple items with the same title.  This keeps the newest item
    (highest id) and deactivates the rest.

    Returns:
        Number of duplicates deactivated.
    """
    # Find titles with multiple active items
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    dup_titles = await ki_repo.find_duplicate_titles("feature_registry")
    if not dup_titles:
        return 0

    total_deactivated = 0
    for title, _cnt in dup_titles:
        # Get all active items with this title, ordered by creation (newest first)
        item_ids = await ki_repo.get_ids_by_title_ordered(title, "feature_registry")
        if len(item_ids) < 2:
            continue

        # Keep the newest, transfer repo links from duplicates, then deactivate
        keep_id = item_ids[0]
        remove_ids = item_ids[1:]
        await ki_repo.transfer_repo_links(remove_ids, keep_id)
        total_deactivated += await ki_repo.bulk_deactivate_by_ids(remove_ids)
        logger.info(
            "dedup_merged_feature",
            title=title,
            kept=str(keep_id),
            removed=len(remove_ids),
        )

    if total_deactivated:
        await db.flush()
    return total_deactivated
