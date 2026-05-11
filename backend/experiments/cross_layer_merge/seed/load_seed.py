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

"""Load ``seed_data.json`` into the sandbox's ``xlm_*`` tables.

The loader is idempotent: it creates tables if missing, truncates the
sandbox tables, and inserts fresh rows from the JSON fixture. Designed
so a single ``run.py load`` call returns the sandbox to a known
starting state regardless of whatever the previous run left behind.

The loader writes only the **inputs** to the merge phase:
``xlm_tracked_repo`` and raw ``xlm_synth_feature`` rows with
``merge_outcome=NULL`` and ``knowledge_item_id=NULL``. The merge
runner is the sole writer of ``xlm_knowledge_item`` and
``xlm_ki_repo_link``, mirroring the production contract that
``phase_b3_merge`` is the only producer of canonical knowledge items.
Pre-promoted KI/link rows in ``seed_data.json`` are ignored.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import delete, text

from app.database import AsyncSessionLocal, engine
from experiments.cross_layer_merge.schema import (
    XLMBase,
    XLMKnowledgeItem,
    XLMKnowledgeRepoLink,
    XLMMergeLog,
    XLMPairLog,
    XLMPairPlan,
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)

# Idempotent ALTER statements that bring an existing sandbox schema up to the
# current model. ``metadata.create_all`` only creates missing tables — it does
# not add columns or enum values to tables that already exist. We run these
# every time ``ensure_tables`` is called so iterative sandbox edits don't
# require a DROP/CREATE.
_SCHEMA_MIGRATIONS: tuple[str, ...] = (
    "ALTER TYPE xlm_repo_layer ADD VALUE IF NOT EXISTS 'batch'",
    "ALTER TABLE xlm_synth_feature "
    "ADD COLUMN IF NOT EXISTS backend_repo_ids uuid[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE xlm_synth_feature "
    "ADD COLUMN IF NOT EXISTS backend_api_paths text[] NOT NULL DEFAULT '{}'",
)

log = structlog.get_logger(__name__)

SEED_PATH = Path(__file__).parent / "seed_data.json"


async def ensure_tables() -> None:
    """Create xlm_* tables if missing and apply idempotent schema migrations.

    Postgres requires ``ALTER TYPE ... ADD VALUE`` to run **outside** a
    transaction, so the enum migration uses an autocommit-isolation
    connection while the column ALTERs run in the normal transactional
    block alongside ``create_all``.
    """
    async with engine.begin() as conn:
        await conn.run_sync(XLMBase.metadata.create_all)

    # ALTER TYPE ADD VALUE must not be inside a transaction.
    async with engine.connect() as conn:
        autocommit_conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        for stmt in _SCHEMA_MIGRATIONS:
            await autocommit_conn.execute(text(stmt))


async def truncate_all() -> None:
    """Wipe sandbox tables so a fresh load starts from clean state."""
    async with AsyncSessionLocal() as session:
        # Order matters: child rows first because of FKs.
        for model in (
            XLMMergeLog,
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

        # Skip the pre-promoted ``knowledge_items`` and ``knowledge_to_repo``
        # rows in seed_data.json by design: those are merge OUTPUTS now,
        # produced by the runner. Keeping the keys ignored — not removed —
        # so the JSON fixture stays a self-contained reference of what the
        # production scan would emit on this dataset.
        counts["knowledge_items"] = 0
        counts["knowledge_to_repo"] = 0

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
                    # Synth rows arrive RAW — the merge runner is the sole
                    # writer of ``knowledge_item_id`` and ``merge_outcome``.
                    knowledge_item_id=None,
                    merge_outcome=None,
                    merged_into_id=None,
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
