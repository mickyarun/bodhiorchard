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

from pydantic import BaseModel, Field


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


class CodeReviewOverrideRequest(BaseModel):
    """Body for POST /buds/{id}/code-review/override.

    Forces a BUD from code_review → testing with a user-supplied reason
    when the normal PR-merge-driven auto-transition doesn't apply (e.g.
    docs-only changes, manual merges, or exceptional escalations).
    """

    reason: str = Field(..., min_length=10, max_length=2000)
