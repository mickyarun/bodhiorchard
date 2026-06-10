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

"""Schema-level validation tests for ``BUDUpdate.branch_overrides``.

The column is a JSONB blob, so the only guard against silently bad
data — a typo, a stage name from a future release, an old client sending
``UAT`` upper-case — is the field validator. These tests pin its
accept / reject set so a refactor of the validator cannot quietly widen
the contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.bud import BUDUpdate


@pytest.mark.parametrize(
    "overrides",
    [
        None,
        {},
        {"uat": "release/*"},
        {"prod": "main"},
        {"uat": "release/2026-08-01", "prod": "main"},
    ],
)
def test_branch_overrides_accepts_valid_stage_keys(
    overrides: dict[str, str] | None,
) -> None:
    """Two stage names (``uat``, ``prod``) — and their combinations — pass."""
    body = BUDUpdate(branch_overrides=overrides)
    assert body.branch_overrides == overrides


@pytest.mark.parametrize(
    "overrides",
    [
        {"UAT": "release/*"},  # wrong case
        {"production": "main"},  # full word instead of stage code
        {"development": "develop"},  # not a release stage at all
        {"uat": "release/*", "code_review": "x"},  # mixed valid + invalid
    ],
)
def test_branch_overrides_rejects_unknown_stage_keys(overrides: dict[str, str]) -> None:
    """Unsupported keys must surface as a 422 at the API boundary."""
    with pytest.raises(ValidationError) as excinfo:
        BUDUpdate(branch_overrides=overrides)
    assert "Unsupported branch_overrides keys" in str(excinfo.value)


@pytest.mark.parametrize(
    "stage,pattern",
    [
        ("uat", ""),
        ("prod", "   "),
        ("uat", "\t"),
    ],
)
def test_branch_overrides_rejects_empty_or_whitespace_patterns(stage: str, pattern: str) -> None:
    """Empty / whitespace strings fnmatch nothing — surface at the edge."""
    with pytest.raises(ValidationError) as excinfo:
        BUDUpdate(branch_overrides={stage: pattern})
    assert "must be a non-empty pattern or null" in str(excinfo.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"uat": None},
        {"prod": None},
        {"uat": "release/*", "prod": None},
    ],
)
def test_branch_overrides_accepts_null_value_as_clear_signal(
    overrides: dict[str, str | None],
) -> None:
    """``{stage: null}`` is the clear-this-stage signal; the handler
    drops the key from the merged column. The schema must let it through.
    """
    body = BUDUpdate(branch_overrides=overrides)
    assert body.branch_overrides == overrides


def test_impacted_repos_passes_through() -> None:
    """Editing impacted_repos via PATCH is now supported on the schema."""
    body = BUDUpdate(impacted_repos=[{"repo_id": "abc", "repo_name": "frontend"}])
    assert body.impacted_repos == [{"repo_id": "abc", "repo_name": "frontend"}]
