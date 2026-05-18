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

"""Widen ``webhook_logs`` into a durable replay queue.

Adds six columns (``repo_id``, ``status``, ``attempts``, ``last_error``,
``next_attempt_at``, ``payload``) plus a partial index that drives the
picker's claim query. ``status`` uses a dedicated Postgres enum type
(``webhook_delivery_status``) to match the project's "status columns are
enums, never text" convention.

Backfill marks every existing row ``status='done'`` (those deliveries
already ran under the old in-memory dispatch path — they must not be
re-picked) and resolves ``repo_id`` from ``payload_summary->>'repo'``
where the tracked repo still exists.

Idempotent inspector pattern matches sibling migrations (``zag``, ``zam``).

Revision ID: zan_webhook_logs_replay_columns
Revises: zam_features_deactivated_at_sha
Create Date: 2026-05-12
"""

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "zan_webhook_logs_replay_columns"
down_revision: str | None = "zam_features_deactivated_at_sha"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE = "webhook_logs"
_REPLAY_INDEX = "ix_webhook_logs_replay"
_REPO_FK = "fk_webhook_logs_repo_id"
_STATUS_ENUM_NAME = "webhook_delivery_status"
_STATUS_ENUM_VALUES = ("pending", "running", "done", "failed", "skipped")


def _status_enum(create_type: bool = False) -> sa.Enum:
    """Build a fresh ``sa.Enum`` reference for the status type.

    ``create_type=False`` is the default — alembic will not auto-create
    the type when this Enum is attached to a column; we drive type
    creation explicitly via the standalone ``ENUM(...).create(bind)``
    call in :func:`upgrade`. That split lets the upgrade survive a
    partial previous run (type exists, columns don't) without raising
    on type re-creation.
    """
    return sa.Enum(*_STATUS_ENUM_VALUES, name=_STATUS_ENUM_NAME, create_type=create_type)


# (column_name, factory) — factory builds a fresh ``sa.Column`` per call
# so the same Column instance is never reused across ``op.add_column``
# invocations (sqlalchemy mutates the column on attach).
_NEW_COLUMN_FACTORIES: tuple[tuple[str, Callable[[], sa.Column]], ...] = (
    ("repo_id", lambda: sa.Column("repo_id", UUID(as_uuid=True), nullable=True)),
    (
        "status",
        lambda: sa.Column(
            "status",
            _status_enum(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    ),
    (
        "attempts",
        lambda: sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
    ),
    ("last_error", lambda: sa.Column("last_error", sa.Text, nullable=True)),
    (
        "next_attempt_at",
        lambda: sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    ),
    ("payload", lambda: sa.Column("payload", JSONB, nullable=True)),
)


def upgrade() -> None:
    """Add the replay columns + partial index + backfill historical rows."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    # Create the enum type idempotently before any column references it.
    bind.execute(
        sa.text(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{_STATUS_ENUM_NAME}') THEN "
            f"CREATE TYPE {_STATUS_ENUM_NAME} AS ENUM "
            f"({', '.join(repr(v) for v in _STATUS_ENUM_VALUES)}); "
            f"END IF; END $$;"
        )
    )

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, factory in _NEW_COLUMN_FACTORIES:
        if name not in existing_cols:
            op.add_column(_TABLE, factory())

    if "tracked_repositories" in inspector.get_table_names():
        existing_fks = {fk["name"] for fk in inspector.get_foreign_keys(_TABLE)}
        if _REPO_FK not in existing_fks:
            op.create_foreign_key(
                _REPO_FK,
                _TABLE,
                "tracked_repositories",
                ["repo_id"],
                ["id"],
                ondelete="SET NULL",
            )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _REPLAY_INDEX not in existing_indexes:
        op.create_index(
            _REPLAY_INDEX,
            _TABLE,
            ["status", "next_attempt_at"],
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        )

    _backfill_historical_rows(inspector)


def _backfill_historical_rows(inspector: "sa.engine.reflection.Inspector") -> None:
    """Mark every pre-existing row ``done`` and resolve ``repo_id`` where possible.

    Two-step:
      1. Best-effort join to ``tracked_repositories`` by ``github_repo_full_name``.
         Skipped entirely if that table doesn't exist yet (fresh DB).
      2. Catch-all: any row still ``pending`` after step 1 is forced to
         ``done`` so the picker never re-attempts it.

    Both steps are no-ops on a fresh DB (table empty), so this is safe
    to run inside the same migration on first deploy.
    """
    if "tracked_repositories" in inspector.get_table_names():
        op.execute(
            sa.text(
                """
                UPDATE webhook_logs
                SET status = 'done',
                    repo_id = tr.id
                FROM tracked_repositories tr
                WHERE webhook_logs.status = 'pending'
                  AND webhook_logs.payload_summary IS NOT NULL
                  AND tr.github_repo_full_name = webhook_logs.payload_summary->>'repo'
                """
            )
        )
    op.execute(sa.text("UPDATE webhook_logs SET status = 'done' WHERE status = 'pending'"))


def downgrade() -> None:
    """Drop everything we added. Index + FK + columns + enum type, in order."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _REPLAY_INDEX in existing_indexes:
        op.drop_index(_REPLAY_INDEX, table_name=_TABLE)

    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys(_TABLE)}
    if _REPO_FK in existing_fks:
        op.drop_constraint(_REPO_FK, _TABLE, type_="foreignkey")

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, _factory in reversed(_NEW_COLUMN_FACTORIES):
        if name in existing_cols:
            op.drop_column(_TABLE, name)

    # Drop the enum type last — must come after the column that referenced it.
    bind.execute(sa.text(f"DROP TYPE IF EXISTS {_STATUS_ENUM_NAME}"))
