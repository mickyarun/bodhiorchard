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

"""Organization member listing and role assignment endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    PermissionSet,
    get_current_user,
    get_db,
    get_permission_set,
    require_permissions,
)
from app.core.security import hash_password
from app.models.user import OrgToUser, User, UserRole
from app.repositories.developer_xp import DeveloperXPRepository, RewardEventRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.pull_request import PullRequestRepository
from app.repositories.role import RoleRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.user import UserRepository
from app.repositories.user_mcp_token import UserMCPTokenRepository
from app.schemas.members import (
    AddMemberRequest,
    AssignRoleRequest,
    MemberRead,
    MergeMembersRequest,
    SetPasswordRequest,
    SetPasswordResponse,
    UpdateCharacterRequest,
)
from app.services.employees.merge import (
    EmployeeMergeConflictError,
    transfer_employee_record,
)
from app.services.identity_takeover import assert_can_act_as
from app.services.member_credentials import (
    login_url,
    send_credentials_slack,
    set_temporary_password,
)
from app.services.role_grants import (
    assert_can_assign_role,
    assert_can_manage_member,
    log_sensitive_grant,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["members"])


def _user_to_member(user: User, aliases: list[str] | None = None) -> MemberRead:
    """Convert a User model to MemberRead schema.

    ``role`` exposes the canonical :class:`UserRole` value (set on
    ``user.role`` by the repo / auth dependency); ``role_name`` is the
    raw role row name so the UI can show e.g. "Senior PM" for CUSTOM roles.
    """
    role_name: str | None = None
    if user.role_ref:
        role_name = user.role_ref.name
    return MemberRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        roleId=user.role_id,
        roleName=role_name,
        avatarUrl=user.avatar_url,
        githubUsername=user.github_username,
        slackId=user.slack_id,
        isActive=user.is_active,
        mustChangePassword=user.must_change_password,
        createdAt=user.created_at.isoformat() if user.created_at else "",
        emailAliases=aliases or [],
    )


@router.post(
    "/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("team:invite"))],
)
async def add_member(
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Add a new member to the current user's organization.

    Args:
        body: New member data (email, name, password, optional roleId).
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The created MemberRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    existing = await user_repo.get_by_email_in_org(org.id, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered in this organization.",
        )

    role = None
    if body.role_id:
        role = await RoleRepository(db, org_id=org.id).get_by_id(body.role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")
    # Inviting is a grant — even without a role, since a role-less member
    # gets the unassigned-member permissions (engineering included).
    granted = await assert_can_assign_role(
        db, actor_id=current_user.id, actor=perms, target_user_id=None, role=role
    )

    new_user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        avatar_url=body.avatar_url,
        github_username=body.github_username,
        must_change_password=body.must_change_password,
    )
    created = await user_repo.create(new_user)

    # Create org membership
    membership = OrgToUser(
        user_id=created.id,
        org_id=org.id,
        role_id=body.role_id,
    )
    db.add(membership)
    await db.flush()

    log_sensitive_grant(
        actor_id=current_user.id, org_id=org.id, granted=granted, target=f"user:{created.id}"
    )

    # Re-fetch with canonical-role resolution so _user_to_member sees the
    # CUSTOM → base_role projection (a manual attr set would miss it).
    hydrated = await user_repo.get_by_id_with_membership(created.id, org.id)
    if hydrated is not None:
        created = hydrated

    logger.info(
        "member_added",
        email=body.email,
        added_by=current_user.email,
    )
    return _user_to_member(created)


@router.get(
    "/members",
    response_model=list[MemberRead],
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def list_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemberRead]:
    """List all members of the current user's organization.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of MemberRead with role details including email aliases.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    users = await user_repo.list_with_membership(org.id)

    # Load aliases for all users in one query
    alias_map = await user_repo.get_alias_map_for_org(org.id)

    return [_user_to_member(u, alias_map.get(u.id)) for u in users]


class MemberDirectoryEntry(BaseModel):
    """Minimal member row — just enough to populate an invite dialog.

    Email is included to disambiguate same-name members in pickers (orgs
    routinely have multiple "Arun" / "Alice" / etc. seeded for testing or
    sharing first names). The plain `/members` page already exposes email
    to every org member, so including it here is consistent visibility,
    not a new disclosure.
    """

    id: uuid.UUID
    name: str
    email: EmailStr
    avatar_url: str | None = None


@router.get("/members/directory", response_model=list[MemberDirectoryEntry])
async def list_member_directory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemberDirectoryEntry]:
    """Lightweight member directory — {id, name, email} per active org member.

    Unlike `/members`, this endpoint has no permission gate beyond "must be
    authenticated + in an org" so non-admin features (race invites, @-mentions)
    can populate their member pickers without requiring `team:manage`.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    users = await user_repo.list_with_membership(org.id)
    return [
        MemberDirectoryEntry(id=u.id, name=u.name or "", email=u.email, avatar_url=u.avatar_url)
        for u in users
        if u.is_active
    ]


@router.patch(
    "/members/{user_id}/role",
    dependencies=[Depends(require_permissions("team:assign_roles"))],
)
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Assign an RBAC role to a user.

    Args:
        user_id: The user UUID.
        body: Role assignment data with roleId.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated MemberRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id_with_membership(user_id, org.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    role_repo = RoleRepository(db, org_id=org.id)
    role = await role_repo.get_by_id(body.role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")
    await assert_can_manage_member(db, actor=perms, target=user)
    granted = await assert_can_assign_role(
        db, actor_id=current_user.id, actor=perms, target_user_id=user_id, role=role
    )

    # Update role on the OrgToUser membership
    membership = await user_repo.get_membership(user_id, org.id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found.")
    membership.role_id = body.role_id
    await db.flush()
    log_sensitive_grant(
        actor_id=current_user.id, org_id=org.id, granted=granted, target=f"user:{user_id}"
    )

    # Re-fetch with the canonical-role join so _user_to_member sees the
    # CUSTOM → base_role projection on the freshly-assigned role.
    hydrated = await user_repo.get_by_id_with_membership(user_id, org.id)
    if hydrated is not None:
        user = hydrated

    logger.info(
        "role_assigned",
        user_id=str(user_id),
        role=role.name,
        assigned_by=current_user.email,
    )

    return _user_to_member(user)


@router.patch(
    "/members/{user_id}/status",
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def toggle_member_status(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Toggle a member's active status (soft delete / reactivate).

    Args:
        user_id: The user UUID.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated MemberRead.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate yourself.",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id_with_membership(user_id, org.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    await assert_can_manage_member(db, actor=perms, target=user)

    new_state = not user.is_active
    user.is_active = new_state
    # On deactivation, revoke every MCP token this user owns. Soft-delete
    # via is_active=False doesn't fire the FK CASCADE on user_mcp_tokens,
    # so without this step a leaked / forgotten bodhi_token would keep
    # authenticating to /mcp/* indefinitely after offboarding.
    #
    # On REACTIVATION we deliberately do NOT re-revoke: there should be
    # nothing left to revoke (the deactivation drained the table), and
    # forcing a re-mint flow on reactivated users is the intended UX.
    # The verify_mcp_token is_active check is the safety net for any
    # token that somehow survives.
    revoked_tokens = 0
    if not new_state:
        revoked_tokens = await UserMCPTokenRepository(db).delete_all_for_user(user.id)
    await db.flush()
    await db.refresh(user)

    action = "reactivated" if user.is_active else "deactivated"
    logger.info(
        "member_status_changed",
        user_id=str(user_id),
        action=action,
        by=current_user.email,
        mcp_tokens_revoked=revoked_tokens,
        # Explicit boolean so an audit query can distinguish "no tokens
        # to revoke" (common) from "0 due to a bug" if the rowcount
        # interpretation ever changes (some drivers return -1 for
        # unknown — our getattr-or-0 in the repo would mask that).
        had_tokens_to_revoke=bool(revoked_tokens),
    )

    return _user_to_member(user)


@router.post(
    "/members/{user_id}/set-password",
    response_model=SetPasswordResponse,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def set_member_password(
    user_id: uuid.UUID,
    body: SetPasswordRequest | None = None,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> SetPasswordResponse:
    """Generate and set a temporary password for a member.

    Optionally sends credentials via Slack DM in the same call so the
    plaintext password never round-trips through the client.

    Args:
        user_id: The target user UUID.
        body: Optional request with send_via channel.
        current_user: The authenticated user (must be org_owner or admin).
        db: The async database session.

    Returns:
        SetPasswordResponse with the generated plaintext password
        and optional Slack send result.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id_with_membership(user_id, org.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    # A temporary password lets the caller sign in as the target.
    await assert_can_act_as(db, actor=perms, target=user, org_id=org.id)

    password = set_temporary_password(user)
    await db.flush()

    logger.info(
        "member_password_set",
        user_id=str(user_id),
        set_by=current_user.email,
    )

    # Optionally send via Slack DM (password stays server-side)
    send_via = body.send_via if body else None
    slack_sent: bool | None = None
    slack_error: str | None = None

    if send_via == "slack":
        slack_sent, slack_error = await send_credentials_slack(org, user, password)

    return SetPasswordResponse(
        password=password,
        loginUrl=login_url(),
        slackSent=slack_sent,
        slackError=slack_error,
    )


@router.patch(
    "/members/{user_id}/character",
    response_model=MemberRead,
)
async def update_character(
    user_id: uuid.UUID,
    body: UpdateCharacterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Update a member's preferred 3D character model for the garden dashboard.

    Members can set their own character, or admins can set it for others.
    Set character_model to null to revert to random assignment.

    Args:
        user_id: The user UUID.
        body: Character model preference.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated MemberRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id_with_membership(user_id, org.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Only the user themselves or admins can update character preference
    if user_id != current_user.id and getattr(current_user, "role", None) not in (
        UserRole.ORG_OWNER,
        UserRole.ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the user or an admin can update character preference.",
        )

    # Validate character/accessory unlocks based on XP level
    if body.character_model and body.character_model.startswith("kaykit:"):
        from app.services.xp_service import get_unlocked_items

        unlocks = await get_unlocked_items(db, user_id=user_id, org_id=org.id)
        parts = body.character_model.split(":")
        char_id = parts[1] if len(parts) > 1 else ""
        right_hand = parts[5] if len(parts) > 5 else ""
        left_hand = parts[6] if len(parts) > 6 else ""

        if char_id and char_id not in unlocks.characters:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Character '{char_id}' is locked. Earn more XP to unlock it.",
            )
        if right_hand and right_hand not in unlocks.accessories:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accessory '{right_hand}' is locked. Earn more XP to unlock it.",
            )
        if left_hand and left_hand not in unlocks.accessories:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accessory '{left_hand}' is locked. Earn more XP to unlock it.",
            )

    user.character_model = body.character_model
    await db.flush()
    await db.refresh(user)

    logger.info(
        "character_model_updated",
        user_id=str(user_id),
        character_model=body.character_model,
        by=current_user.email,
    )

    return _user_to_member(user)


@router.post(
    "/members/{target_id}/merge",
    response_model=MemberRead,
    dependencies=[Depends(require_permissions("team:assign_roles"))],
)
async def merge_members(
    target_id: uuid.UUID,
    body: MergeMembersRequest,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Merge source member into target member.

    Transfers the source's skill profiles to the target, adds the source's
    email as an alias on the target, and deactivates the source.

    Args:
        target_id: The user UUID to keep (merge target).
        body: Contains sourceId — the user UUID to merge away.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated target MemberRead with aliases.
    """
    if target_id == body.source_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge a member into itself.",
        )
    if current_user.id in (target_id, body.source_id) and not perms.is_owner:
        # Merging someone into yourself would hand you their account and record.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can't merge your own account. Ask another admin or the org owner.",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    target = await user_repo.get_by_id_with_membership(target_id, org.id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found.")

    source = await user_repo.get_by_id_with_membership(body.source_id, org.id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source user not found.")
    # Merging deactivates the source and hands its history (and employee
    # record) to the target: the caller must be able to act as both.
    await assert_can_act_as(db, actor=perms, target=source, org_id=org.id)
    await assert_can_act_as(db, actor=perms, target=target, org_id=org.id)

    # 0. Employee record first: it's the only step that can refuse, so a
    # conflict leaves nothing half-merged.
    try:
        employee = await transfer_employee_record(
            db, org_id=org.id, source=source.id, target=target.id
        )
    except EmployeeMergeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # 1. Transfer skill profiles: re-point source's profiles to target
    sp_repo = SkillProfileRepository(db, org_id=org.id)
    transferred = await sp_repo.transfer_profiles(source.id, target.id)

    # 1b. Fold the source's XP + skill-point totals and reward-event history
    # into the target. The leaderboard ranks by DeveloperXP keyed on user_id
    # and skips inactive members, so without this the deactivated source's
    # XP/SP vanish instead of combining onto the surviving member.
    xp_repo = DeveloperXPRepository(db, org_id=org.id)
    moved = await xp_repo.merge_into_target(source.id, target.id)
    event_repo = RewardEventRepository(db, org_id=org.id)
    repointed_events = await event_repo.repoint_user(source.id, target.id)

    # 1c. Re-point the source's pull requests. PR ingestion binds
    # author_user_id to whichever row owns the GitHub login — normally the
    # provisioned stub — so without this the surviving member shows zero
    # PRs while the deactivated row holds the entire history.
    pr_repo = PullRequestRepository(db, org_id=org.id)
    repointed_prs = await pr_repo.repoint_author(source.id, target.id)

    # 2. Rebind every email source owned (primary + aliases) onto target.
    # Force-overwrite any prior conflicting row so a stale alias from an
    # earlier bad merge cannot strand attribution on a deactivated user.
    source_aliases = await user_repo.list_aliases(source.id)
    emails_to_rebind = {source.email} | {a.email for a in source_aliases}
    await user_repo.rebind_aliases_to_target(org.id, target.id, emails_to_rebind)

    # 2b. Move the GitHub login onto the target, but only when the target
    # has none of its own. Leaving it on the source would keep routing
    # every future PR back to a deactivated member — the merge would
    # silently undo itself on the next webhook.
    #
    # When the target already owns a *different* login, the source keeps
    # its own. Clearing it would destroy the only record of that identity
    # (there is no alias table for GitHub logins), so the next PR under it
    # would provision a fresh stub and re-split the very member we just
    # merged. A deactivated row holding a login is harmless now that
    # get_id_by_github_login orders active members first, and
    # bud_learning_alias_resolver still walks the alias backlink from it
    # to the surviving member.
    claimed_login: str | None = None
    if source.github_username and not target.github_username:
        claimed_login = source.github_username
        target.github_username = claimed_login
        source.github_username = None

    # 3. Deactivate source + revoke its MCP tokens. Token revocation must
    # happen here (not via the FK CASCADE) because is_active=False is a
    # soft-delete; tokens would otherwise outlive the merge.
    source.is_active = False
    revoked_tokens = await UserMCPTokenRepository(db).delete_all_for_user(source.id)
    await db.flush()

    logger.info(
        "members_merged",
        target_id=str(target_id),
        source_id=str(body.source_id),
        source_email=source.email,
        profiles_transferred=transferred,
        xp_merged=moved["xp"],
        sp_merged=moved["sp"],
        reward_events_repointed=repointed_events,
        pull_requests_repointed=repointed_prs,
        github_login_claimed=claimed_login,
        emails_rebound=len(emails_to_rebind),
        mcp_tokens_revoked=revoked_tokens,
        employee_record_moved=employee.profile_moved,
        direct_reports_moved=employee.reports_moved,
        had_tokens_to_revoke=bool(revoked_tokens),
        by=current_user.email,
    )

    # Return updated target with aliases
    aliases = await user_repo.list_aliases(target.id)
    return _user_to_member(target, [a.email for a in aliases])


@router.delete(
    "/members/{user_id}/aliases",
    response_model=MemberRead,
    dependencies=[Depends(require_permissions("team:assign_roles"))],
)
async def unlink_alias(
    user_id: uuid.UUID,
    email: str,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Detach an email alias from a member.

    Email is passed as a query parameter so addresses with ``@``/``.``
    don't have to be path-escaped.

    After unlinking, the next scan that sees a commit with that email
    will treat it as an unknown author (and either auto-create a stub
    user or surface it in ``UnmatchedAuthorsError``, depending on the
    org's ``auto_create_members`` setting).
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    user = await user_repo.get_by_id_with_membership(user_id, org.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    await assert_can_manage_member(db, actor=perms, target=user)

    removed = await user_repo.delete_alias(org.id, user_id, email)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alias not found on this member.",
        )

    logger.info(
        "member_alias_unlinked",
        user_id=str(user_id),
        email=email,
        by=current_user.email,
    )

    aliases = await user_repo.list_aliases(user.id)
    return _user_to_member(user, [a.email for a in aliases])
