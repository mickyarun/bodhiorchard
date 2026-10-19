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

"""Recording changes to leave configuration (pure diffing + one write).

Only the fields a change touched are kept, as ``[old, new]`` pairs, and
only plain values (numbers, flags, names, codes, lists of weekdays).
"""

import uuid
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_config_event import LeaveConfigAction
from app.repositories.leave_config_event import LeaveConfigEventRepository


def _plain(value: Any) -> Any:
    """A JSON-safe copy: Decimals as plain strings, enums as values, dates as ISO.

    Decimals are normalised so the stored 5.0 and a submitted 5 compare
    equal: only real changes are recorded.
    """
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[Any]]:
    """``{field: [old, new]}`` for every field in ``after`` whose value changed."""
    return {
        field: [_plain(before.get(field)), _plain(new)]
        for field, new in after.items()
        if _plain(before.get(field)) != _plain(new)
    }


def snapshot(row: object, fields: Mapping[str, Any]) -> dict[str, Any]:
    """The current values of ``fields`` on an ORM row, before it's changed."""
    return {field: getattr(row, field) for field in fields}


def record(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: LeaveConfigAction,
    policy_id: uuid.UUID | None,
    changes: Mapping[str, Any],
) -> None:
    """Add the event to the caller's transaction (it commits with the change)."""
    LeaveConfigEventRepository(db, org_id=org_id).record(
        actor_id=actor_id,
        action=action,
        policy_id=policy_id,
        changes={field: _plain(value) for field, value in changes.items()},
    )
