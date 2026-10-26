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

"""DTOs for employee records.

Work and personal fields are separate models on purpose: a response is
assembled from the sections the caller may see, so a view-only reader can
never receive personal data by way of ``from_attributes`` picking up a
column it shouldn't.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.employee_profile import (
    BloodGroup,
    EmployeeStatus,
    EmploymentType,
    Gender,
    WorkArrangement,
)
from app.schemas.country import CountryCode


class EmployeeWork(BaseModel):
    """Work details — visible to anyone with ``employees:view``."""

    model_config = ConfigDict(from_attributes=True)

    employee_code: str | None = Field(None, max_length=50)
    designation: str | None = Field(None, max_length=150)
    department: str | None = Field(None, max_length=150)
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    date_of_joining: date | None = None
    date_of_exit: date | None = None
    country_code: CountryCode | None = None
    work_arrangement: WorkArrangement = WorkArrangement.OFFICE
    office_id: uuid.UUID | None = None

    @field_validator("employee_code", "designation", "department")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _exit_date_matches_status(self) -> "EmployeeWork":
        # Remote people don't work from an office.
        if self.work_arrangement == WorkArrangement.REMOTE:
            self.office_id = None
        # An active employee has no exit date (e.g. after being re-hired).
        if self.status == EmployeeStatus.ACTIVE:
            self.date_of_exit = None
        if (
            self.date_of_exit is not None
            and self.date_of_joining is not None
            and self.date_of_exit < self.date_of_joining
        ):
            raise ValueError("The exit date can't be before the joining date.")
        return self


class EmployeeContact(BaseModel):
    """The personal fields an employee may edit about themself."""

    model_config = ConfigDict(from_attributes=True)

    phone: str | None = Field(None, max_length=40)
    personal_email: EmailStr | None = None
    emergency_contact_name: str | None = Field(None, max_length=255)
    emergency_contact_relation: str | None = Field(None, max_length=100)
    emergency_contact_phone: str | None = Field(None, max_length=40)


class EmployeePersonal(EmployeeContact):
    """All personal fields — HR, the owner and the employee themself."""

    date_of_birth: date | None = None
    gender: Gender | None = None
    blood_group: BloodGroup | None = None


class EmployeePersonalRead(EmployeePersonal):
    """Personal fields as shown on a profile, plus the celebration opt-outs.

    The opt-outs are read-only here on purpose. They are written only
    through :class:`CelebrationPrefsUpdate`, never by the personal-details
    save: that save replaces every field, so carrying the flags on it would
    let a stale HR form — or any client that omits them — silently switch a
    person's muted announcement back on.
    """

    celebrate_birthday: bool = True
    celebrate_anniversary: bool = True


class CelebrationPrefsUpdate(BaseModel):
    """Mute or unmute someone's celebration announcements. Omitted = unchanged.

    The employee may set either flag either way. HR may only mute (``False``);
    turning an announcement back on is the employee's call alone.
    """

    celebrate_birthday: bool | None = None
    celebrate_anniversary: bool | None = None


class ManagerRef(BaseModel):
    """A reporting manager as shown on a profile."""

    user_id: uuid.UUID
    name: str
    is_primary: bool
    is_active: bool


class EmployeeLeavePolicy(BaseModel):
    """The leave policy an employee follows — part of the work details.

    ``explicit`` is False when nobody has assigned one, so the default applies.
    """

    id: uuid.UUID
    name: str
    is_default: bool
    explicit: bool


class OfficeRef(BaseModel):
    """An office by id and name."""

    id: uuid.UUID
    name: str


class EmployeeAccessRead(BaseModel):
    """What the caller may change on this record (drives the UI)."""

    edit_work: bool
    edit_personal: bool
    edit_managers: bool
    edit_name: bool
    reset_password: bool


class EmployeeRead(BaseModel):
    """One employee record, with only the sections the caller may see."""

    user_id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    email: str
    is_active: bool
    # Profile photo, visible to anyone who can see the record at all. May be
    # absolute (Slack CDN) or root-relative (hosted here); ``None`` means the
    # UI falls back to initials.
    avatar_url: str | None = None
    # Whether the caller may replace this photo: their own, or HR's.
    can_edit_avatar: bool = False
    work: EmployeeWork
    # Read-only alongside the work details; null only before the org has a
    # default policy. Changed through the leave policy assign route.
    leave_policy: EmployeeLeavePolicy | None = None
    office: OfficeRef | None = None
    managers: list[ManagerRef]
    personal: EmployeePersonalRead | None
    access: EmployeeAccessRead
    # Set only after a status change to "exited": whether the account was
    # also deactivated, or still needs an admin to do it.
    access_revoked: bool | None = None


class DirectoryEntry(BaseModel):
    """One row of the employee directory."""

    user_id: uuid.UUID
    avatar_url: str | None = None
    name: str
    email: str
    is_active: bool
    employee_code: str | None
    designation: str | None
    department: str | None
    status: EmployeeStatus
    primary_manager: ManagerRef | None
    manager_count: int
    work_arrangement: WorkArrangement
    office: OfficeRef | None


class MemberCandidate(BaseModel):
    """A member who doesn't have an employee record yet."""

    user_id: uuid.UUID
    name: str
    email: str


class EmployeeCreate(BaseModel):
    """Create the record for an existing member."""

    user_id: uuid.UUID
    work: EmployeeWork = Field(default_factory=EmployeeWork)


class ManagerInput(BaseModel):
    """One requested reporting manager."""

    user_id: uuid.UUID
    is_primary: bool = False


class NameUpdate(BaseModel):
    """A person's name as everyone sees it: on leave, approvals, reports, Slack."""

    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str) -> str:
        tidy = " ".join(value.split())
        if not tidy:
            raise ValueError("Enter a name.")
        return tidy


class ManagersUpdate(BaseModel):
    """Replace an employee's reporting managers."""

    managers: list[ManagerInput] = Field(default_factory=list, max_length=10)


class AvatarRead(BaseModel):
    """The member's profile photo URL after an upload or removal.

    ``None`` means "no photo" — the UI falls back to initials. The value
    may be absolute (a Slack CDN address) or root-relative (one we host);
    see ``app.services.avatars``.
    """

    avatar_url: str | None = None
