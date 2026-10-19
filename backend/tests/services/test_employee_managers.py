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

"""Reporting-manager rules: dedupe, one primary, no self, no loops."""

import uuid

import pytest

from app.services.employees.managers import (
    ManagerChoice,
    ManagerValidationError,
    has_cycle,
    normalize_primary,
    validate_managers,
    would_create_cycle,
)

A, B, C, D = (uuid.uuid4() for _ in range(4))


def test_first_manager_becomes_primary_when_none_marked() -> None:
    assert normalize_primary([ManagerChoice(A), ManagerChoice(B)]) == [(A, True), (B, False)]


def test_marked_primary_is_kept() -> None:
    assert normalize_primary([ManagerChoice(A), ManagerChoice(B, True)]) == [(A, False), (B, True)]


def test_duplicates_collapse_and_keep_primary_flag() -> None:
    assert normalize_primary([ManagerChoice(A), ManagerChoice(A, True)]) == [(A, True)]


def test_two_primaries_rejected() -> None:
    with pytest.raises(ManagerValidationError, match="only one"):
        normalize_primary([ManagerChoice(A, True), ManagerChoice(B, True)])


def test_no_managers_is_fine() -> None:
    assert normalize_primary([]) == []


def test_direct_loop_detected() -> None:
    # B reports to A; making A report to B closes the loop.
    assert would_create_cycle(A, [B], edges=[(B, A)])


def test_indirect_loop_detected() -> None:
    # C → B → A; making A report to C closes a three-step loop.
    assert would_create_cycle(A, [C], edges=[(C, B), (B, A)])


def test_unrelated_chain_is_not_a_loop() -> None:
    assert not would_create_cycle(A, [B], edges=[(B, C), (C, D)])


def test_employees_current_links_are_ignored() -> None:
    # A's existing link to B is being replaced, so it can't form a loop.
    assert not would_create_cycle(A, [B], edges=[(A, B)])


def test_self_manager_rejected() -> None:
    with pytest.raises(ManagerValidationError, match="own manager"):
        validate_managers(A, [ManagerChoice(A)], active_members={A}, edges=[])


def test_inactive_or_foreign_manager_rejected() -> None:
    with pytest.raises(ManagerValidationError, match="active members"):
        validate_managers(A, [ManagerChoice(B)], active_members=set(), edges=[])


def test_loop_rejected() -> None:
    with pytest.raises(ManagerValidationError, match="loop"):
        validate_managers(A, [ManagerChoice(B)], active_members={B}, edges=[(B, A)])


def test_valid_list_is_normalized() -> None:
    pairs = validate_managers(
        A, [ManagerChoice(B), ManagerChoice(C, True)], active_members={B, C}, edges=[]
    )
    assert pairs == [(B, False), (C, True)]


def test_existing_deactivated_manager_may_stay() -> None:
    # B left the company, but HR can still change A's primary to C.
    pairs = validate_managers(
        A,
        [ManagerChoice(B), ManagerChoice(C, True)],
        active_members={C},
        edges=[],
        existing={B},
    )
    assert pairs == [(B, False), (C, True)]


def test_new_deactivated_manager_still_rejected() -> None:
    with pytest.raises(ManagerValidationError, match="active members"):
        validate_managers(A, [ManagerChoice(B)], active_members=set(), edges=[], existing={C})


def test_has_cycle() -> None:
    assert has_cycle([(A, B), (B, C), (C, A)])
    assert not has_cycle([(A, B), (B, C), (A, C)])
    assert not has_cycle([])
