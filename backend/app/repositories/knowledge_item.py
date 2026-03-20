"""KnowledgeItem data access repository.

Handles feature registry CRUD, pgvector semantic search, bulk operations,
and deduplication queries.
"""

import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, text
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem
from app.repositories.base import BaseRepository


class KnowledgeItemRepository(BaseRepository[KnowledgeItem]):
    """Repository for KnowledgeItem queries, scoped to an organization.

    Handles feature registry CRUD, pgvector semantic search, bulk operations,
    and deduplication queries.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(KnowledgeItem, db, org_id=org_id)

    # --- Single-item lookup ---

    async def get_active_by_id(self, item_id: uuid.UUID) -> KnowledgeItem | None:
        """Fetch a single active knowledge item by ID within the org.

        Args:
            item_id: The item UUID.

        Returns:
            The matching KnowledgeItem or None.
        """
        result = await self._db.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.id == item_id,
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # --- Listing & filtering ---

    async def list_active(
        self,
        *,
        category: str | None = None,
        repo_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[KnowledgeItem]:
        """List active knowledge items, optionally filtered by category and repo.

        Args:
            category: Optional category filter.
            repo_id: Optional tracked repository filter.
            limit: Maximum number of results.

        Returns:
            List of active KnowledgeItem instances ordered by updated_at desc.
        """
        stmt = self._scoped(
            select(KnowledgeItem)
            .where(KnowledgeItem.is_active.is_(True))
            .order_by(KnowledgeItem.updated_at.desc())
            .limit(limit)
        )
        if category:
            stmt = stmt.where(KnowledgeItem.category == category)
        if repo_id:
            stmt = stmt.where(KnowledgeItem.repo_id == repo_id)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_category(self) -> dict[str, int]:
        """Count active items grouped by category.

        Returns:
            Dict mapping category name to count.
        """
        result = await self._db.execute(
            select(KnowledgeItem.category, func.count(KnowledgeItem.id))
            .where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
            )
            .group_by(KnowledgeItem.category)
        )
        return dict(result.all())

    async def count_embedded(self) -> int:
        """Count active items that have embeddings.

        Returns:
            Number of active items with non-null embeddings.
        """
        result = await self._db.execute(
            select(func.count(KnowledgeItem.id)).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.embedding.is_not(None),
            )
        )
        return result.scalar() or 0

    async def count_active(
        self,
        *,
        category: str | None = None,
        source: str | None = None,
    ) -> int:
        """Count active items with optional category and source filters.

        Args:
            category: Optional category filter.
            source: Optional source filter.

        Returns:
            Count of matching active items.
        """
        stmt = select(func.count(KnowledgeItem.id)).where(
            KnowledgeItem.org_id == self._org_id,
            KnowledgeItem.is_active.is_(True),
        )
        if category:
            stmt = stmt.where(KnowledgeItem.category == category)
        if source:
            stmt = stmt.where(KnowledgeItem.source == source)
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def has_any(
        self,
        *,
        source: str | None = None,
        is_active: bool = True,
    ) -> bool:
        """Check if any matching items exist.

        Args:
            source: Optional source filter.
            is_active: Filter by active status.

        Returns:
            True if at least one matching item exists.
        """
        stmt = select(KnowledgeItem.id).where(
            KnowledgeItem.org_id == self._org_id,
        )
        if is_active is not None:
            stmt = stmt.where(KnowledgeItem.is_active.is_(is_active))
        if source:
            stmt = stmt.where(KnowledgeItem.source == source)
        stmt = stmt.limit(1)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    # --- Semantic search (pgvector) ---

    async def semantic_search(
        self,
        vector: list[float],
        *,
        category: str | None = None,
        limit: int = 10,
    ) -> list[tuple[KnowledgeItem, float]]:
        """Search items by cosine similarity to a query vector.

        Args:
            vector: The query embedding vector.
            category: Optional category filter.
            limit: Maximum number of results.

        Returns:
            List of (KnowledgeItem, distance) tuples ordered by distance.
        """
        stmt = (
            select(
                KnowledgeItem,
                KnowledgeItem.embedding.cosine_distance(vector).label("distance"),
            )
            .where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.embedding.is_not(None),
            )
            .order_by("distance")
            .limit(limit)
        )
        if category:
            stmt = stmt.where(KnowledgeItem.category == category)
        result = await self._db.execute(stmt)
        return list(result.all())

    async def find_nearest_by_status(
        self,
        vector: list[float],
        *,
        category: str,
        statuses: list[str],
        limit: int = 1,
    ) -> list[tuple[KnowledgeItem, float]]:
        """Find nearest items filtered by feature_status.

        Args:
            vector: The query embedding vector.
            category: Category filter.
            statuses: List of feature_status values to match.
            limit: Maximum number of results.

        Returns:
            List of (KnowledgeItem, distance) tuples.
        """
        stmt = (
            select(
                KnowledgeItem,
                KnowledgeItem.embedding.cosine_distance(vector).label("distance"),
            )
            .where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.category == category,
                KnowledgeItem.feature_status.in_(statuses),
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.embedding.is_not(None),
            )
            .order_by("distance")
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.all())

    # --- Upsert patterns ---

    async def get_by_title_and_category(
        self,
        title: str,
        category: str,
    ) -> KnowledgeItem | None:
        """Fetch an item by exact title and category within the org.

        Args:
            title: The item title.
            category: The item category.

        Returns:
            The matching KnowledgeItem or None.
        """
        result = await self._db.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.title == title,
                KnowledgeItem.category == category,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_source_ref_and_category(
        self,
        source_ref: str,
        category: str,
    ) -> KnowledgeItem | None:
        """Fetch an item by source_ref and category within the org.

        Args:
            source_ref: The source reference string.
            category: The item category.

        Returns:
            The matching KnowledgeItem or None.
        """
        result = await self._db.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.source_ref == source_ref,
                KnowledgeItem.category == category,
            )
        )
        return result.scalar_one_or_none()

    # --- Bulk operations ---

    async def bulk_deactivate_by_titles(
        self,
        titles: list[str],
        category: str,
    ) -> int:
        """Deactivate active items matching any of the given titles.

        Args:
            titles: List of titles to match.
            category: Category filter.

        Returns:
            Number of rows updated.
        """
        if not titles:
            return 0
        result = await self._db.execute(
            sql_update(KnowledgeItem)
            .where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.category == category,
                KnowledgeItem.title.in_(titles),
                KnowledgeItem.is_active.is_(True),
            )
            .values(is_active=False, embedding=None)
        )
        return result.rowcount

    async def bulk_deactivate_by_ids(self, ids: list[uuid.UUID]) -> int:
        """Deactivate items by their IDs.

        Args:
            ids: List of item UUIDs to deactivate.

        Returns:
            Number of rows updated.
        """
        if not ids:
            return 0
        result = await self._db.execute(
            sql_update(KnowledgeItem)
            .where(KnowledgeItem.id.in_(ids))
            .values(is_active=False, embedding=None)
        )
        return result.rowcount

    async def delete_by_category_excluding_source(
        self,
        category: str,
        *,
        exclude_source: str | None = None,
    ) -> int:
        """Hard-delete items in a category, optionally excluding a source.

        Args:
            category: Category to delete from.
            exclude_source: Source value to exclude from deletion.

        Returns:
            Number of rows deleted.
        """
        stmt = sql_delete(KnowledgeItem).where(
            KnowledgeItem.org_id == self._org_id,
            KnowledgeItem.category == category,
        )
        if exclude_source:
            stmt = stmt.where(KnowledgeItem.source != exclude_source)
        result = await self._db.execute(stmt)
        return result.rowcount

    async def delete_inactive_by_category(self, category: str) -> int:
        """Hard-delete inactive items in a category.

        Args:
            category: Category to clean up.

        Returns:
            Number of rows deleted.
        """
        result = await self._db.execute(
            sql_delete(KnowledgeItem).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.category == category,
                KnowledgeItem.is_active.is_(False),
            )
        )
        return result.rowcount

    # --- Title/prefix queries ---

    async def list_titles_with_prefix(self, like_pattern: str) -> list[str]:
        """Fetch titles matching a LIKE pattern.

        Args:
            like_pattern: SQL LIKE pattern (e.g. ``'[%]%'``).

        Returns:
            List of matching title strings.
        """
        result = await self._db.execute(
            select(KnowledgeItem.title).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.title.like(like_pattern),
            )
        )
        return [row[0] for row in result.all()]

    async def list_prefixed_features(self, like_pattern: str) -> list[KnowledgeItem]:
        """Fetch active feature_registry items matching a title LIKE pattern.

        Args:
            like_pattern: SQL LIKE pattern (e.g. ``'[%] Feature:%'``).

        Returns:
            List of matching KnowledgeItem instances.
        """
        result = await self._db.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.category == "feature_registry",
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.title.like(like_pattern),
            )
        )
        return list(result.scalars().all())

    # --- Repo-level counts ---

    async def count_by_title_prefix(self, prefix: str) -> int:
        """Count active items whose title starts with a given prefix.

        Args:
            prefix: Title prefix to match (e.g. ``'[my-repo]'``).

        Returns:
            Number of matching active items.
        """
        result = await self._db.execute(
            select(func.count(KnowledgeItem.id)).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.title.like(f"{prefix}%"),
            )
        )
        return result.scalar() or 0

    async def count_features_by_title_prefix(self, prefix: str) -> int:
        """Count active feature_registry items whose title starts with a prefix.

        Args:
            prefix: Title prefix to match.

        Returns:
            Number of matching feature_registry items.
        """
        result = await self._db.execute(
            select(func.count(KnowledgeItem.id)).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.category == "feature_registry",
                KnowledgeItem.title.like(f"{prefix}%"),
            )
        )
        return result.scalar() or 0

    # --- Repo-linked counts ---

    async def count_by_repo_id(
        self,
        repo_id: uuid.UUID,
        *,
        category: str | None = None,
    ) -> int:
        """Count active items linked to a specific tracked repository.

        Args:
            repo_id: The tracked repository UUID.
            category: Optional category filter.

        Returns:
            Count of matching active items.
        """
        stmt = select(func.count(KnowledgeItem.id)).where(
            KnowledgeItem.org_id == self._org_id,
            KnowledgeItem.is_active.is_(True),
            KnowledgeItem.repo_id == repo_id,
        )
        if category:
            stmt = stmt.where(KnowledgeItem.category == category)
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    # --- Deduplication ---

    async def find_duplicate_titles(self, category: str) -> list[tuple[str, int]]:
        """Find titles with multiple active items.

        Args:
            category: Category to check.

        Returns:
            List of (title, count) tuples for duplicated titles.
        """
        stmt = (
            select(
                KnowledgeItem.title,
                func.count(KnowledgeItem.id).label("cnt"),
            )
            .where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.category == category,
                KnowledgeItem.is_active.is_(True),
            )
            .group_by(KnowledgeItem.title)
            .having(func.count(KnowledgeItem.id) > 1)
        )
        return list((await self._db.execute(stmt)).all())

    async def get_ids_by_title_ordered(
        self,
        title: str,
        category: str,
    ) -> list[uuid.UUID]:
        """Get item IDs for a title, newest first.

        Args:
            title: The title to match.
            category: Category filter.

        Returns:
            List of UUIDs ordered by created_at descending.
        """
        result = await self._db.execute(
            select(KnowledgeItem.id)
            .where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.category == category,
                KnowledgeItem.title == title,
                KnowledgeItem.is_active.is_(True),
            )
            .order_by(KnowledgeItem.created_at.desc())
        )
        return [row[0] for row in result.all()]

    async def find_semantic_duplicates(
        self,
        category: str,
        threshold: float = 0.92,
    ) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
        """Find pairs of items with high cosine similarity.

        Uses raw SQL for the pgvector self-join cosine distance operation.

        Args:
            category: Category to search within.
            threshold: Minimum cosine similarity (0-1) to consider a match.

        Returns:
            List of (id_a, id_b, similarity) tuples.
        """
        stmt = text("""
            SELECT a.id AS a_id, b.id AS b_id,
                   1 - (a.embedding <=> b.embedding) AS similarity
            FROM knowledge_items a
            JOIN knowledge_items b ON a.id < b.id
            WHERE a.org_id = :org_id AND b.org_id = :org_id
              AND a.category = :category
              AND b.category = :category
              AND a.is_active = true AND b.is_active = true
              AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
              AND (a.embedding <=> b.embedding) < :max_distance
        """)
        rows = (
            await self._db.execute(
                stmt,
                {
                    "org_id": str(self._org_id),
                    "category": category,
                    "max_distance": 1.0 - threshold,
                },
            )
        ).all()
        return [(a_id, b_id, sim) for a_id, b_id, sim in rows]

    async def get_by_ids(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, KnowledgeItem]:
        """Fetch multiple items by their IDs.

        Args:
            ids: Set of UUIDs to fetch.

        Returns:
            Dict mapping UUID to KnowledgeItem.
        """
        if not ids:
            return {}
        result = await self._db.execute(select(KnowledgeItem).where(KnowledgeItem.id.in_(ids)))
        return {i.id: i for i in result.scalars()}

    # --- Embedding ---

    async def list_missing_embeddings(self) -> list[KnowledgeItem]:
        """Fetch active items that are missing embeddings.

        Returns:
            List of KnowledgeItem instances without embeddings.
        """
        result = await self._db.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.embedding.is_(None),
            )
        )
        return list(result.scalars().all())

    # --- Stale cleanup ---

    async def list_active_items(self) -> list[KnowledgeItem]:
        """Fetch all active items for the organization.

        Returns:
            List of all active KnowledgeItem instances.
        """
        result = await self._db.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.is_active.is_(True),
            )
        )
        return list(result.scalars().all())
