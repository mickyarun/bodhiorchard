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

"""Absorbed-tier match orchestration through ``reconcile_features_for_repo``.

Covers the reverse-direction containment rescue: a re-synthesis run that
merges old narrow features into one broader new cluster. Without this
tier the old candidates would be swept inactive even though their code
is still present (now living inside the broader feature).

Two properties under test:

1. Primary absorb (1:1 inside ``_resolve_pairings``) routes through
   ``_absorb_into_existing(which_wins="new")`` — the surviving
   ``feature_id`` is preserved while title / description / embedding /
   cluster fields are refreshed from the new write.
2. Multi-absorb secondary rescue: when one new write engulfs *several*
   old candidates, the highest-scoring one becomes the primary absorbed
   match and the others are rescued from the sweep via
   ``touch_last_seen`` (no metadata change) so their ``feature_id``
   remains active.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import feature_reconciler
from app.services.feature_reconciler import FeatureWrite, ReconcilerCandidate


def _candidate(
    *,
    signature: str,
    files: list[str],
    is_active: bool = True,
    title: str | None = None,
) -> ReconcilerCandidate:
    return ReconcilerCandidate(
        feature_id=uuid.uuid4(),
        feature_title=title or f"feat-{signature}",
        cluster_signature=signature,
        code_locations={"frontend": list(files)},
        embedding=None,
        is_active=is_active,
        tags=[],
    )


def _write(
    *,
    signature: str,
    files: list[str],
    title: str = "w",
    description: str = "desc",
) -> FeatureWrite:
    return FeatureWrite(
        feature_title=title,
        description=description,
        capabilities={},
        cluster_names=["c"],
        cluster_signature=signature,
        tags=["t"],
        embedding=None,
        code_locations={"frontend": list(files)},
    )


class _StubFeature:
    """Minimal stand-in for the inserted Feature ORM row (we only need .id)."""

    def __init__(self) -> None:
        self.id = uuid.uuid4()


class _AbsorbCapturingRepo:
    """Records every repo call the reconciler makes during a scan."""

    def __init__(self) -> None:
        self.touch_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.insert_calls: list[dict[str, Any]] = []
        self.mark_inactive_calls: list[dict[str, Any]] = []

    async def touch_last_seen(self, feature_id: uuid.UUID, *, last_seen_sha: str | None) -> None:
        self.touch_calls.append({"feature_id": feature_id, "last_seen_sha": last_seen_sha})

    async def update_in_place(self, feature_id: uuid.UUID, **kw: Any) -> None:
        self.update_calls.append({"feature_id": feature_id, **kw})

    async def insert(self, **kw: Any) -> _StubFeature:
        feat = _StubFeature()
        self.insert_calls.append({"feature_id": feat.id, **kw})
        return feat

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
    """Mimics SQLAlchemy's ``ScalarResult`` for empty SELECTs."""

    def all(self) -> list[Any]:
        return []


class _EmptyResult:
    """Mimics SQLAlchemy's ``Result`` returned by ``AsyncSession.execute``.

    The reconciler's cluster_cache query path calls
    ``result.scalars().all()``; this returns an empty list so the
    file-preserved rescue pass sees an empty ``indexed_files`` set and
    cleanly skips. UPDATE / INSERT statements ignore the return value.
    """

    rowcount = 0

    def scalars(self) -> _EmptyScalars:
        return _EmptyScalars()


class _NoopSession:
    async def execute(self, *_a: Any, **_kw: Any) -> _EmptyResult:
        return _EmptyResult()


async def test_absorbed_primary_match_refreshes_metadata_under_old_feature_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Primary absorbed match calls ``update_in_place`` with the NEW write's
    fields under the OLD candidate's ``feature_id``.

    feature_id stability matters: BUDs reference features by id, so the
    old feature_id must survive the rename. But the row's title /
    description / embedding / cluster_signature should reflect the new
    write — otherwise the UI keeps showing the stale narrow title for a
    feature that's actually now a broader cluster.
    """
    fake_repo = _AbsorbCapturingRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)

    cand = _candidate(
        signature="sig-cache-svc",
        files=["cache.ts", "ttl.ts", "keys.ts"],
        title="Cache Service",
    )
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([cand]),
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
        signature="sig-caching-layer",
        files=[
            "cache.ts",
            "ttl.ts",
            "keys.ts",
            "redis.ts",
            "layer.ts",
            "invalidate.ts",
            "metrics.ts",
            "admin.ts",
        ],
        title="Caching Layer",
        description="Unified caching across services",
    )
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-ABSORB",
        synthesised=[write],
    )

    assert result.matches_by_strategy.get("absorbed") == 1
    assert result.inserted == 0
    assert result.inactivated == 0

    # update_in_place was called once, with the new write's metadata under
    # the OLD candidate's feature_id.
    assert len(fake_repo.update_calls) == 1
    call = fake_repo.update_calls[0]
    assert call["feature_id"] == cand.feature_id
    assert call["feature_title"] == "Caching Layer"
    assert call["description"] == "Unified caching across services"
    assert call["cluster_signature"] == "sig-caching-layer"
    assert call["last_seen_sha"] == "HEAD-ABSORB"

    # No conservative touch (that's containment-tier behaviour) and no
    # destructive overwrite of the junction (which would strand the old
    # candidate's file list).
    assert fake_repo.touch_calls == []
    assert len(merge_calls) == 1
    assert merge_calls[0]["feature_title"] == "Caching Layer"
    assert overwrite_calls == []


async def test_absorbed_secondary_rescue_prevents_sweep_of_extra_engulfed_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When one new write engulfs MULTIPLE old candidates, ``_resolve_pairings``
    claims at most one (the highest-scoring) as the primary absorbed match.
    The rest used to fall through to sweep — false-positive deactivation.

    Secondary rescue catches them: an unmatched-active candidate whose
    files are mostly inside any matched write gets ``touch_last_seen``
    instead of ``mark_inactive``. The candidate's feature_id stays
    active alongside the broader new feature.
    """
    fake_repo = _AbsorbCapturingRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)

    # Three narrow caching features all subsumed by one broader new cluster.
    cand_full = _candidate(
        signature="sig-cache",
        files=["cache.ts", "ttl.ts", "keys.ts"],
        title="Cache Service",
    )  # primary candidate: 100% engulfed
    cand_redis = _candidate(
        signature="sig-redis",
        files=["redis.ts", "layer.ts"],
        title="Redis Cache Backing",
    )  # secondary: 100% engulfed but lower-scored vs sig-cache by index
    cand_metrics = _candidate(
        signature="sig-metrics",
        files=["metrics.ts", "admin.ts"],
        title="Cache Metrics",
    )  # tertiary: 100% engulfed
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([cand_full, cand_redis, cand_metrics]),
    )

    async def _stub_merge(_db: Any, **_kw: Any) -> None:
        return None

    async def _stub_overwrite(_db: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feature_reconciler, "upsert_primary_merge", _stub_merge)
    monkeypatch.setattr(feature_reconciler, "upsert_primary", _stub_overwrite)

    write = _write(
        signature="sig-caching-layer",
        files=[
            "cache.ts",
            "ttl.ts",
            "keys.ts",
            "redis.ts",
            "layer.ts",
            "metrics.ts",
            "admin.ts",
            "extra1.ts",
            "extra2.ts",
        ],
        title="Caching Layer",
    )
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-MULTI",
        synthesised=[write],
    )

    # Exactly one PRIMARY absorbed (via update_in_place) and the rest
    # rescued via touch_last_seen. None swept.
    assert result.inactivated == 0
    assert fake_repo.mark_inactive_calls == []
    assert len(fake_repo.update_calls) == 1
    # All three engulfed candidates are accounted for between
    # update_in_place (primary) and touch_last_seen (secondary).
    primary_id = fake_repo.update_calls[0]["feature_id"]
    rescued_ids = {c["feature_id"] for c in fake_repo.touch_calls}
    all_engulfed_ids = {cand_full.feature_id, cand_redis.feature_id, cand_metrics.feature_id}
    assert primary_id in all_engulfed_ids
    assert rescued_ids == all_engulfed_ids - {primary_id}
    # Every touch carries the scan's head_sha so the rescued features
    # don't look stale on the next reconcile.
    assert all(call["last_seen_sha"] == "HEAD-MULTI" for call in fake_repo.touch_calls)
    # Audit-log: one 'absorbed' entry per engulfed candidate. Primary
    # records the write's title (synthesis identity); secondary records
    # the candidate's title (the row being preserved). Decisions:
    # primary='absorbed', secondary='rescued'.
    via_counts: dict[str, int] = {}
    for row in result.match_log_rows:
        via_counts[row.match_via] = via_counts.get(row.match_via, 0) + 1
    assert via_counts.get("absorbed") == 3
    decisions = [r.decision for r in result.match_log_rows if r.match_via == "absorbed"]
    assert decisions.count("absorbed") == 1
    assert decisions.count("rescued") == 2


async def test_absorbed_secondary_rescue_does_not_modify_candidate_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secondary-rescued candidates keep their original row intact.

    The narrow feature's identity (title / description / embedding /
    cluster_signature) survives the rescue — only ``last_seen_sha``
    advances. If we refreshed the row to the broader write's metadata,
    every engulfed candidate would become a duplicate of the primary,
    destroying the audit trail of which narrow features previously
    existed.
    """
    fake_repo = _AbsorbCapturingRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)

    primary_cand = _candidate(
        signature="sig-cache",
        files=["cache.ts", "ttl.ts", "keys.ts"],
        title="Cache Service",
    )
    secondary_cand = _candidate(
        signature="sig-redis",
        files=["redis.ts", "layer.ts"],
        title="Redis Backing",
    )
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([primary_cand, secondary_cand]),
    )

    async def _noop(_db: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feature_reconciler, "upsert_primary_merge", _noop)
    monkeypatch.setattr(feature_reconciler, "upsert_primary", _noop)

    write = _write(
        signature="sig-broad",
        files=[
            "cache.ts",
            "ttl.ts",
            "keys.ts",
            "redis.ts",
            "layer.ts",
            "extra1.ts",
            "extra2.ts",
            "extra3.ts",
        ],
        title="Caching Layer",
    )
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-NO-MUTATE",
        synthesised=[write],
    )

    # Neither engulfed candidate is swept — that's the rescue's whole job.
    assert result.inactivated == 0
    assert fake_repo.mark_inactive_calls == []
    # Exactly one candidate gets the metadata refresh (the primary
    # absorbed match). The other gets a conservative touch-only rescue.
    # Which-is-which depends on the UUID tiebreak inside the global
    # within-tier resolver — both edges score 1.0, both share the same
    # write index, so the deterministic tiebreak is feature_id ordering.
    # The test contract is "exactly one update + exactly one touch over
    # the two engulfed candidates", not which-one-which.
    assert len(fake_repo.update_calls) == 1
    assert len(fake_repo.touch_calls) == 1
    updated_id = fake_repo.update_calls[0]["feature_id"]
    touched_id = fake_repo.touch_calls[0]["feature_id"]
    engulfed_ids = {primary_cand.feature_id, secondary_cand.feature_id}
    assert {updated_id, touched_id} == engulfed_ids
    assert updated_id != touched_id  # never the same row both ways


# ---------------------------------------------------------------------------
# File-presence preservation pass
# ---------------------------------------------------------------------------
# The final safety net before sweep: when an unmatched-active candidate's
# files still appear in synthesis output (aggregated across all writes) at
# ≥ PRESERVED_FILE_THRESHOLD AND no other matched candidate already covers
# ≥ PRESERVED_DEDUP_JACCARD of those files, the row is kept alive via
# ``touch_last_seen`` and tagged ``match_via='preserved'``,
# ``decision='preserved'`` in the audit log.


async def test_preserved_pass_rescues_candidate_when_files_fragmented_across_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No single write engulfs ≥0.6 of the candidate (so tier 5 misses) but
    the candidate's files appear across two writes summing to ≥0.7 of its
    file set. The preserved pass should catch it.
    """
    fake_repo = _AbsorbCapturingRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)

    # Candidate: 10 files. Two new writes each pick up 4 of them alongside
    # 5 unrelated files (so each write is 9 files — smaller than cand to
    # keep absorbed tier 5 from firing, AND containment fraction 4/9=0.44
    # is below tier 3's 0.5 threshold). Neither write alone clears any tier.
    # Combined, the writes cover 8/10=0.8 of the candidate → preserved pass
    # is the only thing standing between cand and the sweep.
    cand = _candidate(
        signature="sig-old-broad",
        files=[f"x{i}.ts" for i in range(10)],
        title="Broad Feature",
    )
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([cand]),
    )

    async def _noop(_db: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feature_reconciler, "upsert_primary_merge", _noop)
    monkeypatch.setattr(feature_reconciler, "upsert_primary", _noop)

    write_a = _write(
        signature="sig-w-a",
        files=[f"x{i}.ts" for i in range(4)] + [f"new-a-{i}.ts" for i in range(5)],
        title="Write A",
    )
    write_b = _write(
        signature="sig-w-b",
        files=[f"x{i}.ts" for i in range(4, 8)] + [f"new-b-{i}.ts" for i in range(5)],
        title="Write B",
    )
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-PRESERVED",
        synthesised=[write_a, write_b],
    )

    # Candidate not swept.
    assert result.inactivated == 0
    assert fake_repo.mark_inactive_calls == []
    # Preserved via touch_last_seen (no metadata refresh).
    assert any(call["feature_id"] == cand.feature_id for call in fake_repo.touch_calls)
    assert all(call["feature_id"] != cand.feature_id for call in fake_repo.update_calls)
    # Audit-log marker present.
    preserved_rows = [
        r
        for r in result.match_log_rows
        if r.match_via == "preserved" and r.decision == "preserved"
    ]
    assert len(preserved_rows) == 1
    assert preserved_rows[0].matched_feature_id == cand.feature_id
    assert preserved_rows[0].score >= 0.7


async def test_preserved_pass_skips_when_coverage_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coverage 0.5 (under the 0.7 threshold) → not preserved, sweep fires.

    Sizing the write at 15 files (>cand's 10) skips tier-3 containment (which
    requires write < cand). Cand-side containment 5/10=0.5 is below the 0.6
    absorbed threshold, so tier 5 also skips. The preserved pass is the last
    gate; coverage 0.5 < 0.7 → the sweep proceeds.
    """
    fake_repo = _AbsorbCapturingRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)

    cand = _candidate(
        signature="sig-partial",
        files=[f"y{i}.ts" for i in range(10)],
        title="Partial Code Remaining",
    )
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([cand]),
    )

    async def _noop(_db: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feature_reconciler, "upsert_primary_merge", _noop)
    monkeypatch.setattr(feature_reconciler, "upsert_primary", _noop)

    write = _write(
        signature="sig-w",
        files=[f"y{i}.ts" for i in range(5)] + [f"new-{i}.ts" for i in range(10)],
        title="W",
    )
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-BELOW",
        synthesised=[write],
    )

    # Candidate swept because coverage < threshold.
    assert result.inactivated == 1
    assert fake_repo.mark_inactive_calls == [{"ids": [cand.feature_id], "head_sha": "HEAD-BELOW"}]
    # No preserved audit entry.
    preserved_rows = [r for r in result.match_log_rows if r.match_via == "preserved"]
    assert preserved_rows == []


def test_preserved_helper_dedup_guard_skips_candidates_owned_by_matched_feature() -> None:
    """Direct test of ``_compute_file_preserved_rescues`` dedup guard.

    The reconciler-level guard only matters for candidates that escape every
    other tier including the absorbed-secondary rescue, which is hard to set
    up via the full orchestrator (any write that engulfs a candidate at
    ≥ ABSORBED_THRESHOLD claims it via secondary absorb first). Testing the
    helper directly isolates the guard's behavior: when a candidate's files
    are ≥30% jaccard-overlapped by a candidate already in ``matched_ids``,
    the candidate must NOT be returned for preservation — the sweep should
    handle it as a duplicate.
    """
    # F_owner (matched) carries the same 5 files as F_dup (unmatched).
    # Jaccard between them is 1.0, well above PRESERVED_DEDUP_JACCARD (0.3).
    dup_files = ["a.ts", "b.ts", "c.ts", "d.ts", "e.ts"]
    cand_dup = _candidate(signature="sig-dup", files=dup_files, title="Dup")
    cand_owner = _candidate(signature="sig-own", files=dup_files, title="Owner")

    # Synthesised write reflects F_owner; F_owner is already in matched_ids.
    write = _write(signature="sig-own", files=dup_files, title="Owner write")
    matched_ids = {cand_owner.feature_id}
    pairings: list[tuple[ReconcilerCandidate | None, str, float]] = [
        (cand_owner, "signature", 1.0),
    ]

    # Pre-helper change: tests pass an empty indexed_files set so the
    # file-presence signal collapses to synthesis output (the old behaviour
    # before we added cluster_cache as a ground-truth source). That keeps
    # the assertions about coverage/dedup focused on the helper's logic
    # rather than on which data source contributed which files.
    rescues = feature_reconciler._compute_file_preserved_rescues(
        [write],
        [cand_dup, cand_owner],
        pairings,
        matched_ids,
        indexed_files=set(),
        threshold=feature_reconciler.PRESERVED_FILE_THRESHOLD,
        dedup_jaccard=feature_reconciler.PRESERVED_DEDUP_JACCARD,
    )

    # Dedup guard fires: cand_dup is NOT rescued even though file coverage
    # would be 100% — because cand_owner (already matched) carries the same
    # files. The sweep gets to handle it.
    assert rescues == []


def test_preserved_helper_dedup_guard_recognises_inserted_writes() -> None:
    """Dedup guard must also see INSERTED writes, not just matched candidates.

    If a brand-new write was inserted as a fresh feature and that write's
    file set overlaps an unmatched candidate ≥ PRESERVED_DEDUP_JACCARD, the
    candidate is a duplicate of the newly-inserted feature → not preserved.
    Without this branch a stale active row would survive alongside an
    identical newly-created row.
    """
    dup_files = ["a.ts", "b.ts", "c.ts", "d.ts", "e.ts"]
    cand_dup = _candidate(signature="sig-dup", files=dup_files, title="Dup")

    # Write is INSERTED (pairings entry: match=None, via='insert'). Its
    # file set equals cand_dup's — perfect dedup target.
    write = _write(signature="sig-new", files=dup_files, title="Fresh feature")
    pairings: list[tuple[ReconcilerCandidate | None, str, float]] = [
        (None, "insert", 0.0),
    ]

    # Pre-helper change: tests pass an empty indexed_files set so the
    # file-presence signal collapses to synthesis output (the old behaviour
    # before we added cluster_cache as a ground-truth source). That keeps
    # the assertions about coverage/dedup focused on the helper's logic
    # rather than on which data source contributed which files.
    rescues = feature_reconciler._compute_file_preserved_rescues(
        [write],
        [cand_dup],
        pairings,
        matched_ids=set(),
        indexed_files=set(),
        threshold=feature_reconciler.PRESERVED_FILE_THRESHOLD,
        dedup_jaccard=feature_reconciler.PRESERVED_DEDUP_JACCARD,
    )

    # Dedup guard sees the inserted write's footprint and skips the
    # candidate — it's a duplicate of what was just inserted.
    assert rescues == []


def test_preserved_helper_returns_candidate_when_files_fragmented_no_dup() -> None:
    """Direct positive test: candidate's files split across multiple writes,
    no matched feature owns them → rescued.
    """
    cand = _candidate(
        signature="sig-broad",
        files=[f"x{i}.ts" for i in range(10)],
        title="Broad",
    )
    # Two writes, each carrying half of cand's files plus unrelated content.
    # Neither matches cand via any single-write tier (we don't actually run
    # the resolver here — we hand the helper an empty matched_ids).
    # Each insert-write carries some of cand's files alongside many
    # unrelated ones. Each write's jaccard with cand is below the dedup
    # threshold (0.3) — so neither newly-inserted feature can be called a
    # duplicate of cand — but combined they still cover ≥0.7 of cand's
    # files. Exactly the fragmentation pattern this pass exists for.
    # write_a: 5 cand files + 8 unrelated = 13 files. jaccard with cand
    #   = 5 / (10 + 8) = 0.28 (below 0.3, no dedup).
    # write_b: 4 cand files + 8 unrelated = 12 files. jaccard with cand
    #   = 4 / (10 + 8) = 0.22 (below 0.3, no dedup).
    write_a = _write(
        signature="sig-a",
        files=[f"x{i}.ts" for i in range(5)] + [f"new-a-{i}.ts" for i in range(8)],
    )
    write_b = _write(
        signature="sig-b",
        files=[f"x{i}.ts" for i in range(5, 9)] + [f"new-b-{i}.ts" for i in range(8)],
    )
    pairings: list[tuple[ReconcilerCandidate | None, str, float]] = [
        (None, "insert", 0.0),
        (None, "insert", 0.0),
    ]

    # Pre-helper change: tests pass an empty indexed_files set so the
    # file-presence signal collapses to synthesis output (the old behaviour
    # before we added cluster_cache as a ground-truth source). That keeps
    # the assertions about coverage/dedup focused on the helper's logic
    # rather than on which data source contributed which files.
    rescues = feature_reconciler._compute_file_preserved_rescues(
        [write_a, write_b],
        [cand],
        pairings,
        matched_ids=set(),
        indexed_files=set(),
        threshold=feature_reconciler.PRESERVED_FILE_THRESHOLD,
        dedup_jaccard=feature_reconciler.PRESERVED_DEDUP_JACCARD,
    )

    assert len(rescues) == 1
    assert rescues[0][0].feature_id == cand.feature_id
    assert rescues[0][1] == pytest.approx(0.9)  # 9/10 of cand's files in writes


async def test_preserved_pass_runs_after_absorbed_so_absorbed_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pair that qualifies for BOTH absorbed-tier and file-preservation must
    claim via absorbed (richer metadata-refresh path), not via preserved.

    Without this ordering, the gentler preserved pass would silently shadow
    the absorbed tier's metadata refresh and downstream readers would see a
    stale title on the surviving row.
    """
    fake_repo = _AbsorbCapturingRepo()
    monkeypatch.setattr(feature_reconciler, "FeatureRepository", lambda *a, **k: fake_repo)

    cand = _candidate(
        signature="sig-old",
        files=["a.ts", "b.ts", "c.ts"],
        title="Old Narrow Title",
    )
    monkeypatch.setattr(
        feature_reconciler,
        "FeatureReadRepository",
        lambda *a, **k: _FakeReads([cand]),
    )

    async def _noop(_db: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feature_reconciler, "upsert_primary_merge", _noop)
    monkeypatch.setattr(feature_reconciler, "upsert_primary", _noop)

    # New write engulfs the candidate (100% containment, write strictly
    # larger): absorbed tier should claim it via update_in_place, NOT the
    # preserved pass via touch_last_seen.
    write = _write(
        signature="sig-new",
        files=["a.ts", "b.ts", "c.ts", "d.ts", "e.ts", "f.ts", "g.ts"],
        title="New Broader Title",
    )
    result = await feature_reconciler.reconcile_features_for_repo(
        db=_NoopSession(),  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD-ORDER",
        synthesised=[write],
    )

    # Absorbed primary path used → update_in_place with new metadata.
    assert len(fake_repo.update_calls) == 1
    assert fake_repo.update_calls[0]["feature_title"] == "New Broader Title"
    # No preserved audit entry (absorbed claimed it first).
    preserved_rows = [r for r in result.match_log_rows if r.match_via == "preserved"]
    assert preserved_rows == []
    # No sweep.
    assert result.inactivated == 0
