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

"""Unit tests for :func:`app.services.job_queue.find_active_job`.

The helper underpins the AI Editor chat panel re-entry flow: it scans
``_job_store`` for a queued/running job of a given type whose payload
matches every key in ``match_payload``. The endpoint built on top of it
is exercised in ``tests/api/v1/test_bud_chat_basic.py``; these tests
pin the store-level semantics in isolation.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from app.schemas.jobs import JobState, JobStatusRead
from app.services import job_queue
from app.services.job_queue import find_active_job


def _put(state: JobState, payload: dict[str, Any], *, job_type: str = "bud_chat") -> str:
    """Insert a synthetic entry into ``_job_store`` for the test to match against."""
    job_id = str(uuid.uuid4())
    status = JobStatusRead(
        job_id=job_id,
        job_type=job_type,
        state=state,
        status_message="",
    )
    job_queue._job_store[job_id] = job_queue._JobEntry(
        status=status,
        created_mono=time.monotonic(),
        user_id=None,
        payload=payload,
    )
    return job_id


@pytest.fixture(autouse=True)
def _isolated_store() -> Iterator[None]:
    """Snapshot + restore ``_job_store`` so tests don't bleed into each other."""
    saved = dict(job_queue._job_store)
    job_queue._job_store.clear()
    try:
        yield
    finally:
        job_queue._job_store.clear()
        job_queue._job_store.update(saved)


def test_empty_store_returns_none() -> None:
    assert find_active_job("bud_chat", {"bud_id": "x"}) is None


def test_returns_status_for_queued_match() -> None:
    job_id = _put(JobState.QUEUED, {"org_id": "o1", "bud_id": "b1", "section": "requirements_md"})
    out = find_active_job(
        "bud_chat",
        {"org_id": "o1", "bud_id": "b1", "section": "requirements_md"},
    )
    assert out is not None
    assert out.job_id == job_id
    assert out.state is JobState.QUEUED


def test_returns_status_for_running_match() -> None:
    _put(JobState.RUNNING, {"bud_id": "b1"})
    out = find_active_job("bud_chat", {"bud_id": "b1"})
    assert out is not None
    assert out.state is JobState.RUNNING


@pytest.mark.parametrize("terminal", [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED])
def test_skips_terminal_states(terminal: JobState) -> None:
    _put(terminal, {"bud_id": "b1"})
    assert find_active_job("bud_chat", {"bud_id": "b1"}) is None


def test_filters_by_job_type() -> None:
    _put(JobState.RUNNING, {"bud_id": "b1"}, job_type="design_agent")
    assert find_active_job("bud_chat", {"bud_id": "b1"}) is None


def test_partial_payload_mismatch_skipped() -> None:
    _put(JobState.RUNNING, {"org_id": "o1", "bud_id": "b1"})
    # Different bud — must not match.
    assert find_active_job("bud_chat", {"org_id": "o1", "bud_id": "b2"}) is None


def test_design_id_none_matches_none() -> None:
    """A non-design chat job carries ``design_id=None``; matching by ``None`` must hit."""
    _put(JobState.QUEUED, {"bud_id": "b1", "design_id": None, "section": "requirements_md"})
    out = find_active_job(
        "bud_chat",
        {"bud_id": "b1", "design_id": None, "section": "requirements_md"},
    )
    assert out is not None


def test_design_id_none_does_not_match_specific() -> None:
    """A non-design job (design_id=None) must not match a specific design_id query."""
    _put(JobState.QUEUED, {"bud_id": "b1", "design_id": None})
    assert find_active_job("bud_chat", {"bud_id": "b1", "design_id": "d1"}) is None


def test_specific_design_id_does_not_match_none() -> None:
    """A design-scoped job must not match a non-design (design_id=None) query."""
    _put(JobState.QUEUED, {"bud_id": "b1", "design_id": "d1"})
    assert find_active_job("bud_chat", {"bud_id": "b1", "design_id": None}) is None
