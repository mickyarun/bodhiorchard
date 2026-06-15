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

"""User data access repository."""

import uuid
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select, true
from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.developer_xp import DeveloperXP
from app.models.role import Role, RoleScopeType
from app.models.skill_profile import SkillProfile
from app.models.user import OrgToUser, User, UserEmailAlias, UserRole
from app.repositories.base import BaseRepository, SelectT, rowcount


def _effective_role_case(base_role_alias: Any) -> Any:
    """SQL CASE that resolves an ``OrgToUser`` row to its canonical role name.

    CUSTOM roles fall through to ``base_role.name`` so an org-defined
    "Senior PM" still resolves to :class:`UserRole.PM`.  Memberships with
    ``role_id IS NULL`` resolve to ``NULL`` — callers decide whether that
    means "no role" or some default.

    The base_role join must already exist on the calling query:
    ``.outerjoin(Role, Role.id == OrgToUser.role_id)`` and
    ``.outerjoin(base_role_alias, base_role_alias.id == Role.base_role_id)``.
    """
    return case(
        (Role.scope_type == RoleScopeType.CUSTOM, base_role_alias.name),
        else_=Role.name,
    )


def _role_from_name(name: str | None) -> UserRole | None:
    """Convert a canonical role string to :class:`UserRole`, or ``None``.

    Returns ``None`` for unknown strings rather than raising — custom roles
    without a ``base_role_id`` cannot be canonicalised and the caller
    should treat them as ungated.
    """
    if not name:
        return None
    try:
        return UserRole(name)
    except ValueError:
        return None


class UserRepository(BaseRepository[User]):
    """Repository for User queries, optionally scoped to an organization.

    When org_id is provided, queries join through OrgToUser to filter
    by organization membership.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID | None = None) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Optional organization UUID for scoping queries.
        """
        super().__init__(User, db, org_id=org_id)

    def _scoped(self, stmt: Select[SelectT]) -> Select[SelectT]:
        """Apply tenant scope by joining OrgToUser when org_id is set."""
        if self._org_id is not None:
            stmt = stmt.join(OrgToUser, OrgToUser.user_id == User.id).where(
                OrgToUser.org_id == self._org_id
            )
        return stmt

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email within the scoped organization.

        Args:
            email: The email address to search for.

        Returns:
            The matching User or None.
        """
        stmt = self._scoped(select(User).where(User.email == email))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
        """Bulk-fetch users by ID. Returns matched rows in arbitrary order.

        Caller is responsible for handling missing IDs (rows where the
        user has been deleted will simply be absent from the result).
        """
        if not user_ids:
            return []
        result = await self._db.execute(select(User).where(User.id.in_(user_ids)))
        return list(result.scalars().all())

    async def get_by_email_in_org(self, org_id: uuid.UUID, email: str) -> User | None:
        """Fetch a user by email in a specific organization.

        Args:
            org_id: The organization UUID to search within.
            email: The email address to search for.

        Returns:
            The matching User or None.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id, User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id_in_org(self, user_id: uuid.UUID, org_id: uuid.UUID) -> User | None:
        """Fetch a user by ID if they are a member of the given organization.

        Args:
            user_id: The user UUID.
            org_id: The organization UUID.

        Returns:
            The matching User or None if not found or not a member.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(User.id == user_id, OrgToUser.org_id == org_id)
        )
        return result.scalar_one_or_none()

    async def list_active_slack_user_pairs(self, org_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        """``(user_id, slack_id)`` pairs for active org members with a slack_id."""
        stmt = (
            select(User.id, User.slack_id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id.is_not(None),
                User.is_active.is_(True),
            )
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all() if row[1]]

    async def list_slack_recipients(
        self, org_id: uuid.UUID, *, category: str, default_enabled: bool = True
    ) -> list[tuple[uuid.UUID, str]]:
        """``(user_id, slack_id)`` pairs for active members who allow ``category``.

        Same shape as :meth:`list_active_slack_user_pairs` but applies the
        per-user preference filter in SQL via
        ``COALESCE(notification_prefs ->> category, <default>) <> 'false'``:

        * A member is excluded only when the resolved value is ``'false'``.
        * A missing key falls back to ``default_enabled`` — so an opt-out
          category (``default_enabled=True``) keeps members who never set a
          preference, while an opt-in category (``default_enabled=False``)
          keeps only members who explicitly turned it on.

        This mirrors ``app.services.notifications.is_category_enabled`` exactly.
        ``category`` is the stable string key and ``default_enabled`` the
        registry default (a ``NotificationCategory`` value / ``category_default``
        result); passing them in keeps the repo free of the registry import.
        """
        default_text = "true" if default_enabled else "false"
        stmt = (
            select(User.id, User.slack_id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id.is_not(None),
                User.is_active.is_(True),
                func.coalesce(User.notification_prefs[category].astext, default_text) != "false",
            )
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all() if row[1]]

    async def get_notification_prefs(self, user_id: uuid.UUID) -> dict[str, bool]:
        """Return a member's stored opt-out map (``{}`` when never set)."""
        result = await self._db.execute(select(User.notification_prefs).where(User.id == user_id))
        return result.scalar_one_or_none() or {}

    async def set_notification_prefs(
        self, user_id: uuid.UUID, prefs: dict[str, bool]
    ) -> dict[str, bool]:
        """Overwrite a member's notification preference map; returns it back."""
        await self._db.execute(
            sql_update(User).where(User.id == user_id).values(notification_prefs=prefs)
        )
        await self._db.flush()
        return prefs

    async def get_by_slack_id_with_role(
        self, org_id: uuid.UUID, slack_id: str
    ) -> tuple[User, UserRole | None] | None:
        """Look up an org member by Slack ID and return ``(user, effective_role)``.

        ``effective_role`` is resolved from ``OrgToUser.role_id`` — SYSTEM
        roles map directly via ``Role.name``; CUSTOM roles inherit via
        ``base_role.name`` so a custom "Senior PM" still gates as
        :class:`UserRole.PM`.  Memberships with ``role_id IS NULL`` return
        ``None`` — the caller decides whether to default or reject.
        """
        base_role = aliased(Role)
        stmt = (
            select(User, _effective_role_case(base_role))
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id == slack_id,
            )
        )
        result = await self._db.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        return (row[0], _role_from_name(row[1]))

    async def list_in_org_by_ids_with_role(
        self, org_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> list[tuple[User, UserRole | None, str | None]]:
        """Bulk-fetch users by id with their effective role + role_name.

        Returns triples ``(user, effective_role, role_name)``: ``role`` is
        the canonical :class:`UserRole` resolved through the same SYSTEM /
        CUSTOM → base_role rules as :meth:`list_active_with_role`; the
        second string is the raw role row name so a custom "Senior PM"
        renders distinctly from the inherited "pm" UserRole. Empty input
        short-circuits without a query. Order is unspecified; callers
        sort as needed.
        """
        if not user_ids:
            return []
        base_role = aliased(Role)
        stmt = (
            select(User, _effective_role_case(base_role), Role.name)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(
                OrgToUser.org_id == org_id,
                User.id.in_(user_ids),
            )
        )
        result = await self._db.execute(stmt)
        return [(row[0], _role_from_name(row[1]), row[2]) for row in result.all()]

    async def list_active_with_role(self, org_id: uuid.UUID, role: UserRole) -> list[User]:
        """Active org members **explicitly** assigned a role whose identity equals ``role``.

        Resolution rules (discriminated on ``Role.scope_type``):
          - SYSTEM role  → match by ``Role.name`` (which IS the canonical
            UserRole value, e.g. "tech_lead").
          - CUSTOM role  → join through ``Role.base_role_id`` to its
            inherited system role and match that parent's name.

        Requiring ``OrgToUser.role_id IS NOT NULL`` (via inner join) keeps
        members who were imported through scan / Slack / GitHub paths
        without an explicit role assignment out of the candidate pool —
        otherwise they would silently become eligible for every
        development BUD despite the org admin never granting them a role.
        """
        # Alias the parent system role so we can join self-referentially.
        base_role = aliased(Role)
        stmt = (
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .join(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(
                OrgToUser.org_id == org_id,
                User.is_active == true(),
                or_(
                    and_(
                        Role.scope_type == RoleScopeType.SYSTEM,
                        Role.name == role.value,
                    ),
                    and_(
                        Role.scope_type == RoleScopeType.CUSTOM,
                        base_role.name == role.value,
                    ),
                ),
            )
            .distinct()
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_id_by_github_login(
        self, org_id: uuid.UUID, github_login: str
    ) -> uuid.UUID | None:
        """Resolve a GitHub login to a user_id within an org. None if no match."""
        if not github_login:
            return None
        stmt = (
            select(User.id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(User.github_username == github_login, OrgToUser.org_id == org_id)
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_role(self, user_id: uuid.UUID, org_id: uuid.UUID) -> UserRole | None:
        """Return the user's canonical :class:`UserRole` within the org, or ``None``.

        Resolves ``OrgToUser.role_id`` → ``Role.name`` (with CUSTOM →
        ``base_role.name``).  Memberships without ``role_id`` return ``None``.
        """
        base_role = aliased(Role)
        stmt = (
            select(_effective_role_case(base_role))
            .select_from(OrgToUser)
            .outerjoin(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(
                OrgToUser.user_id == user_id,
                OrgToUser.org_id == org_id,
            )
        )
        result = await self._db.execute(stmt)
        return _role_from_name(result.scalar_one_or_none())

    async def get_membership_with_role(
        self, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> tuple[OrgToUser, UserRole | None] | None:
        """Fetch ``(membership, effective_role)`` for an authenticated request.

        Single query that powers ``deps.get_current_user`` — joins through
        ``Role`` + ``base_role`` so the canonical role is resolved without
        a follow-up SELECT per request.
        """
        base_role = aliased(Role)
        stmt = (
            select(OrgToUser, _effective_role_case(base_role))
            .outerjoin(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(
                OrgToUser.user_id == user_id,
                OrgToUser.org_id == org_id,
            )
        )
        result = await self._db.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        return (row[0], _role_from_name(row[1]))

    async def count_active_by_role(self, org_id: uuid.UUID) -> dict[UserRole, int]:
        """Return ``{role: member_count}`` for an org, grouped by canonical role.

        Used by capacity planning.  Counts every membership row in the
        org (matching the pre-refactor query); only those that resolve to
        a canonical :class:`UserRole` are kept — CUSTOM-without-base and
        ``role_id``-less rows fall out because they have no pool semantics.
        """
        base_role = aliased(Role)
        # The CASE must be the SAME expression object in SELECT and GROUP BY;
        # calling ``_effective_role_case`` twice would emit two distinct
        # parameterised CASEs and Postgres would reject the GROUP BY as not
        # covering the SELECT's underlying ``roles.scope_type`` reference.
        role_expr = _effective_role_case(base_role).label("effective_role")
        stmt = (
            select(role_expr, func.count())
            .select_from(OrgToUser)
            .outerjoin(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(OrgToUser.org_id == org_id)
            .group_by(role_expr)
        )
        result = await self._db.execute(stmt)
        counts: dict[UserRole, int] = {}
        for name, count in result.all():
            role = _role_from_name(name)
            if role is not None:
                counts[role] = counts.get(role, 0) + int(count)
        return counts

    async def get_first_member_id(self, org_id: uuid.UUID) -> uuid.UUID | None:
        """Return any one user_id from ``OrgToUser`` for the given org, else None."""
        stmt = select(OrgToUser.user_id).where(OrgToUser.org_id == org_id).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def map_emails_to_ids(self, org_id: uuid.UUID, emails: set[str]) -> dict[str, uuid.UUID]:
        """Bulk-resolve emails to user_ids within an org.

        Returns lowercase ``email -> user_id`` for matches.
        """
        if not emails:
            return {}
        stmt = (
            select(User.email, User.id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id)
            .where(User.email.in_(emails))
        )
        result = await self._db.execute(stmt)
        return {row[0].lower(): row[1] for row in result.all()}

    async def list_active_members_for_tree(
        self, org_id: uuid.UUID, *, limit: int = 50
    ) -> list[Any]:
        """Heavy aggregate row used by the dashboard tree's member section.

        Joins ``OrgToUser`` (membership), ``SkillProfile`` (touch totals),
        and ``DeveloperXP`` (level/house). Returns rows with attributes
        ``id``, ``name``, ``email``, ``avatar_url``, ``character_model``,
        ``slack_id``, ``total_touches``, ``level``, ``level_name``,
        ``house_level``. Ordered by ``User.id`` to match the Colyseus
        snapshot's slot assignment.
        """
        stmt = (
            select(
                User.id,
                User.name,
                User.email,
                User.avatar_url,
                User.character_model,
                User.slack_id,
                func.coalesce(func.sum(SkillProfile.touch_count), 0).label("total_touches"),
                DeveloperXP.level,
                DeveloperXP.level_name,
                DeveloperXP.house_level,
            )
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                SkillProfile,
                (SkillProfile.user_id == User.id) & (SkillProfile.org_id == org_id),
            )
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
            )
            .where(OrgToUser.org_id == org_id)
            .where(User.is_active.is_(True))
            .where(~User.name.ilike("%[bot]%"))
            .group_by(
                User.id,
                User.name,
                User.email,
                User.avatar_url,
                User.character_model,
                User.slack_id,
                DeveloperXP.level,
                DeveloperXP.level_name,
                DeveloperXP.house_level,
            )
            .order_by(User.id)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.all())

    async def list_contributors_for_tree(
        self, org_id: uuid.UUID, *, limit: int = 100
    ) -> list[Any]:
        """All users with feature-mapped skill profiles in this org.

        Unlike :meth:`list_active_members_for_tree`, this query does NOT
        require an ``OrgToUser`` row — it returns every user with a
        ``SkillProfile`` for this org's features, including synthetic /
        example-workspace developers that the scan pipeline credits with
        commits but who were never formally onboarded as org members.

        Used by the dashboard tree's detail panel and the graph view's
        feature-developer popover so a feature with real contributors
        still surfaces them even when none are OrgToUser members.

        Returns rows shaped like ``list_active_members_for_tree`` so the
        same ``MemberActivity`` builder can consume both — DeveloperXP
        columns come back ``None`` because contributors-not-members
        typically have no XP record.
        """
        stmt = (
            select(
                User.id,
                User.name,
                User.email,
                User.avatar_url,
                User.character_model,
                User.slack_id,
                func.coalesce(func.sum(SkillProfile.touch_count), 0).label("total_touches"),
                DeveloperXP.level,
                DeveloperXP.level_name,
                DeveloperXP.house_level,
            )
            .join(SkillProfile, SkillProfile.user_id == User.id)
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
            )
            .where(SkillProfile.org_id == org_id)
            .where(SkillProfile.feature_id.is_not(None))
            .where(User.is_active.is_(True))
            .where(~User.name.ilike("%[bot]%"))
            .group_by(
                User.id,
                User.name,
                User.email,
                User.avatar_url,
                User.character_model,
                User.slack_id,
                DeveloperXP.level,
                DeveloperXP.level_name,
                DeveloperXP.house_level,
            )
            .order_by(User.id)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.all())

    async def list_active_member_xp_summary(
        self, org_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, str | None, int | None, str | None]]:
        """For each active, non-bot org member return ``(id, name,
        avatar_url, level, level_name)`` ordered by name.

        Used by the standup service which only needs the level summary,
        not the full DeveloperXP row.
        """
        stmt = (
            select(
                User.id,
                User.name,
                User.avatar_url,
                DeveloperXP.level,
                DeveloperXP.level_name,
            )
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
            )
            .where(OrgToUser.org_id == org_id)
            .where(User.is_active.is_(True))
            .where(~User.name.ilike("%[bot]%"))
            .order_by(User.name)
        )
        result = await self._db.execute(stmt)
        return [
            (row.id, row.name, row.avatar_url, row.level, row.level_name) for row in result.all()
        ]

    async def is_member_of_org(self, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        """Return True if the user has an OrgToUser membership in the org."""
        result = await self._db.execute(
            select(OrgToUser.user_id).where(
                OrgToUser.org_id == org_id,
                OrgToUser.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_active_members_with_xp(
        self, org_id: uuid.UUID
    ) -> list[tuple[User, DeveloperXP | None]]:
        """Active org members (excluding bots) with their XP rows.

        Stable ordering by ``user.id`` so callers (e.g. Colyseus snapshot)
        get deterministic slot assignment across reloads.
        """
        stmt = (
            select(User, DeveloperXP)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                DeveloperXP,
                (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
            )
            .where(OrgToUser.org_id == org_id)
            .where(User.is_active.is_(True))
            .where(~User.name.ilike("%[bot]%"))
            .order_by(User.id)
        )
        result = await self._db.execute(stmt)
        return list(result.tuples().all())

    async def get_by_slack_id_in_org(self, org_id: uuid.UUID, slack_id: str) -> User | None:
        """Fetch the org member whose ``slack_id`` matches.

        Args:
            org_id: Organization UUID for membership scoping.
            slack_id: Slack user ID to look up.

        Returns:
            The matching User or None.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id, User.slack_id == slack_id)
        )
        return result.scalar_one_or_none()

    async def get_membership(self, user_id: uuid.UUID, org_id: uuid.UUID) -> OrgToUser | None:
        """Fetch the OrgToUser membership row for a user/org pair.

        Args:
            user_id: The user UUID.
            org_id: The organization UUID.

        Returns:
            The OrgToUser row, or None if the user is not a member.
        """
        result = await self._db.execute(
            select(OrgToUser).where(
                OrgToUser.user_id == user_id,
                OrgToUser.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_slack_id_to_name(self, org_id: uuid.UUID, slack_ids: set[str]) -> dict[str, str]:
        """Map Slack user IDs to Bodhiorchard user display names within an org.

        Args:
            org_id: Organization UUID for membership scoping.
            slack_ids: Set of Slack user IDs to resolve.

        Returns:
            Dict of slack_id → user.name (only entries with both fields).
        """
        if not slack_ids:
            return {}
        stmt = (
            select(User.slack_id, User.name)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id.in_(slack_ids),
            )
        )
        result = await self._db.execute(stmt)
        return {row.slack_id: row.name for row in result.all() if row.slack_id and row.name}

    async def get_names_by_ids(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Batch-fetch user names by IDs.

        Args:
            user_ids: Set of user UUIDs to look up.

        Returns:
            Dict mapping user_id to user name.
        """
        if not user_ids:
            return {}
        result = await self._db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        return {row.id: row.name for row in result.all()}

    async def list_by_org(self, org_id: uuid.UUID) -> list[User]:
        """List all users in a given organization.

        Args:
            org_id: The organization UUID.

        Returns:
            List of User instances belonging to the organization.
        """
        result = await self._db.execute(
            select(User)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(OrgToUser.org_id == org_id)
        )
        return list(result.scalars().all())

    async def get_by_id_with_membership(
        self, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> User | None:
        """Load a user and set transient org/role attrs from OrgToUser.

        ``user.role`` is the canonical :class:`UserRole` resolved through
        ``Role`` (with CUSTOM → ``base_role``).  Memberships without a
        ``role_id`` get ``UserRole.DEVELOPER`` so downstream identity
        checks have a stable value to compare against.
        """
        base_role = aliased(Role)
        result = await self._db.execute(
            select(User, OrgToUser, _effective_role_case(base_role))
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(User.id == user_id, OrgToUser.org_id == org_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        user: User = row[0]
        membership: OrgToUser = row[1]
        user.org_id = membership.org_id
        user.role = _role_from_name(row[2]) or UserRole.DEVELOPER
        user.role_id = membership.role_id
        user.role_ref = membership.role_ref
        return user

    async def list_with_membership(self, org_id: uuid.UUID) -> list[User]:
        """List users in an org with transient role attrs set from OrgToUser.

        ``user.role`` resolves via the canonical-role join (see
        :meth:`get_by_id_with_membership`).
        """
        base_role = aliased(Role)
        result = await self._db.execute(
            select(User, OrgToUser, _effective_role_case(base_role))
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(Role, Role.id == OrgToUser.role_id)
            .outerjoin(base_role, base_role.id == Role.base_role_id)
            .where(OrgToUser.org_id == org_id)
        )
        users = []
        for user, membership, role_name in result.all():
            user.org_id = membership.org_id
            user.role = _role_from_name(role_name) or UserRole.DEVELOPER
            user.role_id = membership.role_id
            user.role_ref = membership.role_ref
            users.append(user)
        return users

    async def get_email_map(self, org_id: uuid.UUID) -> dict[str, User]:
        """Build a lowercase-email to User mapping for an organization.

        Includes both primary emails and email aliases, so git commits
        authored with any known email resolve to the correct user.

        Args:
            org_id: The organization UUID.

        Returns:
            Dict mapping lowercase email strings to User instances.
        """
        users = await self.list_by_org(org_id)
        email_map = {u.email.lower(): u for u in users}

        # Add aliases
        user_by_id = {u.id: u for u in users}
        result = await self._db.execute(
            select(UserEmailAlias).where(UserEmailAlias.org_id == org_id)
        )
        for alias in result.scalars():
            user = user_by_id.get(alias.user_id)
            if user:
                email_map[alias.email.lower()] = user

        return email_map

    async def add_email_alias(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        email: str,
    ) -> UserEmailAlias | None:
        """Add an email alias for a user. Skips if already exists.

        Args:
            org_id: Organization UUID.
            user_id: Target user UUID.
            email: The alias email.

        Returns:
            The created alias, or None if it already exists.
        """
        existing = await self._db.execute(
            select(UserEmailAlias).where(
                UserEmailAlias.org_id == org_id,
                UserEmailAlias.email == email,
            )
        )
        if existing.scalar_one_or_none():
            return None
        alias = UserEmailAlias(user_id=user_id, org_id=org_id, email=email)
        self._db.add(alias)
        return alias

    async def rebind_aliases_to_target(
        self,
        org_id: uuid.UUID,
        target_user_id: uuid.UUID,
        emails: set[str],
    ) -> int:
        """Force every alias row for ``emails`` in ``org_id`` to point at
        ``target_user_id``.

        Used by member-merge to claim emails that may already be attached
        to a previously-merged-away user. Plain ``add_email_alias`` skips
        on ``(org_id, email)`` conflict and leaves the stale row in place;
        this primitive does delete-then-insert so the most recent merge
        wins.

        Not atomic against a concurrent ``add_email_alias`` for the same
        ``(org_id, email)`` at default ``READ COMMITTED``: an interleaved
        insert between the DELETE and the INSERT here would surface as
        an ``IntegrityError`` on flush. Callers must serialize merges
        (the merge-members handler is one-admin-at-a-time in practice;
        no batch caller exists today).
        """
        if not emails:
            return 0
        await self._db.execute(
            sql_delete(UserEmailAlias).where(
                UserEmailAlias.org_id == org_id,
                UserEmailAlias.email.in_(emails),
            )
        )
        for email in emails:
            self._db.add(UserEmailAlias(user_id=target_user_id, org_id=org_id, email=email))
        await self._db.flush()
        return len(emails)

    async def delete_alias(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        email: str,
    ) -> bool:
        """Remove an alias row only if it currently points at ``user_id``.

        ``user_id`` is part of the WHERE clause (not just ``org_id, email``)
        so that an admin on a stale page cannot delete a row that has
        since been reassigned to a different member by someone else.
        """
        result = await self._db.execute(
            sql_delete(UserEmailAlias).where(
                UserEmailAlias.org_id == org_id,
                UserEmailAlias.user_id == user_id,
                UserEmailAlias.email == email,
            )
        )
        await self._db.flush()
        return (rowcount(result) or 0) > 0

    async def create_stub_member(
        self,
        org_id: uuid.UUID,
        *,
        email: str,
        name: str,
        github_username: str,
        password_hash: str,
    ) -> User:
        """Insert a stub User + ``OrgToUser`` membership in one shot.

        Used to surface GitHub PR authors who don't yet have an account
        so admins can merge them into a real member via Settings →
        Members. Caller chooses ``password_hash`` — typically a random
        bcrypt-hashed string so the account cannot authenticate.

        Concurrent BUD closures may race on the same unknown
        ``email`` — the insert is wrapped in a SAVEPOINT and, on the
        ``uq_users_email`` violation, the loser re-fetches the winning
        row instead of poisoning the outer transaction.
        """
        try:
            async with self._db.begin_nested():
                user = User(
                    email=email,
                    name=name,
                    password_hash=password_hash,
                    github_username=github_username,
                    is_active=True,
                )
                self._db.add(user)
                await self._db.flush()
                self._db.add(OrgToUser(user_id=user.id, org_id=org_id))
                await self._db.flush()
            return user
        except IntegrityError:
            existing = await self.get_by_email_in_org(org_id, email)
            if existing is None:
                raise
            return existing

    async def find_user_by_alias_email(self, org_id: uuid.UUID, email: str) -> User | None:
        """Return the user who has ``email`` listed as a UserEmailAlias.

        Walks one hop of the Settings → Members merge backlink: when
        member B is merged into A, B's primary email is recorded as an
        alias on A. Given B's email, this returns A.

        Returns the immediate target without filtering on ``is_active``
        so multi-hop chains (A → B → C) can be traversed externally;
        callers that need a guaranteed-active user must loop until
        ``user.is_active`` is true.
        """
        if not email:
            return None
        result = await self._db.execute(
            select(User)
            .join(UserEmailAlias, UserEmailAlias.user_id == User.id)
            .where(
                UserEmailAlias.org_id == org_id,
                UserEmailAlias.email == email,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_aliases(self, user_id: uuid.UUID) -> list[UserEmailAlias]:
        """List all email aliases for a user.

        Args:
            user_id: The user UUID.

        Returns:
            List of alias records.
        """
        result = await self._db.execute(
            select(UserEmailAlias).where(UserEmailAlias.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_alias_map_for_org(
        self,
        org_id: uuid.UUID,
    ) -> dict[uuid.UUID, list[str]]:
        """Build a user_id → [alias emails] mapping for an entire org.

        Single query instead of per-user lookups.

        Args:
            org_id: The organization UUID.

        Returns:
            Dict mapping user UUIDs to lists of alias email strings.
        """
        result = await self._db.execute(
            select(UserEmailAlias).where(UserEmailAlias.org_id == org_id)
        )
        alias_map: dict[uuid.UUID, list[str]] = {}
        for alias in result.scalars():
            alias_map.setdefault(alias.user_id, []).append(alias.email)
        return alias_map
