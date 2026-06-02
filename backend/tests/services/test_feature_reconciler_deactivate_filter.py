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

"""``deactivate_filter`` plumbing — separate eviction scope from matching.

The PR-merge narrow path admits a broad set of candidates into the
matching pool (signature OR file overlap) so that legacy
stale-signature features stay match-eligible. But the broader the
matching pool, the worse it is as a deactivation pool: a feature
admitted purely via file overlap should NOT be soft-deleted just
because nothing in the synth output happens to match it.

``deactivate_filter`` lets callers pass a stricter predicate for the
inactivation sweep while keeping the matching scope wide. Default
behaviour (``deactivate_filter=None``) preserves the historical
contract.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import feature_reconciler
from app.services.feature_reconciler import ReconcilerCandidate


def _candidate(*, signature: str, is_active: bool = True) -> ReconcilerCandidate:
    return ReconcilerCandidate(
        feature_id=uuid.uuid4(),
        feature_title=f"feat-{signature}",
        cluster_signature=signature,
        code_locations={"frontend": [f"{signature}.ts"]},
        embedding=None,
        is_active=is_active,
        tags=[],
    )


class _FakeFeatureRepo:
    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.mark_inactive_calls: list[dict[str, Any]] = []

    async def mark_inactive(
        self, feature_ids: list[uuid.UUID], *, head_sha: str | None = None
    ) -> int:
        self.mark_inactive_calls.append({"ids": list(feature_ids), "head_sha": head_sha})
        return len(feature_ids)


class _FakeReads:
    def __init__(self, candidates: list[ReconcilerCandidate]) -> None:
        self._candidates = candidates

    async def bulk_load_for_reconcile(
        self, _repo_id: uuid.UUID, *, include_inactive: bool = True
    ) -> list[ReconcilerCandidate]:
        return list(self._candidates)


class _EmptyScalars:
    def all(self) -> list[Any]:
        return []


class _EmptyResult:
    """Mimics SQLAlchemy ``Result`` so the reconciler's cluster_cache
    SELECT returns an empty list and the preserved pass sees an empty
    indexed_files set."""

    rowcount = 0

    def scalars(self) -> _EmptyScalars:
        return _EmptyScalars()


class _NoopSession:
    async def execute(self, *_a: Any, **_kw: Any) -> _EmptyResult:
        return _EmptyResult()


async def test_deactivate_filter_default_matches_candidate_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``deactivate_filter`` is None, the inactivation sweep uses the
    same predicate as ``candidate_filter`` — preserving the pre-fix
    behaviour so existing full-scan and tightly-scoped callers don't
    regress.
    """
    in_pool = _candidate(signature="sig-in")
    out_of_pool = _candidate(signature="sig-out")
    fake_repo = _FakeFeatureRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([in_pool, out_of_pool]),
    )

    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD",
        synthesised=[],
        candidate_filter=lambda c: c.cluster_signature == "sig-in",
    )

    # Only the in-pool candidate is in scope (candidate_filter) and
    # unmatched (no synthesised entries) → it inactivates. The
    # out-of-pool candidate is invisible to both filters.
    assert result.inactivated == 1
    assert fake_repo.mark_inactive_calls[0]["ids"] == [in_pool.feature_id]


async def test_stricter_deactivate_filter_protects_file_overlap_only_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug-class scenario: a broader feature lands in the matching
    pool because one of its files was touched, but its own cluster
    signature is NOT in the affected set. With a signature-only
    ``deactivate_filter``, that feature must NOT be inactivated even
    though no synth output claimed it.
    """
    # Both candidates pass ``candidate_filter`` (the matching pool).
    sig_admitted = _candidate(signature="sig-affected")
    file_admitted = _candidate(signature="sig-unaffected")
    fake_repo = _FakeFeatureRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([sig_admitted, file_admitted]),
    )

    affected_signatures = {"sig-affected"}
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD",
        synthesised=[],
        # Both candidates pass the matching scope.
        candidate_filter=lambda _c: True,
        # Only signature matches can be soft-deleted.
        deactivate_filter=lambda c: c.cluster_signature in affected_signatures,
    )

    # Only the signature-admitted candidate inactivates. The
    # file-overlap-admitted one stays alive.
    assert result.inactivated == 1
    assert fake_repo.mark_inactive_calls[0]["ids"] == [sig_admitted.feature_id]


async def test_deactivate_filter_cannot_inactivate_candidates_outside_match_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``deactivate_filter`` further restricts an ALREADY-FILTERED pool —
    it cannot resurrect candidates the ``candidate_filter`` rejected.
    """
    in_pool = _candidate(signature="sig-in")
    out_of_pool = _candidate(signature="sig-out")
    fake_repo = _FakeFeatureRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([in_pool, out_of_pool]),
    )

    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD",
        synthesised=[],
        candidate_filter=lambda c: c.cluster_signature == "sig-in",
        # Deliberately tries to include the out-of-pool candidate — it
        # must still be invisible because candidate_filter ran first.
        deactivate_filter=lambda _c: True,
    )

    assert result.inactivated == 1
    assert fake_repo.mark_inactive_calls[0]["ids"] == [in_pool.feature_id]
