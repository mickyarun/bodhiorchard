"""Slack member sync and linking endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.encryption import decrypt_secret
from app.models.user import OrgToUser, User
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings-slack"])


class SlackMemberPreview(BaseModel):
    """A Slack workspace member with optional auto-matched Bodhigrove user."""

    slack_id: str
    slack_name: str
    slack_avatar: str | None = None
    matched_user_id: uuid.UUID | None = None
    matched_user_name: str | None = None
    already_linked: bool = False


class SlackLinkRequest(BaseModel):
    """Mapping of Slack ID → Bodhigrove user ID for bulk linking."""

    links: list[dict[str, str]]


@router.post("/slack/sync-members", response_model=list[SlackMemberPreview])
async def sync_slack_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SlackMemberPreview]:
    """Fetch all Slack workspace members and match against Bodhigrove users.

    Returns a preview list showing each Slack user with their best-guess
    Bodhigrove match (by email or existing slack_id link). The admin then
    confirms/adjusts the mappings before calling link-members.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of Slack members with suggested Bodhigrove user matches.
    """
    from app.services import slack_client

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    if not org.slack_bot_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack bot token not configured.",
        )

    bot_token = decrypt_secret(org.slack_bot_token)
    slack_members = await slack_client.users_list(bot_token)

    # Load all Bodhigrove users for this org
    user_repo = UserRepository(db, org_id=org.id)
    users = await user_repo.list_by_org(org.id)

    # Build lookup maps
    email_to_user = {u.email.lower(): u for u in users}
    slack_id_to_user = {u.slack_id: u for u in users if u.slack_id}

    results: list[SlackMemberPreview] = []
    for member in slack_members:
        # Skip bots and deactivated users
        if member.get("is_bot") or member.get("deleted") or member.get("id") == "USLACKBOT":
            continue

        sid = member["id"]
        profile = member.get("profile", {})
        display_name = (
            member.get("real_name") or profile.get("display_name") or member.get("name", sid)
        )
        avatar = profile.get("image_48")
        slack_email = (profile.get("email") or "").lower()

        # Check if already linked
        if sid in slack_id_to_user:
            linked_user = slack_id_to_user[sid]
            results.append(
                SlackMemberPreview(
                    slack_id=sid,
                    slack_name=display_name,
                    slack_avatar=avatar,
                    matched_user_id=linked_user.id,
                    matched_user_name=linked_user.name,
                    already_linked=True,
                )
            )
            continue

        # Try email match as a suggestion
        matched_user = email_to_user.get(slack_email) if slack_email else None

        results.append(
            SlackMemberPreview(
                slack_id=sid,
                slack_name=display_name,
                slack_avatar=avatar,
                matched_user_id=matched_user.id if matched_user else None,
                matched_user_name=matched_user.name if matched_user else None,
                already_linked=False,
            )
        )

    # Sort: unlinked first, then linked
    results.sort(key=lambda r: (r.already_linked, r.slack_name.lower()))

    return results


@router.post("/slack/link-members")
async def link_slack_members(
    body: SlackLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Bulk-link Slack IDs to Bodhigrove users.

    Args:
        body: List of {slack_id, user_id} mappings.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Count of linked users.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    linked = 0
    for link in body.links:
        slack_id = link.get("slack_id", "")
        user_id_str = link.get("user_id", "")
        if not slack_id or not user_id_str:
            continue

        try:
            uid = uuid.UUID(user_id_str)
        except ValueError:
            continue

        user = await user_repo.get_by_id(uid)
        if user:
            user.slack_id = slack_id
            linked += 1

    await db.flush()

    logger.info(
        "slack_members_linked",
        linked=linked,
        total=len(body.links),
        by=current_user.email,
    )

    return {"linked": linked}


@router.post("/slack/unlink-member")
async def unlink_slack_member(
    body: dict[str, str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Remove the Slack link from a Bodhigrove user.

    Args:
        body: Dict with ``slack_id`` to unlink.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Success flag.
    """
    slack_id = body.get("slack_id", "")
    if not slack_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="slack_id is required",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    result = await db.execute(
        select(User)
        .join(OrgToUser, OrgToUser.user_id == User.id)
        .where(OrgToUser.org_id == org.id, User.slack_id == slack_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user linked with this Slack ID",
        )

    user.slack_id = None
    await db.flush()

    logger.info(
        "slack_member_unlinked",
        slack_id=slack_id,
        user_id=str(user.id),
        by=current_user.email,
    )

    return {"success": True}
