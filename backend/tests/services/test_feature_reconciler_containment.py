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

"""Containment-tier matching + conservative absorb path.

Covers the bug class where a narrow PR adds a sub-component (a handful
of new files) to a broader existing feature. Previously the reconciler
would emit a new feature and soft-delete the broader one; the
containment tier now matches the synth output to the broader candidate
and ``_absorb_into_existing`` preserves its curated metadata while
expanding ``code_locations``.

Three properties under test:

1. ``_resolve_pairings`` returns ``match_via="containment"`` when the
   synth's files are mostly inside a larger candidate.
2. The containment tier does not fire when the synth side is the same
   size or larger than the candidate (no false absorbs into smaller
   features that happen to share a file).
3. ``reconcile_features_for_repo`` routes the containment match through
   ``_absorb_into_existing`` — invoking ``touch_last_seen`` and
   ``upsert_primary_merge`` rather than the destructive
   ``update_in_place`` / ``upsert_primary`` pair.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import feature_reconciler
from app.services.feature_reconciler import (
    ABSORBED_THRESHOLD,
    CONTAINMENT_THRESHOLD,
    COSINE_THRESHOLD,
    JACCARD_THRESHOLD,
    FeatureWrite,
    ReconcilerCandidate,
    _resolve_pairings,
)


def _pair_one(
    write: FeatureWrite,
    candidates: list[ReconcilerCandidate],
) -> tuple[ReconcilerCandidate | None, str, float]:
    """Run :func:`_resolve_pairings` for a single write and return its slot.

    The matcher is now global (resolves an entire batch at once), so the
    single-write tier-behavior tests below wrap the write in a one-element
    list and read pairings[0].
    """
    by_signature = {c.cluster_signature: c for c in candidates}
    pairings = _resolve_pairings(
        [write],
        candidates,
        by_signature,
        jaccard_threshold=JACCARD_THRESHOLD,
        cosine_threshold=COSINE_THRESHOLD,
        containment_threshold=CONTAINMENT_THRESHOLD,
        absorbed_threshold=ABSORBED_THRESHOLD,
    )
    return pairings[0]


def _candidate(
    *,
    signature: str,
    files: list[str],
    embedding: list[float] | None = None,
    is_active: bool = True,
    title: str | None = None,
) -> ReconcilerCandidate:
    return ReconcilerCandidate(
        feature_id=uuid.uuid4(),
        feature_title=title or f"feat-{signature}",
        cluster_signature=signature,
        code_locations={"frontend": list(files)},
        embedding=embedding,
        is_active=is_active,
        tags=[],
    )


def _write(
    *,
    signature: str,
    files: list[str],
    title: str = "narrow",
    embedding: list[float] | None = None,
) -> FeatureWrite:
    return FeatureWrite(
        feature_title=title,
        description="desc",
        capabilities={},
        cluster_names=["c"],
        cluster_signature=signature,
        tags=[],
        embedding=embedding,
        code_locations={"frontend": list(files)},
    )


def test_containment_matches_when_synth_files_are_subset_of_larger_candidate() -> None:
    """1-file PR adds a sidebar file already implied by a 5-file feature.

    Synth: ``{sidebar.vue}`` (size 1). Candidate: ``{a, b, c, d, sidebar.vue}``
    (size 5). Containment = 1/1 = 1.0; Jaccard = 1/5 = 0.2 (below 0.7);
    cosine N/A. Expect ``containment`` to win.
    """
    cand = _candidate(
        signature="sig-broad",
        files=["a.vue", "b.vue", "c.vue", "d.vue", "sidebar.vue"],
        title="Products Catalog",
    )
    write = _write(signature="sig-narrow", files=["sidebar.vue"])

    match, via, score = _pair_one(write, [cand])

    assert match is cand
    assert via == "containment"
    assert score == pytest.approx(1.0)


def test_containment_skips_when_synth_is_not_smaller() -> None:
    """Equal-size sets must NOT trigger containment.

    Containment is meant for "narrow slice absorbed into broad feature".
    An equal-size match either belongs in Jaccard (above threshold) or
    is genuinely a different feature; either way containment isn't the
    right call.
    """
    cand = _candidate(signature="sig-cand", files=["a.vue", "b.vue"])
    write = _write(signature="sig-write", files=["a.vue", "c.vue"])

    match, via, _score = _pair_one(write, [cand])

    assert match is None
    assert via == "insert"


def test_signature_match_beats_containment() -> None:
    """Signature ladder takes precedence even when containment would also fit."""
    cand = _candidate(signature="sig-shared", files=["a.vue", "b.vue", "c.vue", "d.vue"])
    write = _write(signature="sig-shared", files=["a.vue"])

    _match, via, score = _pair_one(write, [cand])

    assert via == "signature"
    assert score == pytest.approx(1.0)


def test_jaccard_match_beats_containment() -> None:
    """When Jaccard ≥ threshold and containment would also fit, Jaccard wins."""
    cand = _candidate(signature="sig-cand", files=["a.vue", "b.vue", "c.vue"])
    # Synth shares all 3 files plus 1 extra → Jaccard = 3/4 = 0.75 (≥ 0.7).
    # Containment would also match (3/4 = 0.75) — but Jaccard runs first.
    write = _write(signature="sig-write", files=["a.vue", "b.vue", "c.vue", "d.vue"])

    _match, via, _score = _pair_one(write, [cand])

    # Jaccard cares about |∩| / |∪|. Containment is asymmetric. The synth
    # is the LARGER side here, so containment is structurally disallowed
    # anyway — this also guards that branch.
    assert via == "jaccard"


def test_containment_below_threshold_falls_through_to_insert() -> None:
    """Synth files barely overlap a candidate — not enough for containment."""
    cand = _candidate(
        signature="sig-cand",
        files=["a.vue", "b.vue", "c.vue", "d.vue", "e.vue"],
    )
    # 1 of 4 synth files in candidate → containment = 0.25 < 0.5.
    write = _write(signature="sig-write", files=["a.vue", "x.vue", "y.vue", "z.vue"])

    match, via, _score = _pair_one(write, [cand])

    assert match is None
    assert via == "insert"


class _AbsorbCapturingRepo:
    """Captures conservative-update calls + the destructive ones for contrast."""

    def __init__(self) -> None:
        self.touch_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.mark_inactive_calls: list[dict[str, Any]] = []

    async def touch_last_seen(self, feature_id: uuid.UUID, *, last_seen_sha: str | None) -> None:
        self.touch_calls.append({"feature_id": feature_id, "last_seen_sha": last_seen_sha})

    async def update_in_place(self, feature_id: uuid.UUID, **kw: Any) -> None:
        self.update_calls.append({"feature_id": feature_id, **kw})

    async def mark_inactive(
        self, feature_ids: list[uuid.UUID], *, head_sha: str | None = None
    ) -> int:
        self.mark_inactive_calls.append({"ids": list(feature_ids), "head_sha": head_sha})
        return len(feature_ids)

    async def revive(self, _fid: uuid.UUID, *, last_seen_sha: str | None) -> None:
        return None


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


async def test_containment_match_routes_through_absorb_not_update_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Containment match → conservative update path used (touch_last_seen +
    upsert_primary_merge), NOT the destructive update_in_place +
    upsert_primary that overwrites the broader feature's title /
    description.
    """
    fake_repo = _AbsorbCapturingRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)

    broader = _candidate(
        signature="sig-broad",
        files=["a.vue", "b.vue", "c.vue", "sidebar.vue", "form.vue"],
        title="Products Catalog",
    )
    monkeypatch.setattr(
        feature_reconciler, "FeatureReadRepository", lambda *a, **k: _FakeReads([broader])
    )

    merge_calls: list[dict[str, Any]] = []
    overwrite_calls: list[dict[str, Any]] = []

    async def _stub_merge(_db: Any, **kw: Any) -> None:
        merge_calls.append(kw)

    async def _stub_overwrite(_db: Any, **kw: Any) -> None:
        overwrite_calls.append(kw)

    monkeypatch.setattr(feature_reconciler, "upsert_primary_merge", _stub_merge)
    monkeypatch.setattr(feature_reconciler, "upsert_primary", _stub_overwrite)

    write = _write(
        signature="sig-narrow",
        files=["sidebar.vue"],
        title="Product Details Sidebar",
    )
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-PR-3599",
        synthesised=[write],
    )

    assert result.updated == 1
    assert result.inserted == 0
    assert result.inactivated == 0
    assert result.matches_by_strategy.get("containment") == 1
    # Conservative path used, destructive path NOT used.
    assert len(fake_repo.touch_calls) == 1
    assert fake_repo.touch_calls[0]["last_seen_sha"] == "HEAD-PR-3599"
    assert fake_repo.update_calls == []
    assert len(merge_calls) == 1
    # The merging upsert carries the broader feature's existing title —
    # NOT the narrow synth output's title — into the junction so the
    # partial unique index keeps pointing at the broader row.
    assert merge_calls[0]["feature_title"] == "Products Catalog"
    assert overwrite_calls == []
