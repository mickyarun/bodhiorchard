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

"""Unit tests for the ``test_case_id`` regex guard in ``bud_qa``."""

from __future__ import annotations

import pytest

from app.api.v1.bud_qa import _TEST_CASE_ID_PATTERN


@pytest.mark.parametrize(
    "value",
    [
        "tc-001",
        "TC_42",
        "abc123",
        "a",
        "a" * 64,  # max length
    ],
)
def test_test_case_id_pattern_accepts_real_identifiers(value: str) -> None:
    """Real test-case IDs from the frontend pass through."""
    assert _TEST_CASE_ID_PATTERN.match(value) is not None


@pytest.mark.parametrize(
    "payload",
    [
        "../escape",
        "tc-001/../other",
        "tc 001",
        "tc/001",
        "tc.001",
        "",
        "a" * 65,  # one over the cap
        "tc-001\n",
    ],
)
def test_test_case_id_pattern_rejects_path_separators(payload: str) -> None:
    """Anything containing ``/``, ``..``, whitespace, or unsafe chars is rejected."""
    assert _TEST_CASE_ID_PATTERN.match(payload) is None
