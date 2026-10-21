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


"""Summary columns merge same-named leave types across policies."""

import uuid
from decimal import Decimal

from app.models.leave_type import LeaveType
from app.services.leave.reports.type_columns import type_columns


def _type(name: str) -> LeaveType:
    return LeaveType(id=uuid.uuid4(), policy_id=uuid.uuid4(), name=name, code="X")


def test_same_names_share_a_column_ignoring_case_and_spacing() -> None:
    india, uk, earned = _type("Sick leave"), _type("sick  Leave"), _type("Earned leave")
    columns = type_columns([india, uk, earned])
    assert [c.name for c in columns.refs] == ["Earned leave", "Sick leave"]
    assert columns.key_of[india.id] == columns.key_of[uk.id]


def test_taken_sums_and_left_goes_unlimited_if_any_type_is() -> None:
    old, new, wfh = _type("Casual"), _type("Casual"), _type("Comp off")
    columns = type_columns([old, new, wfh])
    key, comp = columns.key_of[old.id], columns.key_of[wfh.id]
    taken = columns.taken({old.id: Decimal("2"), new.id: Decimal("1.5")})
    assert taken == {key: Decimal("3.5")}
    left = columns.left({new.id: Decimal("4"), wfh.id: None})
    assert left == {key: Decimal("4"), comp: None}
    assert columns.left({old.id: Decimal("1"), new.id: None}) == {key: None}
