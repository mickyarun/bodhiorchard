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

"""The in-memory job store without workers: ids, backpressure, updates, TTL."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from app.schemas.jobs import JobState
from app.services import job_queue
from tests.services.job_queue_support import QueueSpy, fresh_queue

JOB = "test_job"


async def _noop(job_id: str, payload: dict[str, Any]) -> None:
    return None


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> QueueSpy:
    spy = fresh_queue(monkeypatch)
    job_queue.register_job_type(JOB, _noop, queue_maxsize=3)
    return spy


def test_new_job_is_queued(spy: QueueSpy) -> None:
    """create_job returns a QUEUED status that get_job then serves."""
    job = job_queue.create_job(JOB, payload={"a": 1})
    assert job.state == JobState.QUEUED
    assert job_queue.get_job(job.job_id) is job


def test_unknown_job_type_is_refused(spy: QueueSpy) -> None:
    with pytest.raises(ValueError, match="Unknown job type"):
        job_queue.create_job("not_registered", payload={})


@pytest.mark.parametrize("job_id", ["", "   "])
def test_blank_job_id_is_refused(spy: QueueSpy, job_id: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        job_queue.create_job_with_id(job_id, JOB, payload={})


def test_reused_job_id_is_refused_and_original_kept(spy: QueueSpy) -> None:
    """A duplicate id must not clobber the in-flight entry."""
    job_queue.create_job_with_id("chat-1", JOB, payload={"v": 1})
    with pytest.raises(ValueError, match="already in use"):
        job_queue.create_job_with_id("chat-1", JOB, payload={"v": 2})
    assert job_queue._job_store["chat-1"].payload == {"v": 1}


def test_full_queue_applies_backpressure(spy: QueueSpy) -> None:
    """Past ``queue_maxsize`` the caller gets QueueFull (the API's 503)."""
    for _ in range(3):
        job_queue.create_job(JOB, payload={})
    with pytest.raises(asyncio.QueueFull):
        job_queue.create_job(JOB, payload={})


def test_update_changes_only_given_fields(spy: QueueSpy) -> None:
    """Omitted fields keep their values; ``None`` clears result/error explicitly."""
    job = job_queue.create_job(JOB, payload={})
    job_queue.update_job(job.job_id, progress_pct=40, result={"x": 1}, error="e")
    job_queue.update_job(job.job_id, status_message="half way")
    after = job_queue.get_job(job.job_id)
    assert after is not None
    assert (after.progress_pct, after.result, after.error) == (40, {"x": 1}, "e")
    job_queue.update_job(job.job_id, result=None, error=None)
    assert (after.result, after.error, after.status_message) == (None, None, "half way")


def test_update_of_unknown_job_is_ignored(spy: QueueSpy) -> None:
    job_queue.update_job("ghost", state=JobState.FAILED)
    assert spy.published == []


def test_failed_job_without_owner_sends_no_notification(spy: QueueSpy) -> None:
    job = job_queue.create_job(JOB, payload={"org_id": "o"})
    job_queue.update_job(job.job_id, state=JobState.FAILED, error="boom")
    assert spy.notified == []


def test_progress_updates_do_not_notify(spy: QueueSpy) -> None:
    """Only terminal states produce a user notification."""
    job = job_queue.create_job(JOB, payload={}, user_id="u")
    job_queue.update_job(job.job_id, state=JobState.RUNNING, progress_pct=10)
    assert spy.notified == []
    job_queue.update_job(job.job_id, state=JobState.FAILED)
    assert [n["state"] for n in spy.notified] == [JobState.FAILED]
    assert spy.notified[0]["org_id"] == ""


def test_cleanup_drops_only_old_terminal_jobs(spy: QueueSpy) -> None:
    """Expired finished jobs go; running and recent ones stay."""
    ids = {name: job_queue.create_job(JOB, payload={}).job_id for name in ("old", "new", "live")}
    job_queue.update_job(ids["old"], state=JobState.COMPLETED)
    job_queue.update_job(ids["new"], state=JobState.CANCELLED)
    job_queue.update_job(ids["live"], state=JobState.RUNNING)
    long_ago = time.monotonic() - job_queue._COMPLETED_TTL - 1
    for name in ("old", "live"):
        entry = job_queue._job_store[ids[name]]
        job_queue._job_store[ids[name]] = entry._replace(created_mono=long_ago)

    assert job_queue.cleanup_completed_jobs() == 1
    assert job_queue.get_job(ids["old"]) is None
    assert job_queue.get_job(ids["new"]) is not None
    assert job_queue.get_job(ids["live"]) is not None


def test_active_lookups_ignore_terminal_and_other_types(spy: QueueSpy) -> None:
    """is_job_active matches every given payload key on live jobs of that type."""
    job = job_queue.create_job(JOB, payload={"org_id": "o", "bud_id": "b"})
    assert job_queue.is_job_active(JOB, {"org_id": "o", "bud_id": "b"})
    assert not job_queue.is_job_active(JOB, {"org_id": "o", "bud_id": "other"})
    assert not job_queue.is_job_active("other_type", {"org_id": "o"})
    job_queue.update_job(job.job_id, state=JobState.FAILED)
    assert not job_queue.is_job_active(JOB, {"org_id": "o"})
