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

"""What someone is told when a request goes past a "stops at balance" type."""

from decimal import Decimal

from app.services.leave.over_balance import Other, over_balance_message

D = Decimal


def test_some_left_points_at_what_else_they_have() -> None:
    text = over_balance_message("Sick leave", D(1), [Other("Earned leave", D(6))])
    assert text == (
        "You have 1 day of Sick leave left, so request that much. "
        "Request the rest as another type: Earned leave (6 days left)."
    )


def test_none_left_and_types_that_are_used_up_are_not_offered() -> None:
    others = [Other("Earned leave", D(0)), Other("Unpaid leave", None)]
    assert over_balance_message("Sick leave", D(0), others) == (
        "You have no Sick leave left. Request it as another type: Unpaid leave."
    )


def test_nothing_else_left_sends_them_to_a_person() -> None:
    text = over_balance_message("Sick leave", D("-1"), [Other("Earned leave", D(0))])
    assert text == (
        "You have no Sick leave left. You have no other leave left, so talk to your manager or HR."
    )
