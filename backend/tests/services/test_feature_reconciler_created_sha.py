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

"""``created_at_sha`` plumbing through the reconciler's insert path.

Scope: verify that
1. ``FeatureRepository.insert`` accepts a ``created_at_sha`` kwarg and
   stamps it on the row.
2. ``feature_reconciler._insert_new`` passes the current ``head_sha``
   as ``created_at_sha`` so a newly-synthesised feature carries its
   birth SHA forward (this is what the Features API later joins
   against ``pull_requests`` to render "Created by PR #N").
3. ``_insert_new`` does NOT pass ``created_at_sha`` on the update
   path — that column is set-on-insert-only by contract.

Unit-level: monkey-patches the repo's ``insert`` method to capture the
keyword arguments rather than hitting Postgres.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.feature import Feature
from app.services import feature_reconciler


@pytest.mark.asyncio
async def test_feature_repository_insert_stamps_created_at_sha() -> None:
    """``FeatureRepository.insert`` writes ``created_at_sha`` onto the row
    so the ORM ``add`` carries it down to the INSERT statement.
    """
    from app.repositories.feature import FeatureRepository

    class _Session:
        added: list[Any] = []

        async def flush(self) -> None:
            return None

        async def refresh(self, obj: Any) -> None:
            return None

        def add(self, obj: Any) -> None:
            self.added.append(obj)

    sess = _Session()
    repo = FeatureRepository(sess, org_id=uuid.uuid4())  # type: ignore[arg-type]

    await repo.insert(
        feature_title="Test",
        description="d",
        capabilities={},
        cluster_names=["c"],
        cluster_signature="sig",
        last_seen_sha="sha-last",
        created_at_sha="sha-birth",
    )

    row = sess.added[0]
    assert isinstance(row, Feature)
    assert row.created_at_sha == "sha-birth"
    assert row.last_seen_sha == "sha-last"


@pytest.mark.asyncio
async def test_insert_new_passes_head_sha_as_created_at_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_insert_new`` must pass the in-flight ``head_sha`` as both
    ``last_seen_sha`` AND ``created_at_sha`` — the row is born at this
    SHA, and its "last touched" view starts equal to creation.
    """
    captured_kwargs: dict[str, Any] = {}

    class _StubFeatRepo:
        async def insert(self, **kw: Any) -> Any:
            captured_kwargs.update(kw)

            class _Out:
                id = uuid.uuid4()

            return _Out()

    async def _stub_upsert(_db: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feature_reconciler, "upsert_primary", _stub_upsert)

    write = feature_reconciler.FeatureWrite(
        feature_title="Brand new",
        description="desc",
        capabilities={},
        cluster_names=["c"],
        cluster_signature="sig-new",
        tags=[],
        embedding=None,
        code_locations={"backend": ["x.py"]},
        source_ref=None,
        feature_status=None,
    )

    await feature_reconciler._insert_new(
        _StubFeatRepo(),  # type: ignore[arg-type]
        db=object(),  # type: ignore[arg-type]
        repo_id=uuid.uuid4(),
        head_sha="HEADSHA",
        write=write,
    )

    assert captured_kwargs["last_seen_sha"] == "HEADSHA"
    assert captured_kwargs["created_at_sha"] == "HEADSHA"


@pytest.mark.asyncio
async def test_update_existing_does_not_pass_created_at_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_update_existing`` updates a row that already exists — its
    ``created_at_sha`` was set at insert and must NOT be overwritten on
    later reconciles. Guarding against a refactor that copy-pastes the
    insert call and accidentally clobbers the column.
    """
    captured_kwargs: dict[str, Any] = {}

    class _StubFeatRepo:
        async def update_in_place(self, _feature_id: Any, **kw: Any) -> None:
            captured_kwargs.update(kw)

    async def _stub_upsert(_db: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feature_reconciler, "upsert_primary", _stub_upsert)

    write = feature_reconciler.FeatureWrite(
        feature_title="Updated",
        description="desc",
        capabilities={},
        cluster_names=["c"],
        cluster_signature="sig",
        tags=[],
        embedding=None,
        code_locations={"backend": ["x.py"]},
        source_ref=None,
        feature_status=None,
    )

    await feature_reconciler._update_existing(
        _StubFeatRepo(),  # type: ignore[arg-type]
        db=object(),  # type: ignore[arg-type]
        feature_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEADSHA",
        write=write,
    )

    assert "created_at_sha" not in captured_kwargs
    assert captured_kwargs["last_seen_sha"] == "HEADSHA"
