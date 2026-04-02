"""Organization member listing and role assignment endpoints."""

import secrets
import string
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import OrgToUser, User, UserRole
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.user import UserRepository
from app.schemas.members import (
    AddMemberRequest,
    AssignRoleRequest,
    MemberRead,
    MergeMembersRequest,
    SetPasswordRequest,
    SetPasswordResponse,
    UpdateCharacterRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["members"])


def _user_to_member(user: User, aliases: list[str] | None = None) -> MemberRead:
    """Convert a User model to MemberRead schema.

    Args:
        user: The User ORM instance.
        aliases: Optional list of alias email strings.

    Returns:
        MemberRead with role information.
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

    if body.role_id:
        role_repo = RoleRepository(db)
        role = await role_repo.get_by_id(body.role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")

    new_user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        avatar_url=body.avatar_url,
        github_username=body.github_username,
    )
    created = await user_repo.create(new_user)

    # Create org membership
    membership = OrgToUser(
        user_id=created.id,
        org_id=org.id,
        role=UserRole.DEVELOPER,
        role_id=body.role_id,
    )
    db.add(membership)
    await db.flush()
    await db.refresh(created)
    await db.refresh(membership)

    # Set transient org/role attrs for _user_to_member serialization
    created.org_id = org.id  # type: ignore[attr-defined]
    created.role = membership.role  # type: ignore[attr-defined]
    created.role_id = membership.role_id  # type: ignore[attr-defined]
    created.role_ref = membership.role_ref  # type: ignore[attr-defined]

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


@router.patch(
    "/members/{user_id}/role",
    dependencies=[Depends(require_permissions("team:assign_roles"))],
)
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    current_user: User = Depends(get_current_user),
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

    role_repo = RoleRepository(db)
    role = await role_repo.get_by_id(body.role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")

    # Update role on the OrgToUser membership
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(OrgToUser).where(
            OrgToUser.user_id == user_id,
            OrgToUser.org_id == org.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found.")
    membership.role_id = body.role_id
    await db.flush()
    await db.refresh(membership)

    # Re-set transient attrs so _user_to_member sees the updated role
    user.role_id = membership.role_id  # type: ignore[attr-defined]
    user.role_ref = membership.role_ref  # type: ignore[attr-defined]

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

    user.is_active = not user.is_active
    await db.flush()
    await db.refresh(user)

    action = "reactivated" if user.is_active else "deactivated"
    logger.info(
        "member_status_changed", user_id=str(user_id), action=action, by=current_user.email
    )

    return _user_to_member(user)


def _generate_password(length: int = 12) -> str:
    """Generate a secure random password with mixed characters."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one of each category
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%&*" for c in password)
        ):
            return password


@router.post(
    "/members/{user_id}/set-password",
    response_model=SetPasswordResponse,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def set_member_password(
    user_id: uuid.UUID,
    body: SetPasswordRequest | None = None,
    current_user: User = Depends(get_current_user),
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

    # Prevent privilege escalation: non-owners cannot reset an owner's password
    caller_role = getattr(current_user, "role", None)
    target_role = getattr(user, "role", None)
    if target_role == UserRole.ORG_OWNER and caller_role != UserRole.ORG_OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the org owner can reset another org owner's password.",
        )

    password = _generate_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
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
        slack_sent, slack_error = await _send_credentials_slack(
            org, user, password
        )

    from app.config import settings

    login_url = settings.frontend_url.rstrip("/") + "/login"

    return SetPasswordResponse(
        password=password,
        loginUrl=login_url,
        slackSent=slack_sent,
        slackError=slack_error,
    )


async def _send_credentials_slack(
    org: Organization,
    user: User,
    password: str,
) -> tuple[bool, str | None]:
    """Send login credentials to a user via Slack DM.

    Returns:
        Tuple of (sent, error_detail).
    """
    if not user.slack_id:
        return False, "This member has no linked Slack account."

    from app.core.encryption import decrypt_secret
    from app.services.slack_client import chat_post_message, conversations_open

    if not org.slack_bot_token:
        return False, "Slack is not configured for this organization."

    bot_token = decrypt_secret(org.slack_bot_token)
    if not bot_token:
        return False, "Slack token decryption failed. Check your encryption key."

    dm_channel = await conversations_open(bot_token, user.slack_id)
    if not dm_channel:
        return False, "Failed to open DM channel with this member."

    from app.config import settings

    login_url = settings.frontend_url.rstrip("/") + "/login"

    message = (
        f"Hi {user.name}! Your login credentials have been set up.\n\n"
        f"*Email:* `{user.email}`\n"
        f"*Temporary Password:* `{password}`\n\n"
        f"Log in here: {login_url}\n"
        f"You will be asked to change your password on first login."
    )

    result = await chat_post_message(bot_token, dm_channel, message)
    if result is None:
        return False, "Failed to send Slack DM."

    logger.info(
        "credentials_sent_via_slack",
        user_id=str(user.id),
    )
    return True, None


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

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    target = await user_repo.get_by_id_with_membership(target_id, org.id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found.")

    source = await user_repo.get_by_id_with_membership(body.source_id, org.id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source user not found.")

    # 1. Transfer skill profiles: re-point source's profiles to target
    sp_repo = SkillProfileRepository(db, org_id=org.id)
    transferred = await sp_repo.transfer_profiles(source.id, target.id)

    # 2. Add source's primary email as alias on target
    await user_repo.add_email_alias(org.id, target.id, source.email)

    # 3. Transfer source's existing aliases to target
    source_aliases = await user_repo.list_aliases(source.id)
    for alias in source_aliases:
        await user_repo.add_email_alias(org.id, target.id, alias.email)

    # 4. Deactivate source
    source.is_active = False
    await db.flush()

    logger.info(
        "members_merged",
        target_id=str(target_id),
        source_id=str(body.source_id),
        source_email=source.email,
        profiles_transferred=transferred,
        by=current_user.email,
    )

    # Return updated target with aliases
    aliases = await user_repo.list_aliases(target.id)
    return _user_to_member(target, [a.email for a in aliases])
