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

"""Which dates a request may cover (pure).

* not further back than the policy's backdating limit,
* not past the end of next leave year,
* within a single leave year.
"""

from datetime import date, timedelta

from app.schemas.leave import ProblemCode
from app.services.leave.calendar_math import (
    leave_year_bounds,
    leave_year_by_label,
    same_leave_year,
)


def date_problems(
    start: date,
    end: date,
    *,
    today: date,
    backdate_limit_days: int,
    year_start_month: int,
) -> list[tuple[ProblemCode, str]]:
    """Reasons the range can't be requested; empty when it's fine."""
    problems: list[tuple[ProblemCode, str]] = []
    if start < today - timedelta(days=backdate_limit_days):
        problems.append(
            ("too_far_back", f"Requests can go back at most {backdate_limit_days} days.")
        )
    current = leave_year_bounds(today, year_start_month).label
    latest = leave_year_by_label(current + 1, year_start_month).end
    if end > latest:
        problems.append(
            (
                "too_far_ahead",
                f"Requests can be made up to {latest:%a %d %b %Y}, the end of next leave year.",
            )
        )
        return problems
    if not same_leave_year(start, end, year_start_month):
        year_end = leave_year_bounds(start, year_start_month).end
        problems.append(
            (
                "crosses_leave_year",
                f"Requests can't span two leave years. Split it at {year_end:%a %d %b}.",
            )
        )
    return problems
