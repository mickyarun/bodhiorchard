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

"""Pydantic schemas for the BUD code-review tab + override endpoint.

Split out of :mod:`app.schemas.bud` so the code-review DTOs live next
to their endpoint surface area instead of inflating the core BUD CRUD
module.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Lifecycle states surfaced on the Code Review tab for the latest
# ``code_review`` agent task. Drives a banner above the per-repo PR list:
#
# * ``never_run`` — no task has run for this BUD yet (rare in normal flow,
#   but possible if the agent was force-skipped by the no-open-PRs guard).
#   No banner.
# * ``running`` — a task is in-flight. Optional "agent running…" banner.
# * ``ok`` — last run succeeded (parse_ok). No banner.
# * ``parse_failed`` — last run completed but its JSON was unparseable.
#   Banner with the typed ``last_run_message`` (see
#   ``_parse_failure_reason`` in agent_result_handlers).
# * ``failed`` — last task row is in status FAILED (subprocess crash,
#   skill error, etc.).
CodeReviewRunStatus = Literal["never_run", "running", "ok", "parse_failed", "failed"]


# Banner copy surfaced on the Code Review tab when the last agent run
# could not be parsed. Reason values come from
# :func:`app.services.agent_result_handlers._parse_code_review_output`
# and are persisted on ``BUDAgentTask.result_summary.parse_failure_reason``.
# Co-located here (rather than in the service layer) so the API
# contract — types AND user-facing copy — lives in one place.
PARSE_FAILURE_MESSAGES: dict[str, str] = {
    "insight_contaminated": (
        "Code review agent output was wrapped in ★ Insight blocks (a Claude "
        "output-style plugin contaminated the response). Disable the "
        "learning/explanatory output-style plugin on the backend host, then "
        "re-run the review."
    ),
    "no_json": (
        "Code review agent did not return JSON. Check the backend logs for "
        "``code_review_output_no_json`` and re-run the review."
    ),
    "not_dict": (
        "Code review agent returned malformed JSON (not an object). Check "
        "the backend logs for ``code_review_output_not_dict`` and re-run."
    ),
    "parse_exception": (
        "Code review agent output could not be parsed (extractor raised). "
        "Check the backend logs and re-run the review."
    ),
}
GENERIC_PARSE_FAILURE_MESSAGE = (
    "Code review agent output was unparseable. Check the backend logs and re-run the review."
)
TASK_FAILED_MESSAGE = (
    "Code review agent task failed before producing output. Check the "
    "backend logs and re-run from the BUD."
)


class CodeReviewRepoStatus(BaseModel):
    """Per-repo status row shown on the Code Review tab."""

    repo_id: str
    repo_name: str
    pr_number: int | None = None
    pr_state: str  # "not_raised" | "open" | "merged" | "closed"
    pr_url: str | None = None
    comment_count: int


class CodeReviewStatusResponse(BaseModel):
    """Response for GET /buds/{id}/code-review/status."""

    repos: list[CodeReviewRepoStatus]
    last_run_status: CodeReviewRunStatus = "never_run"
    # Short human-facing message for the banner when ``last_run_status``
    # is ``parse_failed`` or ``failed``. ``None`` for the success / idle
    # states so the frontend can short-circuit rendering.
    last_run_message: str | None = None


class CodeReviewOverrideRequest(BaseModel):
    """Body for POST /buds/{id}/code-review/override.

    Forces a BUD from code_review → testing with a user-supplied reason
    when the normal PR-merge-driven auto-transition doesn't apply (e.g.
    docs-only changes, manual merges, or exceptional escalations).
    """

    reason: str = Field(..., min_length=10, max_length=2000)
