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

"""Who sees and edits which parts of an employee record."""

import uuid

from app.core.deps import PermissionSet
from app.services.employees.access import access_for

ME, OTHER = uuid.uuid4(), uuid.uuid4()
HR = PermissionSet(ids=frozenset({"employees:view", "employees:manage"}), is_owner=False)
VIEWER = PermissionSet(ids=frozenset({"employees:view"}), is_owner=False)
NOBODY = PermissionSet(ids=frozenset(), is_owner=False)
OWNER = PermissionSet(ids=frozenset(), is_owner=True)


def test_hr_sees_and_edits_others() -> None:
    access = access_for(HR, ME, OTHER)
    assert access.view_personal and access.edit_work and access.edit_managers


def test_hr_cannot_edit_own_work_or_managers() -> None:
    access = access_for(HR, ME, ME)
    assert access.view_personal
    assert not access.edit_work
    assert not access.edit_managers


def test_owner_can_edit_own_work() -> None:
    assert access_for(OWNER, ME, ME).edit_work


def test_view_only_gets_work_fields_only() -> None:
    access = access_for(VIEWER, ME, OTHER)
    assert access.view and not access.view_personal and not access.edit_work


def test_member_without_permissions_sees_only_themself() -> None:
    assert access_for(NOBODY, ME, ME).view_personal
    assert not access_for(NOBODY, ME, OTHER).view
