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

"""Tests for ``skill_loader._validate_skill_name`` defensive check."""

from __future__ import annotations

import pytest

from app.services.skill_loader import _validate_skill_name, load_skill


@pytest.mark.parametrize(
    "name",
    [
        "triage-analyst",
        "bud-spec",
        "a",
        "abc123",
        "z" + "a" * 98 + "z",  # 100 chars exactly
    ],
)
def test_validate_skill_name_accepts_kebab_case(name: str) -> None:
    """Real kebab-case slugs pass through unchanged."""
    assert _validate_skill_name(name) == name


@pytest.mark.parametrize(
    "payload",
    [
        "../escape",
        "triage/../other",
        "/etc/passwd",
        "triage_analyst",  # underscore not allowed
        "Triage-Analyst",  # uppercase not allowed
        "triage analyst",  # whitespace
        "triage.analyst",  # dot
        "-leading-hyphen",
        "trailing-hyphen-",
        "",
        "a" * 101,  # one over the length cap
    ],
)
def test_validate_skill_name_rejects_traversal_and_malformed(payload: str) -> None:
    """Any slug carrying ``/``, ``..``, whitespace, or non-kebab chars is rejected."""
    with pytest.raises(ValueError, match="invalid skill name"):
        _validate_skill_name(payload)


def test_load_skill_rejects_traversal_payload() -> None:
    """``load_skill`` blocks traversal before touching the filesystem."""
    with pytest.raises(ValueError, match="invalid skill name"):
        load_skill("../../etc/passwd")
