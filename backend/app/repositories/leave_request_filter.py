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

"""Optional narrowing shared by request lists (approvals queue, reports)."""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Select

from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus


@dataclass(frozen=True)
class RequestFilter:
    """Each field narrows when set. ``start``/``end`` match overlapping dates."""

    start: date | None = None
    end: date | None = None
    kind: LeaveKind | None = None
    leave_type_id: uuid.UUID | None = None
    statuses: tuple[LeaveStatus, ...] | None = None
    policy_id: uuid.UUID | None = None


def apply_filter[S: Select[Any]](stmt: S, filters: RequestFilter | None) -> S:
    """``stmt`` (selecting from LeaveRequest) narrowed by ``filters``."""
    if filters is None:
        return stmt
    if filters.start is not None:
        stmt = stmt.where(LeaveRequest.end_date >= filters.start)
    if filters.end is not None:
        stmt = stmt.where(LeaveRequest.start_date <= filters.end)
    if filters.kind is not None:
        stmt = stmt.where(LeaveRequest.kind == filters.kind)
    if filters.leave_type_id is not None:
        stmt = stmt.where(LeaveRequest.leave_type_id == filters.leave_type_id)
    if filters.statuses is not None:
        stmt = stmt.where(LeaveRequest.status.in_(filters.statuses))
    if filters.policy_id is not None:
        stmt = stmt.where(LeaveRequest.policy_id == filters.policy_id)
    return stmt
