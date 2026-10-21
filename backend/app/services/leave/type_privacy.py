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

"""Who may see a gender-limited leave type (period leave) on someone else's leave (pure).

Its name says why someone is off, and whether it appears at all says how
they're recorded on their profile. So only the person themself and those
who already see personal details (``employees:manage``, the owner) see it.
Everyone else, managers and ``leave:reports`` included, sees plain "leave":
the type is left out for every person they look at, never only for some,
so its absence can't single anyone out either.
"""

from collections.abc import Callable, Iterable

from app.core.permission_deps import PermissionSet
from app.models.leave_type import LeaveType

# Personal details already include gender; nobody else learns it from leave.
SEES_RESTRICTED = "employees:manage"


def sees_restricted(perms: PermissionSet) -> bool:
    """True if the viewer may see gender-limited types on anyone's leave."""
    return perms.has(SEES_RESTRICTED)


def is_restricted(leave_type: LeaveType) -> bool:
    """True for a type only some genders can use."""
    return leave_type.eligible_genders is not None


def shown(leave_type: LeaveType | None, *, sees_all: bool) -> bool:
    """Whether a viewer may see this type by name (no type is nothing to hide)."""
    return leave_type is None or sees_all or not is_restricted(leave_type)


def visible[T](
    items: Iterable[T], type_of: Callable[[T], LeaveType | None], *, sees_all: bool
) -> list[T]:
    """``items`` without those whose type the viewer may not see."""
    return [item for item in items if shown(type_of(item), sees_all=sees_all)]
