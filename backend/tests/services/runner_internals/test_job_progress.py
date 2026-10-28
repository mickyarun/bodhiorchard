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

"""Job progress from a streamed agent run, and the MCP config builder.

A scripted run streams ``tool_use`` events through the real runner into
``make_progress_callback``, which rewrites the job's status and publishes it.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.mcp import auth as mcp_auth
from app.schemas.jobs import JobState
from app.services import job_queue, job_utils
from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
from tests.fakes.app_state import EventRecorder
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, Say, ToolCall


async def _noop(job_id: str, payload: dict[str, object]) -> None:
    """A registered handler that is never run (no workers are started)."""


@pytest.fixture
async def job_id(monkeypatch: pytest.MonkeyPatch, event_recorder: EventRecorder) -> str:
    """A running job in an isolated store, as a worker leaves it before the handler runs.

    No worker is started; the job is moved to RUNNING by hand and the frame
    that publishes is dropped, so tests see only what the progress callback sends.
    """
    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    job_queue.register_job_type("runner_internals_probe", _noop)
    job = job_queue.create_job("runner_internals_probe", payload={}).job_id
    job_queue.update_job(job, state=JobState.RUNNING, status_message="Starting...")
    await event_recorder.settle()
    event_recorder.events.clear()
    return job


def _messages(recorder: EventRecorder, job: str) -> list[str]:
    return [frame["statusMessage"] for frame in recorder.payloads(f"job:{job}")]


async def test_each_tool_call_in_the_stream_becomes_a_status_message(
    fake_claude: FakeClaudeRunner, event_recorder: EventRecorder, job_id: str, tmp_path: Path
) -> None:
    """Built-in and MCP tool names map to readable messages; free text does not."""
    fake_claude.enqueue(
        AgentScript.ok(
            "done",
            Say("Let me look around."),
            ToolCall("get_bud_context", {}),
            ToolCall("write_bud_design", {}),
            ToolCall("code_impact", {}),
        )
    )

    await run_claude_code(
        "p", tmp_path, ClaudeRunnerConfig(), job_utils.make_progress_callback(job_id)
    )
    await event_recorder.settle()

    assert _messages(event_recorder, job_id) == [
        "Reading BUD requirements...",
        "Saving wireframe...",
        "Using code_impact...",
    ]


@pytest.mark.parametrize(
    ("tool", "tool_input", "message"),
    [
        ("Read", {"file_path": "/repo/app/orders.py"}, "Reading orders.py..."),
        ("Edit", {}, "Editing file..."),
        ("Grep", {"pattern": "def refund"}, "Searching for 'def refund'..."),
        ("Bash", {"command": "pytest -q\nsecond line"}, "Running: pytest -q..."),
        ("mcp__bodhiorchard__list_design_systems", {}, "Discovering design systems..."),
    ],
)
async def test_tool_input_is_summarised_without_dumping_it(
    job_id: str, tool: str, tool_input: dict[str, str], message: str
) -> None:
    """File paths shrink to a basename and commands to their first line."""
    job_utils.make_progress_callback(job_id)(tool, tool_input)

    job = job_queue.get_job(job_id)
    assert job is not None and job.status_message == message


async def test_quiet_stretch_after_a_tool_flips_to_the_generating_message(
    job_id: str, event_recorder: EventRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One heartbeat after the last tool call; an earlier one is cancelled by the next call."""
    monkeypatch.setattr(job_utils, "_HEARTBEAT_DELAY_SECONDS", 0.02)
    callback = job_utils.make_progress_callback(job_id, generating_message="Drawing...")

    callback("Read", {"file_path": "a.py"})
    callback("Read", {"file_path": "b.py"})
    await asyncio.sleep(0.1)
    await event_recorder.settle()

    assert _messages(event_recorder, job_id) == [
        "Reading a.py...",
        "Reading b.py...",
        "Drawing...",
    ]


async def test_heartbeat_does_not_overwrite_a_finished_job(
    job_id: str, event_recorder: EventRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A heartbeat armed during the run stays quiet once the job is terminal."""
    monkeypatch.setattr(job_utils, "_HEARTBEAT_DELAY_SECONDS", 0.02)
    job_utils.make_progress_callback(job_id, generating_message="Drawing...")("Read", {})
    job_queue.update_job(job_id, state=JobState.COMPLETED, status_message="Done")
    await asyncio.sleep(0.1)
    await event_recorder.settle()

    job = job_queue.get_job(job_id)
    assert job is not None and job.status_message == "Done"
    assert _messages(event_recorder, job_id)[-1] == "Done"


def test_progress_for_an_unknown_job_publishes_nothing(event_recorder: EventRecorder) -> None:
    """A callback outliving its job (store cleaned up) is a silent no-op."""
    job_utils.make_progress_callback("gone")("Read", {"file_path": "a.py"})

    assert event_recorder.events == []


def test_mcp_config_carries_a_token_bound_to_the_org(monkeypatch: pytest.MonkeyPatch) -> None:
    """The built config names the backend, the tools, and a token for exactly this org."""
    org_id = uuid.uuid4()
    monkeypatch.setattr(settings, "mcp_backend_url", "http://127.0.0.1:8999")
    monkeypatch.setattr(mcp_auth, "_internal_tokens", {})

    config = job_utils.build_mcp_config(str(org_id), tool_names=["write_bud"])

    assert config is not None
    assert (config.backend_url, config.tool_names, config.org_id) == (
        "http://127.0.0.1:8999",
        ["write_bud"],
        str(org_id),
    )
    assert mcp_auth._internal_tokens == {config.mcp_token: org_id}


def test_mcp_config_is_skipped_without_a_backend_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid org but no backend URL: no MCP server, and no token minted."""
    monkeypatch.setattr(settings, "mcp_backend_url", "")
    monkeypatch.setattr(mcp_auth, "_internal_tokens", {})

    assert job_utils.build_mcp_config(str(uuid.uuid4())) is None
    assert mcp_auth._internal_tokens == {}


def test_mcp_config_is_skipped_for_an_org_id_that_is_not_a_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend URL but a malformed org id: no MCP server, and no token minted."""
    monkeypatch.setattr(settings, "mcp_backend_url", "http://127.0.0.1:8999")
    monkeypatch.setattr(mcp_auth, "_internal_tokens", {})

    assert job_utils.build_mcp_config("not-a-uuid") is None
    assert mcp_auth._internal_tokens == {}
