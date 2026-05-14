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

"""Unit tests for the BUD section edit-policy gate.

These are pure helper tests — no DB access — covering every
``(field, status)`` combination plus the boolean predicate variants.
The handler-level contract tests (PATCH /buds/{id} and the import
endpoint both raising 409 with ``bud_section_locked``) live in
``tests/api/v1/test_bud_edit_gating.py``.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.bud import BUDStatus
from app.services.bud_edit_policy import (
    FIELD_OWNING_STATUS,
    assert_design_editable,
    assert_section_editable,
    is_design_editable,
    is_section_editable,
)


@pytest.mark.parametrize(
    ("field", "owning_status"),
    list(FIELD_OWNING_STATUS.items()),
)
def test_section_editable_in_owning_phase(field: str, owning_status: BUDStatus) -> None:
    """In the section's owning phase, the gate is a no-op."""
    bud = SimpleNamespace(status=owning_status)
    # Must not raise.
    assert_section_editable(bud, field)


@pytest.mark.parametrize(
    ("field", "owning_status"),
    list(FIELD_OWNING_STATUS.items()),
)
@pytest.mark.parametrize(
    "other_status",
    [
        BUDStatus.BUD,
        BUDStatus.DESIGN,
        BUDStatus.TECH_ARCH,
        BUDStatus.DEVELOPMENT,
        BUDStatus.CODE_REVIEW,
        BUDStatus.TESTING,
        BUDStatus.UAT,
        BUDStatus.PROD,
        BUDStatus.CLOSED,
    ],
)
def test_section_locked_outside_owning_phase(
    field: str,
    owning_status: BUDStatus,
    other_status: BUDStatus,
) -> None:
    """Out of phase → HTTP 409 with the bud_section_locked code."""
    if other_status == owning_status:
        return  # covered by the happy-path test
    bud = SimpleNamespace(status=other_status)
    with pytest.raises(HTTPException) as excinfo:
        assert_section_editable(bud, field)
    assert excinfo.value.status_code == 409
    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "bud_section_locked"
    assert detail["field"] == field
    assert detail["current_status"] == other_status.value
    assert detail["required_status"] == owning_status.value


@pytest.mark.parametrize(
    "free_field",
    ["title", "assignee_id", "status", "metadata_", "status_override_reason"],
)
def test_non_section_fields_are_always_allowed(free_field: str) -> None:
    """Fields outside FIELD_OWNING_STATUS pass regardless of phase."""
    for status in (BUDStatus.BUD, BUDStatus.DEVELOPMENT, BUDStatus.PROD):
        bud = SimpleNamespace(status=status)
        # Must not raise.
        assert_section_editable(bud, free_field)


def test_design_editable_only_in_design_phase() -> None:
    """assert_design_editable mirrors the section gate for design rows."""
    assert_design_editable(SimpleNamespace(status=BUDStatus.DESIGN))
    for other in (
        BUDStatus.BUD,
        BUDStatus.TECH_ARCH,
        BUDStatus.DEVELOPMENT,
        BUDStatus.CODE_REVIEW,
        BUDStatus.TESTING,
        BUDStatus.UAT,
        BUDStatus.PROD,
        BUDStatus.CLOSED,
        BUDStatus.DISCARDED,
    ):
        with pytest.raises(HTTPException) as excinfo:
            assert_design_editable(SimpleNamespace(status=other))
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail["code"] == "bud_section_locked"
        assert excinfo.value.detail["field"] == "design"


# ── Pure predicate variants (callable from non-HTTP contexts) ──────────


def test_is_section_editable_matches_assert_outcome() -> None:
    """The bool predicate should agree with the HTTP wrapper across all combinations."""
    for field, owning in FIELD_OWNING_STATUS.items():
        for current in BUDStatus:
            bud = SimpleNamespace(status=current)
            should_be_editable = current == owning
            assert is_section_editable(bud, field) is should_be_editable


def test_is_section_editable_true_for_unmapped_field() -> None:
    """``title`` and friends are always editable."""
    bud = SimpleNamespace(status=BUDStatus.PROD)
    assert is_section_editable(bud, "title") is True
    assert is_section_editable(bud, "assignee_id") is True


def test_is_design_editable() -> None:
    """Pure predicate mirrors the assert form for design rows."""
    assert is_design_editable(SimpleNamespace(status=BUDStatus.DESIGN)) is True
    assert is_design_editable(SimpleNamespace(status=BUDStatus.BUD)) is False
    assert is_design_editable(SimpleNamespace(status=BUDStatus.DEVELOPMENT)) is False
