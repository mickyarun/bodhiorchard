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


"""One summary column per leave-type name, across policies.

Each policy has its own "Sick leave" type, but a person is on one policy at
a time, so a single "Sick leave" column reads naturally: a cell shows that
person's own type. Names match ignoring case and spacing.
"""

import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.models.leave_type import LeaveType
from app.schemas.leave_reports import TypeColumn


def column_key(name: str) -> str:
    """The column a type name falls under; "Sick  Leave" and "sick leave" share one."""
    return " ".join(name.split()).casefold()


@dataclass(frozen=True)
class Columns:
    """The columns, and which column each leave type falls under."""

    refs: list[TypeColumn]
    key_of: dict[uuid.UUID, str]

    def taken(self, per_type: Mapping[uuid.UUID, Decimal]) -> dict[str, Decimal]:
        """Days per column; a column sums its types (e.g. an old policy's)."""
        out: dict[str, Decimal] = defaultdict(Decimal)
        for type_id, days in per_type.items():
            out[self.key_of[type_id]] += days
        return dict(out)

    def left(self, per_type: Mapping[uuid.UUID, Decimal | None]) -> dict[str, Decimal | None]:
        """Days left per column; None (no limit) if any of its types is unlimited."""
        totals: dict[str, Decimal] = defaultdict(Decimal)
        unlimited: set[str] = set()
        for type_id, available in per_type.items():
            key = self.key_of[type_id]
            if available is None:
                unlimited.add(key)
            else:
                totals[key] += available
        return {key: None if key in unlimited else totals[key] for key in {*totals, *unlimited}}


def type_columns(types: Sequence[LeaveType]) -> Columns:
    """Columns sorted by name; each is titled by its first type's spelling."""
    refs: dict[str, TypeColumn] = {}
    key_of: dict[uuid.UUID, str] = {}
    for t in sorted(types, key=lambda t: column_key(t.name)):
        key = column_key(t.name)
        refs.setdefault(key, TypeColumn(key=key, name=t.name))
        key_of[t.id] = key
    return Columns(refs=list(refs.values()), key_of=key_of)
