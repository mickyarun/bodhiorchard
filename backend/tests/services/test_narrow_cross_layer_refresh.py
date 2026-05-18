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

"""Cross-layer refresh helpers in ``pr_narrow_synthesis``.

Two helpers run after every narrow synth, both intentionally wrapping
their bodies in ``except (SQLAlchemyError, OSError)``: the
frontend-side ``_refresh_backend_links_post_reconcile`` and the
backend-merge-side ``_refresh_cross_layer_from_backend_merge``. The
narrower except (rather than the original ``except Exception``) means
**programmer errors propagate** — these tests pin both the happy path
(helpers run, dispatch to ``refresh_backend_links_for_features``) and
the failure-class triage (DB errors swallowed, AttributeError raises).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from app.services.scan import pr_narrow_synthesis as mod


@pytest.fixture
def captured_refresh_calls() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def _patched_refresh(
    monkeypatch: pytest.MonkeyPatch,
    captured_refresh_calls: list[dict[str, Any]],
) -> None:
    """Stub the underlying ``refresh_backend_links_for_features`` so
    the test can assert WHICH feature_ids the helper passed in.
    """

    async def _spy_refresh(_db: Any, *, org_id: uuid.UUID, feature_ids: list[uuid.UUID]) -> None:
        captured_refresh_calls.append({"org_id": org_id, "feature_ids": list(feature_ids)})

    monkeypatch.setattr(mod, "refresh_backend_links_for_features", _spy_refresh)


def _install_session_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop in a no-op AsyncSessionLocal — the helpers only pass the
    session into the (stubbed) repo factories, so a context manager
    yielding a placeholder is sufficient.
    """

    class _Ctx:
        async def __aenter__(self) -> Any:
            return object()

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(mod, "AsyncSessionLocal", lambda: _Ctx())


# --- _refresh_backend_links_post_reconcile -----------------------------------


async def test_frontend_refresh_dispatches_when_features_match(
    monkeypatch: pytest.MonkeyPatch,
    _patched_refresh: None,
    captured_refresh_calls: list[dict[str, Any]],
) -> None:
    """Happy path: matching feature_ids → refresh_backend_links_for_features called."""
    _install_session_stub(monkeypatch)
    org_id = uuid.uuid4()
    feature_ids = [uuid.uuid4(), uuid.uuid4()]

    class _FakeFeatRepo:
        def __init__(self, _db: Any, *, org_id: uuid.UUID) -> None:
            del org_id

        async def list_active_ids_by_signatures(
            self, _repo_id: uuid.UUID, _signatures: set[str], *, affected_files: set[str]
        ) -> list[uuid.UUID]:
            del affected_files
            return feature_ids

    monkeypatch.setattr(mod, "FeatureRepository", _FakeFeatRepo)

    await mod._refresh_backend_links_post_reconcile(
        org_id=org_id,
        repo_id=uuid.uuid4(),
        signatures={"sig-a"},
        affected_files={"a.py"},
    )
    assert len(captured_refresh_calls) == 1
    assert captured_refresh_calls[0]["feature_ids"] == feature_ids


async def test_frontend_refresh_short_circuits_when_no_features(
    monkeypatch: pytest.MonkeyPatch,
    _patched_refresh: None,
    captured_refresh_calls: list[dict[str, Any]],
) -> None:
    """Empty list → don't call the heavy refresh."""
    _install_session_stub(monkeypatch)

    class _FakeFeatRepo:
        def __init__(self, _db: Any, *, org_id: uuid.UUID) -> None:
            pass

        async def list_active_ids_by_signatures(
            self, _repo_id: uuid.UUID, _signatures: set[str], *, affected_files: set[str]
        ) -> list[uuid.UUID]:
            del affected_files
            return []

    monkeypatch.setattr(mod, "FeatureRepository", _FakeFeatRepo)

    await mod._refresh_backend_links_post_reconcile(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        signatures={"sig"},
        affected_files=set(),
    )
    assert captured_refresh_calls == []


async def test_frontend_refresh_skips_above_cap(
    monkeypatch: pytest.MonkeyPatch,
    _patched_refresh: None,
    captured_refresh_calls: list[dict[str, Any]],
) -> None:
    """Above the per-merge cap → skip with log; full scan heals later."""
    _install_session_stub(monkeypatch)
    too_many = [uuid.uuid4() for _ in range(mod.NARROW_BACKEND_LINK_FEATURE_CAP + 1)]

    class _FakeFeatRepo:
        def __init__(self, _db: Any, *, org_id: uuid.UUID) -> None:
            pass

        async def list_active_ids_by_signatures(
            self, _repo_id: uuid.UUID, _signatures: set[str], *, affected_files: set[str]
        ) -> list[uuid.UUID]:
            del affected_files
            return too_many

    monkeypatch.setattr(mod, "FeatureRepository", _FakeFeatRepo)

    await mod._refresh_backend_links_post_reconcile(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        signatures=set(),
        affected_files=set(),
    )
    assert captured_refresh_calls == []  # helper never invoked above the cap


async def test_frontend_refresh_swallows_sqlalchemy_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SQLAlchemyError`` is the documented swallow class — boot path
    must not abort the narrow synth if cross-layer DB writes hiccup.
    """
    _install_session_stub(monkeypatch)

    class _FailingFeatRepo:
        def __init__(self, _db: Any, *, org_id: uuid.UUID) -> None:
            pass

        async def list_active_ids_by_signatures(self, *_a: Any, **_kw: Any) -> Any:
            raise OperationalError("statement", {}, Exception("connection reset"))

    monkeypatch.setattr(mod, "FeatureRepository", _FailingFeatRepo)

    # No assertion — the test passes if no exception propagates.
    await mod._refresh_backend_links_post_reconcile(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        signatures={"sig"},
        affected_files=set(),
    )


async def test_frontend_refresh_propagates_programmer_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-DB exceptions (``AttributeError`` here) must escape so a
    refactor that breaks the helper signature fails in CI rather than
    getting silently swallowed.
    """
    _install_session_stub(monkeypatch)

    class _BuggyRepo:
        def __init__(self, _db: Any, *, org_id: uuid.UUID) -> None:
            pass

        async def list_active_ids_by_signatures(self, *_a: Any, **_kw: Any) -> Any:
            raise AttributeError("signature mismatch — pretend a future refactor broke this")

    monkeypatch.setattr(mod, "FeatureRepository", _BuggyRepo)

    with pytest.raises(AttributeError):
        await mod._refresh_backend_links_post_reconcile(
            org_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            signatures={"sig"},
            affected_files=set(),
        )


# --- _refresh_cross_layer_from_backend_merge ---------------------------------


async def test_backend_merge_refresh_skips_when_route_index_no_op(
    monkeypatch: pytest.MonkeyPatch,
    _patched_refresh: None,
    captured_refresh_calls: list[dict[str, Any]],
) -> None:
    """``index_and_cache_backend_routes`` returning 0 (non-backend repo
    OR cache hit) must short-circuit before the frontend-feature
    refresh — that work would be wasted.
    """
    _install_session_stub(monkeypatch)
    monkeypatch.setattr(mod, "index_and_cache_backend_routes", AsyncMock(return_value=0))

    await mod._refresh_cross_layer_from_backend_merge(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="any",
    )
    assert captured_refresh_calls == []


async def test_backend_merge_refresh_dispatches_to_linked_features(
    monkeypatch: pytest.MonkeyPatch,
    _patched_refresh: None,
    captured_refresh_calls: list[dict[str, Any]],
) -> None:
    """When the route cache updates AND frontend features link in,
    refresh them. This is the FT-5b live-verified happy path.
    """
    _install_session_stub(monkeypatch)
    linked_features = [uuid.uuid4(), uuid.uuid4()]

    monkeypatch.setattr(mod, "index_and_cache_backend_routes", AsyncMock(return_value=17))

    async def _stub_list(_db: Any, *, org_id: uuid.UUID, backend_repo_id: uuid.UUID) -> Any:
        del org_id, backend_repo_id
        return linked_features

    monkeypatch.setattr(mod, "list_features_with_backend_link_to", _stub_list)

    await mod._refresh_cross_layer_from_backend_merge(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD",
    )
    assert len(captured_refresh_calls) == 1
    assert captured_refresh_calls[0]["feature_ids"] == linked_features


async def test_backend_merge_refresh_skips_above_cap(
    monkeypatch: pytest.MonkeyPatch,
    _patched_refresh: None,
    captured_refresh_calls: list[dict[str, Any]],
) -> None:
    """Same cap as the frontend-side refresh — bigger sets defer to full scan."""
    _install_session_stub(monkeypatch)
    too_many = [uuid.uuid4() for _ in range(mod.NARROW_BACKEND_LINK_FEATURE_CAP + 1)]

    monkeypatch.setattr(mod, "index_and_cache_backend_routes", AsyncMock(return_value=10))

    async def _stub_list(_db: Any, *, org_id: uuid.UUID, backend_repo_id: uuid.UUID) -> Any:
        del org_id, backend_repo_id
        return too_many

    monkeypatch.setattr(mod, "list_features_with_backend_link_to", _stub_list)

    await mod._refresh_cross_layer_from_backend_merge(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD",
    )
    assert captured_refresh_calls == []
