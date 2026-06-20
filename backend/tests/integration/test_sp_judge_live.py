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

"""Live (un-stubbed) check that the SP-attribution judge actually works.

Every other SP test stubs ``judge_sp_attribution``; this one runs the real
``run_claude_code`` call so the prompt + JSON parsing are exercised against
a real model. It needs a working Claude auth session (host login or org API
key), so it is gated behind ``-m integration`` and **self-skips** when the
judge returns its deterministic fallback (the all-equal weights you get when
the LLM is unavailable) — that way it never produces a false failure in an
environment without LLM access.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.sp_attribution import TodoForJudgment, judge_sp_attribution

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_judge_downweights_trivial_work() -> None:
    substantive = uuid.uuid4()
    trivial = uuid.uuid4()
    todos = [
        TodoForJudgment(
            todo_id="t_real",
            assignee_id=substantive,
            title="Implement webhook fan-out delivery with a retry queue",
            description="New service: parse event, enqueue per-subscriber, exponential backoff",
        ),
        TodoForJudgment(
            todo_id="t_trivial",
            assignee_id=trivial,
            title="Change the settings gear icon",
            description="swap the icon asset",
        ),
    ]

    result = await judge_sp_attribution(todos, [])

    # Fallback (LLM unavailable) → every weight is exactly 1.0. Skip rather
    # than fail, so this only asserts when a real model actually ran.
    if all(w == 1.0 for w in result.todo_weights.values()):
        pytest.skip("LLM judge unavailable — got deterministic fallback weights")

    assert set(result.todo_weights) == {"t_real", "t_trivial"}
    assert 0.0 <= result.todo_weights["t_trivial"] <= 1.0
    assert 0.0 <= result.todo_weights["t_real"] <= 1.0
    # The whole point: trivial work is weighted strictly below substantive work.
    assert result.todo_weights["t_trivial"] < result.todo_weights["t_real"]
