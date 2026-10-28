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

"""``GET /jobs/{id}/status`` and ``POST /jobs/{id}/cancel`` over HTTP.

The jobs router runs on its own app with the signed-in user overridden;
the job store is an empty private copy per test.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.jobs import router
from app.core.deps import get_current_user
from app.schemas.jobs import JobState
from app.services import job_queue
from tests.services.job_queue_support import QueueSpy, fresh_queue

JOB = "test_job"
ORG = uuid.uuid4()


async def _noop(job_id: str, payload: dict[str, Any]) -> None:
    return None


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> QueueSpy:
    spy = fresh_queue(monkeypatch)
    job_queue.register_job_type(JOB, _noop)
    return spy


@pytest.fixture
def client(spy: QueueSpy) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/jobs")
    user = MagicMock(id=uuid.uuid4(), org_id=ORG, email="ana@acme.dev")
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as c:
        yield c


def _job(**payload: Any) -> str:
    return job_queue.create_job(JOB, payload={"org_id": str(ORG), **payload}).job_id


def test_status_returns_camel_case_job(client: TestClient) -> None:
    """A queued job is served with the API's camelCase field names."""
    job_id = _job()
    job_queue.update_job(job_id, progress_pct=30, status_message="Reading repo")

    body = client.get(f"/api/v1/jobs/{job_id}/status").json()

    assert body["jobId"] == job_id
    assert (body["state"], body["progressPct"], body["statusMessage"]) == (
        "queued",
        30,
        "Reading repo",
    )


@pytest.mark.parametrize("method", ["get", "post"])
def test_unknown_job_is_404(client: TestClient, method: str) -> None:
    """Both routes answer 404 for an id that isn't in the store."""
    path = "status" if method == "get" else "cancel"
    response = client.request(method.upper(), f"/api/v1/jobs/{uuid.uuid4()}/{path}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_cancel_queued_job_marks_it_cancelled_with_who(client: TestClient) -> None:
    """Cancelling a job no worker picked up yet flips it straight to cancelled."""
    job_id = _job()

    body = client.post(f"/api/v1/jobs/{job_id}/cancel").json()

    assert body["state"] == "cancelled"
    assert body["error"] == "Cancelled by ana@acme.dev"


@pytest.mark.parametrize("state", [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED])
def test_cancel_of_finished_job_returns_it_unchanged(
    client: TestClient, spy: QueueSpy, state: JobState
) -> None:
    """A second cancel, or one after the job ended, is a harmless no-op."""
    job_id = _job()
    job_queue.update_job(job_id, state=state, error="original")
    published = len(spy.published)

    body = client.post(f"/api/v1/jobs/{job_id}/cancel").json()

    assert (body["state"], body["error"]) == (state.value, "original")
    assert len(spy.published) == published
