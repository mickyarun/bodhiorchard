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

"""``deactivated_at_sha`` plumbing through repository + reconciler.

Scope: verify that
1. ``FeatureRepository.mark_inactive`` accepts a ``head_sha`` kwarg and
   stamps it on the row.
2. ``FeatureRepository.revive`` clears ``deactivated_at_sha`` back to
   ``NULL`` alongside the ``deactivated_at`` clear.
3. ``feature_reconciler.reconcile_features_for_repo`` forwards the
   pass-in ``head_sha`` to ``mark_inactive`` (so the new column is
   actually populated on the PR-merge path).

These are unit tests over the SQL ``UPDATE`` values we construct — no
real DB. The end-to-end correctness is covered by the smoke harness.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.repositories.feature import FeatureRepository
from app.services import feature_reconciler


@dataclass
class _RecordedExec:
    """Captured ``db.execute`` invocation."""

    statement: Any


class _FakeSession:
    """Async session double that records every ``execute`` call."""

    def __init__(self) -> None:
        self.calls: list[_RecordedExec] = []

    async def execute(self, statement: Any) -> Any:
        self.calls.append(_RecordedExec(statement=statement))

        class _Result:
            rowcount = 1

        return _Result()


def _values_of(statement: Any) -> dict[str, Any]:
    """Pull the ``.values()`` payload out of a SQLAlchemy UPDATE statement.

    SQLAlchemy stores literals as ``BindParameter`` objects; unwrap to
    the underlying Python value so tests can compare ``is False`` etc.
    """
    out: dict[str, Any] = {}
    for k, v in statement._values.items():
        key = k.key if hasattr(k, "key") else k
        out[key] = v.value if hasattr(v, "value") else v
    return out


async def test_mark_inactive_stamps_head_sha() -> None:
    session = _FakeSession()
    repo = FeatureRepository(session, org_id=uuid.uuid4())  # type: ignore[arg-type]

    feature_id = uuid.uuid4()
    rows = await repo.mark_inactive([feature_id], head_sha="abc123def")

    assert rows == 1
    assert len(session.calls) == 1
    values = _values_of(session.calls[0].statement)
    assert values["is_active"] is False
    assert values["deactivated_at_sha"] == "abc123def"
    assert "deactivated_at" in values  # timestamp also stamped


async def test_mark_inactive_no_sha_leaves_column_null() -> None:
    """BUD-lifecycle path passes no SHA — column must be NULL."""
    session = _FakeSession()
    repo = FeatureRepository(session, org_id=uuid.uuid4())  # type: ignore[arg-type]
    await repo.mark_inactive([uuid.uuid4()])

    values = _values_of(session.calls[0].statement)
    assert values["deactivated_at_sha"] is None


async def test_revive_clears_deactivated_at_sha() -> None:
    session = _FakeSession()
    repo = FeatureRepository(session, org_id=uuid.uuid4())  # type: ignore[arg-type]
    await repo.revive(uuid.uuid4(), last_seen_sha="newhead")

    values = _values_of(session.calls[0].statement)
    assert values["is_active"] is True
    assert values["deactivated_at"] is None
    assert values["deactivated_at_sha"] is None
    assert values["last_seen_sha"] == "newhead"


class _FakeFeatureRepo:
    """Captures ``mark_inactive`` invocations from the reconciler."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    async def mark_inactive(
        self, ids: list[uuid.UUID], *, head_sha: str | None = None
    ) -> int:
        self.calls.append({"ids": list(ids), "head_sha": head_sha})
        return len(ids)


class _FakeReads:
    """Returns a fixed candidate list from ``bulk_load_for_reconcile``."""

    def __init__(self, candidates: list[feature_reconciler.ReconcilerCandidate]) -> None:
        self._candidates = candidates

    async def bulk_load_for_reconcile(
        self, _repo_id: uuid.UUID, *, include_inactive: bool = True
    ) -> list[feature_reconciler.ReconcilerCandidate]:
        return list(self._candidates)


class _NoopSession:
    async def execute(self, *_a: Any, **_kw: Any) -> Any:
        return None


def _make_candidate(
    *, signature: str, is_active: bool = True
) -> feature_reconciler.ReconcilerCandidate:
    return feature_reconciler.ReconcilerCandidate(
        feature_id=uuid.uuid4(),
        feature_title=f"feat-{signature}",
        cluster_signature=signature,
        code_locations={"frontend": [f"{signature}.ts"]},
        embedding=None,
        is_active=is_active,
        tags=[],
    )


async def test_reconciler_forwards_head_sha_to_mark_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive ``reconcile_features_for_repo`` with one unmatched active
    candidate and assert the resulting ``mark_inactive`` call carries
    ``head_sha`` from the parent invocation.
    """
    fake_repo = _FakeFeatureRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([_make_candidate(signature="sig-orphan")]),
    )

    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEADSHA1",
        synthesised=[],  # no writes -> the one candidate is "unmatched active"
    )

    assert result.inactivated == 1
    assert len(fake_repo.calls) == 1
    assert fake_repo.calls[0]["head_sha"] == "HEADSHA1"


async def test_candidate_filter_keeps_out_of_scope_features_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PR-merge narrow path passes a filter scoping the reconcile
    pool to features whose signature is in the affected set. Features
    outside the scope must NOT be inactivated even though they have no
    matching ``FeatureWrite`` in the synthesis batch.
    """
    in_scope_orphan = _make_candidate(signature="sig-in-scope")
    out_of_scope = _make_candidate(signature="sig-out-of-scope")

    fake_repo = _FakeFeatureRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([in_scope_orphan, out_of_scope]),
    )

    affected = {"sig-in-scope"}
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-NARROW",
        synthesised=[],
        candidate_filter=lambda c: c.cluster_signature in affected,
    )

    assert result.inactivated == 1
    # Exactly one mark_inactive call, scoped to the in-scope row only.
    assert len(fake_repo.calls) == 1
    assert fake_repo.calls[0]["ids"] == [in_scope_orphan.feature_id]
    assert fake_repo.calls[0]["head_sha"] == "HEAD-NARROW"


async def test_candidate_filter_none_preserves_default_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No filter → both unmatched active candidates inactivate, matching
    today's full-scan reconciler contract.
    """
    orphan_a = _make_candidate(signature="sig-a")
    orphan_b = _make_candidate(signature="sig-b")

    fake_repo = _FakeFeatureRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([orphan_a, orphan_b]),
    )

    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-FULL",
        synthesised=[],
    )

    assert result.inactivated == 2
    assert sorted(fake_repo.calls[0]["ids"]) == sorted([orphan_a.feature_id, orphan_b.feature_id])
