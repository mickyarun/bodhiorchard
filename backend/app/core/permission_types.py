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

"""Dataclasses describing permissions and their categories."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionDef:
    """A single permission definition.

    Attributes:
        sensitive: Grants access to people data (leave reasons, employee
            records). Grants of sensitive permissions are logged for audit.
        backfill_custom_roles: When the seeder first inserts this
            permission, also grant it to every existing custom role. Used
            for permissions that gate access the custom roles already had
            before the permission existed.
    """

    resource_id: str
    name: str
    description: str = ""
    sensitive: bool = False
    backfill_custom_roles: bool = False


@dataclass(frozen=True)
class CategoryDef:
    """A permission category with its child permissions."""

    key: str
    name: str
    description: str = ""
    permissions: list[PermissionDef] = field(default_factory=list)
