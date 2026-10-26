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

"""The celebration opt-out belongs to the employee.

The employee may mute or unmute; HR may only mute; nobody else may touch
it — and the HR personal-details save can never flip it, stale form or not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1 import employee_updates as routes
from app.schemas.employee import CelebrationPrefsUpdate, EmployeePersonal

ORG = uuid.uuid4()
EMPLOYEE = uuid.uuid4()
HR_USER = uuid.uuid4()
COLLEAGUE = uuid.uuid4()


@dataclass
class _Perms:
    granted: set[str] = field(default_factory=set)
    is_owner: bool = False

    def has(self, permission: str) -> bool:
        return self.is_owner or permission in self.granted

    def has_all(self, permissions: Any) -> bool:
        return all(self.has(p) for p in permissions)

    def has_any(self, permissions: Any) -> bool:
        return any(self.has(p) for p in permissions)


class _Db:
    async def flush(self) -> None:
        return None


@pytest.fixture
def profile(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    record = SimpleNamespace(
        celebrate_birthday=False,  # the employee muted it
        celebrate_anniversary=True,
        gender=None,
        date_of_birth=None,
        blood_group=None,
    )

    async def _load(db: Any, org_id: Any, user_id: Any, **kw: Any) -> Any:
        return record, SimpleNamespace(id=user_id)

    async def _read(db: Any, **kw: Any) -> str:
        return "ok"

    monkeypatch.setattr(routes, "load_record", _load)
    monkeypatch.setattr(routes, "employee_read", _read)
    return record


def _caller(user_id: uuid.UUID) -> Any:
    return SimpleNamespace(id=user_id, org_id=ORG)


async def _patch(actor: uuid.UUID, perms: _Perms, **changes: bool) -> Any:
    return await routes.update_celebration_prefs(
        EMPLOYEE,
        CelebrationPrefsUpdate(**changes),
        current_user=_caller(actor),
        perms=perms,
        db=_Db(),
    )


HR = _Perms({"employees:manage"})


async def test_employee_can_unmute_their_own(profile: SimpleNamespace) -> None:
    await _patch(EMPLOYEE, _Perms(), celebrate_birthday=True)
    assert profile.celebrate_birthday is True


async def test_employee_can_mute_their_own(profile: SimpleNamespace) -> None:
    await _patch(EMPLOYEE, _Perms(), celebrate_anniversary=False)
    assert profile.celebrate_anniversary is False


async def test_hr_can_mute_on_someones_behalf(profile: SimpleNamespace) -> None:
    await _patch(HR_USER, HR, celebrate_anniversary=False)
    assert profile.celebrate_anniversary is False


async def test_hr_cannot_unmute_someone(profile: SimpleNamespace) -> None:
    with pytest.raises(HTTPException) as exc:
        await _patch(HR_USER, HR, celebrate_birthday=True)
    assert exc.value.status_code == 403
    assert profile.celebrate_birthday is False


async def test_even_the_owner_cannot_unmute_someone(profile: SimpleNamespace) -> None:
    with pytest.raises(HTTPException):
        await _patch(HR_USER, _Perms(is_owner=True), celebrate_birthday=True)
    assert profile.celebrate_birthday is False


async def test_a_colleague_cannot_touch_it(profile: SimpleNamespace) -> None:
    with pytest.raises(HTTPException) as exc:
        await _patch(COLLEAGUE, _Perms({"employees:view"}), celebrate_anniversary=False)
    assert exc.value.status_code == 403
    assert profile.celebrate_anniversary is True


async def test_omitted_fields_are_left_alone(profile: SimpleNamespace) -> None:
    await _patch(EMPLOYEE, _Perms(), celebrate_anniversary=False)
    assert profile.celebrate_birthday is False  # untouched


async def test_hr_personal_save_cannot_flip_the_opt_out(profile: SimpleNamespace) -> None:
    """A stale HR form (or one sending the flags) leaves the mute in place."""
    body = EmployeePersonal.model_validate(
        {"blood_group": "o_positive", "celebrate_birthday": True, "celebrate_anniversary": True}
    )
    assert "celebrate_birthday" not in body.model_dump()
    await routes.update_personal(EMPLOYEE, body, current_user=_caller(HR_USER), perms=HR, db=_Db())
    assert profile.blood_group == "o_positive"
    assert profile.celebrate_birthday is False
