# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Load ``seed_data.json`` into the sandbox's ``xlm_*`` tables.

The loader is idempotent: it creates tables if missing, truncates the
sandbox tables, and inserts fresh rows from the JSON fixture. Designed
so a single ``run.py load`` call returns the sandbox to a known
starting state regardless of whatever the previous run left behind.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from experiments.cross_layer_merge.schema import (
    XLMBase,
    XLMKnowledgeItem,
    XLMKnowledgeRepoLink,
    XLMPairLog,
    XLMPairPlan,
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)

log = structlog.get_logger(__name__)

SEED_PATH = Path(__file__).parent / "seed_data.json"


async def ensure_tables() -> None:
    """Create xlm_* tables if missing. Safe to call repeatedly."""
    async with engine.begin() as conn:
        await conn.run_sync(XLMBase.metadata.create_all)


async def truncate_all() -> None:
    """Wipe sandbox tables so a fresh load starts from clean state."""
    async with AsyncSessionLocal() as session:
        # Order matters: child rows first because of FKs.
        for model in (
            XLMPairLog,
            XLMPairPlan,
            XLMKnowledgeRepoLink,
            XLMSynthesizedFeature,
            XLMKnowledgeItem,
            XLMTrackedRepo,
        ):
            await session.execute(delete(model))
        await session.commit()


def _to_uuid(raw: str | None) -> uuid.UUID | None:
    return uuid.UUID(raw) if raw else None


async def load_from_json(path: Path = SEED_PATH) -> dict[str, int]:
    """Read the seed file and INSERT its rows into the sandbox tables.

    Returns a count summary so the CLI can confirm what landed.
    """
    payload: dict[str, Any] = json.loads(path.read_text())
    counts: dict[str, int] = {}

    async with AsyncSessionLocal() as session:
        for row in payload.get("tracked_repos", []):
            session.add(
                XLMTrackedRepo(
                    id=_to_uuid(row["id"]),
                    org_id=_to_uuid(row["org_id"]),
                    name=row["name"],
                    path=row.get("path"),
                )
            )
        counts["tracked_repos"] = len(payload.get("tracked_repos", []))
        await session.flush()  # parents must exist before child inserts reference them

        for row in payload.get("knowledge_items", []):
            session.add(
                XLMKnowledgeItem(
                    id=_to_uuid(row["id"]),
                    org_id=_to_uuid(row["org_id"]),
                    category=row.get("category", "feature_registry"),
                    title=row["title"],
                    content=row.get("content"),
                    tags=row.get("tags"),
                    embedding=row.get("embedding"),
                    is_active=row.get("is_active", True),
                    source_ref=row.get("source_ref"),
                )
            )
        counts["knowledge_items"] = len(payload.get("knowledge_items", []))
        await session.flush()

        for row in payload.get("knowledge_to_repo", []):
            session.add(
                XLMKnowledgeRepoLink(
                    knowledge_id=_to_uuid(row["knowledge_id"]),
                    repo_id=_to_uuid(row["repo_id"]),
                    code_locations=row.get("code_locations"),
                )
            )
        counts["knowledge_to_repo"] = len(payload.get("knowledge_to_repo", []))
        await session.flush()

        for row in payload.get("synthesized_features", []):
            session.add(
                XLMSynthesizedFeature(
                    id=_to_uuid(row["id"]),
                    scan_id=_to_uuid(row["scan_id"]),
                    org_id=_to_uuid(row["org_id"]),
                    repo_id=_to_uuid(row["repo_id"]),
                    feature_title=row["feature_title"],
                    description=row["description"],
                    capabilities=row.get("capabilities", {}),
                    cluster_names=row.get("cluster_names", []),
                    tags=row.get("tags", []),
                    code_locations=row.get("code_locations", {}),
                    embedding=row.get("embedding"),
                    knowledge_item_id=_to_uuid(row.get("knowledge_item_id")),
                    merge_outcome=row.get("merge_outcome"),
                    merged_into_id=_to_uuid(row.get("merged_into_id")),
                )
            )
        counts["synthesized_features"] = len(payload.get("synthesized_features", []))

        await session.commit()

    log.info("seed.loaded", counts=counts, source=str(path))
    return counts


async def reset_and_load() -> dict[str, int]:
    """End-to-end load: ensure schema, wipe rows, insert fresh seed."""
    await ensure_tables()
    await truncate_all()
    return await load_from_json()
