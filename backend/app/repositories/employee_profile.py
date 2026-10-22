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

"""Data access for employee profiles (one per org member)."""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

from sqlalchemy import extract, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped

from app.models.employee_profile import EmployeeProfile, EmployeeStatus
from app.models.user import OrgToUser, User
from app.repositories.base import BaseRepository, rowcount

# Someone serving their notice is still a colleague with a birthday; only an
# exited employee drops out of the announcements.
_CELEBRATED_STATUSES = (EmployeeStatus.ACTIVE, EmployeeStatus.ON_NOTICE)


def _is_leap(year: int) -> bool:
    """Gregorian leap-year test."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


@dataclass(frozen=True)
class DirectoryRow:
    """A profile with the member fields the directory shows."""

    profile: EmployeeProfile
    name: str
    email: str
    is_active: bool
    avatar_url: str | None = None


@dataclass(frozen=True)
class MemberSummary:
    """A member who could be given an employee record."""

    user_id: uuid.UUID
    name: str
    email: str


@dataclass(frozen=True)
class Celebrant:
    """One person with a birthday or work anniversary on a given date.

    Carries the occasion as a bare ``(month, day)`` pair, never a ``date``:
    the stored ``date_of_birth`` includes the year, and a field typed as a
    date would let any future consumer (a log line, an event payload, an
    API) leak someone's age. With no year anywhere on the type, that
    guarantee is structural rather than a convention.

    ``years`` is the completed count for an anniversary (1, 2, 3 …) and is
    always ``None`` for a birthday.
    """

    user_id: uuid.UUID
    name: str
    avatar_url: str | None
    slack_id: str | None
    # The stored month/day being celebrated. For a Feb-29 birthday in a
    # common year this stays (2, 29), not the Feb 28 it was matched on.
    month: int
    day: int
    years: int | None = None


class EmployeeProfileRepository(BaseRepository[EmployeeProfile]):
    """Employee profiles, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose profiles this repository exposes.
        """
        super().__init__(EmployeeProfile, db, org_id=org_id)
        self._org = org_id

    async def get_by_user(self, user_id: uuid.UUID) -> EmployeeProfile | None:
        """The profile for ``user_id`` in this org, if any."""
        result = await self._db.execute(
            self._scoped(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def by_users(self, user_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, EmployeeProfile]:
        """Profiles for ``user_ids`` in this org, keyed by user id."""
        if not user_ids:
            return {}
        result = await self._db.execute(
            self._scoped(select(EmployeeProfile).where(EmployeeProfile.user_id.in_(user_ids)))
        )
        return {p.user_id: p for p in result.scalars().all()}

    async def code_taken(self, code: str, *, exclude_profile: uuid.UUID | None) -> bool:
        """True if another profile in this org already uses ``code``."""
        stmt = self._scoped(
            select(EmployeeProfile.id).where(EmployeeProfile.employee_code == code)
        )
        if exclude_profile is not None:
            stmt = stmt.where(EmployeeProfile.id != exclude_profile)
        return (await self._db.execute(stmt)).first() is not None

    async def list_directory(
        self,
        *,
        search: str | None = None,
        department: str | None = None,
        status: EmployeeStatus | None = None,
    ) -> list[DirectoryRow]:
        """Profiles joined to their member, ordered by name."""
        stmt = (
            select(EmployeeProfile, User.name, User.email, User.is_active, User.avatar_url)
            .join(User, User.id == EmployeeProfile.user_id)
            .where(EmployeeProfile.org_id == self._org)
            .order_by(User.name)
        )
        if search:
            # Escape LIKE wildcards so "%" or "_" in a search match literally.
            term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{term}%"
            stmt = stmt.where(
                or_(
                    User.name.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                    EmployeeProfile.employee_code.ilike(pattern, escape="\\"),
                    EmployeeProfile.designation.ilike(pattern, escape="\\"),
                )
            )
        if department:
            stmt = stmt.where(EmployeeProfile.department == department)
        if status is not None:
            stmt = stmt.where(EmployeeProfile.status == status)
        rows = (await self._db.execute(stmt)).all()
        return [
            DirectoryRow(profile=r[0], name=r[1], email=r[2], is_active=r[3], avatar_url=r[4])
            for r in rows
        ]

    async def list_members_without_profile(self) -> list[MemberSummary]:
        """Active org members who don't have an employee record yet."""
        stmt = (
            select(User.id, User.name, User.email)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                EmployeeProfile,
                (EmployeeProfile.user_id == User.id) & (EmployeeProfile.org_id == self._org),
            )
            .where(
                OrgToUser.org_id == self._org,
                User.is_active.is_(True),
                EmployeeProfile.id.is_(None),
            )
            .order_by(User.name)
        )
        rows = (await self._db.execute(stmt)).all()
        return [MemberSummary(user_id=r[0], name=r[1], email=r[2]) for r in rows]

    async def list_celebrants(
        self,
        occasions: Collection[date],
        *,
        birthdays: bool = True,
        anniversaries: bool = True,
    ) -> tuple[list[Celebrant], list[Celebrant]]:
        """Birthdays and work anniversaries falling on any of ``occasions``.

        Matches on (month, day) so the stored year is irrelevant for
        birthdays and only bounds the count for anniversaries. Only ACTIVE
        employees with an active login are returned, and each stream honours
        its own per-employee opt-out flag.

        **Leap day:** a Feb-29 birth or joining date would never match in a
        common year, so when ``occasions`` contains a Feb 28 that is not
        itself followed by a Feb 29, that date also matches Feb 29 records.
        The returned ``occasion_date`` keeps the stored Feb 29 so the post
        still reads "February 29".

        Args:
            occasions: The local dates this digest covers.
            birthdays: Include the birthday stream.
            anniversaries: Include the work-anniversary stream.

        Returns:
            ``(birthday_celebrants, anniversary_celebrants)``, each ordered
            by name.
        """
        if not occasions:
            return [], []

        # (month, day) pairs to match, each mapped back to the date whose
        # digest they belong to and the year used for the anniversary count.
        wanted: dict[tuple[int, int], date] = {}
        for day in occasions:
            wanted[(day.month, day.day)] = day
            if (day.month, day.day) == (2, 28) and not _is_leap(day.year):
                # Common year: Feb-29 people are celebrated on Feb 28.
                wanted.setdefault((2, 29), day)

        birthday_rows = (
            await self._celebrants(EmployeeProfile.date_of_birth, wanted, count_years=False)
            if birthdays
            else []
        )
        anniversary_rows = (
            await self._celebrants(EmployeeProfile.date_of_joining, wanted, count_years=True)
            if anniversaries
            else []
        )
        return birthday_rows, anniversary_rows

    async def _celebrants(
        self,
        column: Mapped[date | None],
        wanted: dict[tuple[int, int], date],
        *,
        count_years: bool,
    ) -> list[Celebrant]:
        """Run one celebration stream against ``column``.

        ``count_years`` switches between the anniversary stream (which needs
        a completed-years count and therefore drops the joining year itself)
        and the birthday stream (which never exposes a year).
        """
        opt_in = (
            EmployeeProfile.celebrate_anniversary
            if count_years
            else EmployeeProfile.celebrate_birthday
        )
        stmt = (
            select(column, User.id, User.name, User.avatar_url, User.slack_id)
            .join(User, User.id == EmployeeProfile.user_id)
            .where(
                EmployeeProfile.org_id == self._org,
                EmployeeProfile.status.in_(_CELEBRATED_STATUSES),
                User.is_active.is_(True),
                opt_in.is_(True),
                column.is_not(None),
                # Narrow on month first so Postgres can discard most rows
                # before the per-row day comparison.
                extract("month", column).in_({m for m, _ in wanted}),
            )
            .order_by(User.name)
        )
        rows = (await self._db.execute(stmt)).all()

        out: list[Celebrant] = []
        for stored, user_id, name, avatar_url, slack_id in rows:
            if stored is None:  # pragma: no cover — excluded by the SQL filter
                continue
            occasion = wanted.get((stored.month, stored.day))
            if occasion is None:
                # Same month, different day — the SQL filter is deliberately
                # coarse, so this is the expected majority of rows.
                continue
            years: int | None = None
            if count_years:
                completed = occasion.year - stored.year
                if completed < 1:
                    # Their joining day itself, or a future-dated record.
                    continue
                years = completed
            out.append(
                Celebrant(
                    user_id=user_id,
                    name=name,
                    avatar_url=avatar_url,
                    slack_id=slack_id,
                    month=stored.month,
                    day=stored.day,
                    years=years,
                )
            )
        return out

    async def count_celebration_audience(self) -> tuple[int, int]:
        """How many people the celebration feed will ever announce.

        ``(birthdays, anniversaries)``: employees who are still with the
        org, have the relevant date on file, and have not muted that stream.
        Shown on the settings page so whoever switches the feature on can
        see how many people it is about to start announcing.
        """

        async def _count(column: Mapped[date | None], opt_in: Mapped[bool]) -> int:
            stmt = (
                select(func.count())
                .select_from(EmployeeProfile)
                .join(User, User.id == EmployeeProfile.user_id)
                .where(
                    EmployeeProfile.org_id == self._org,
                    EmployeeProfile.status.in_(_CELEBRATED_STATUSES),
                    User.is_active.is_(True),
                    opt_in.is_(True),
                    column.is_not(None),
                )
            )
            return int((await self._db.execute(stmt)).scalar_one())

        birthdays = await _count(EmployeeProfile.date_of_birth, EmployeeProfile.celebrate_birthday)
        anniversaries = await _count(
            EmployeeProfile.date_of_joining, EmployeeProfile.celebrate_anniversary
        )
        return birthdays, anniversaries

    async def repoint_user(self, source: uuid.UUID, target: uuid.UUID) -> int:
        """Move ``source``'s profile to ``target`` (member merge)."""
        result = await self._db.execute(
            sql_update(EmployeeProfile)
            .where(EmployeeProfile.org_id == self._org, EmployeeProfile.user_id == source)
            .values(user_id=target)
        )
        return rowcount(result) or 0
