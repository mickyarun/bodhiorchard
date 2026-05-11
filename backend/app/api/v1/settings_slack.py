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

"""Slack member sync, linking, and import endpoints."""

import secrets
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.encryption import decrypt_secret
from app.core.security import hash_password
from app.models.user import OrgToUser, User, UserRole
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings-slack"])


class SlackMemberPreview(BaseModel):
    """A Slack workspace member with optional auto-matched Bodhiorchard user."""

    slack_id: str
    slack_name: str
    slack_avatar: str | None = None
    slack_email: str | None = None
    matched_user_id: uuid.UUID | None = None
    matched_user_name: str | None = None
    already_linked: bool = False


class SlackLinkRequest(BaseModel):
    """Mapping of Slack ID → Bodhiorchard user ID for bulk linking."""

    links: list[dict[str, str]]


class SlackImportItem(BaseModel):
    """A Slack member to import as a new Bodhiorchard user."""

    slack_id: str
    slack_name: str
    slack_email: str
    slack_avatar: str | None = None


class SlackImportRequest(BaseModel):
    """Batch import of Slack members as new Bodhiorchard users."""

    imports: list[SlackImportItem]


class SlackImportResponse(BaseModel):
    """Response from batch import of Slack members."""

    imported: int
    skipped: list[str] = []


@router.post("/slack/sync-members", response_model=list[SlackMemberPreview])
async def sync_slack_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SlackMemberPreview]:
    """Fetch all Slack workspace members and match against Bodhiorchard users.

    Returns a preview list showing each Slack user with their best-guess
    Bodhiorchard match (by email or existing slack_id link). The admin then
    confirms/adjusts the mappings before calling link-members.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of Slack members with suggested Bodhiorchard user matches.
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

    # Load all Bodhiorchard users for this org
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
        avatar = profile.get("image_72") or profile.get("image_48")
        slack_email = (profile.get("email") or "").lower()

        # Check if already linked
        if sid in slack_id_to_user:
            linked_user = slack_id_to_user[sid]
            results.append(
                SlackMemberPreview(
                    slack_id=sid,
                    slack_name=display_name,
                    slack_avatar=avatar,
                    slack_email=slack_email or None,
                    matched_user_id=linked_user.id,
                    matched_user_name=linked_user.name,
                    already_linked=True,
                )
            )
            continue

        # Try email match first, then name prefix match
        matched_user = email_to_user.get(slack_email) if slack_email else None

        if not matched_user and display_name:
            # Match by name tokens (case-insensitive):
            # any Slack name token matching any Bodhiorchard user name token
            slack_tokens = {t.lower() for t in display_name.split() if len(t) >= 3}
            for user in users:
                if not user.name:
                    continue
                user_tokens = {t.lower() for t in user.name.split() if len(t) >= 3}
                if slack_tokens & user_tokens:
                    matched_user = user
                    break

        results.append(
            SlackMemberPreview(
                slack_id=sid,
                slack_name=display_name,
                slack_avatar=avatar,
                slack_email=slack_email or None,
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
    """Bulk-link Slack IDs to Bodhiorchard users.

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
    """Remove the Slack link from a Bodhiorchard user.

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

    user_repo = UserRepository(db)
    user = await user_repo.get_by_slack_id_in_org(org.id, slack_id)
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


@router.post("/slack/import-members", response_model=SlackImportResponse)
async def import_slack_members(
    body: SlackImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SlackImportResponse:
    """Import Slack workspace members as new Bodhiorchard users.

    Creates a User + OrgToUser membership for each Slack member that does
    not already exist (by email). Automatically links the Slack ID.

    Args:
        body: List of Slack members to import.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Count of imported users and list of skipped emails (duplicates).
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    imported = 0
    skipped: list[str] = []

    for item in body.imports:
        existing = await user_repo.get_by_email_in_org(org.id, item.slack_email)
        if existing is not None:
            skipped.append(item.slack_email)
            continue

        new_user = User(
            email=item.slack_email,
            name=item.slack_name,
            password_hash=hash_password(secrets.token_urlsafe(12)),
            avatar_url=item.slack_avatar,
            slack_id=item.slack_id,
        )
        created = await user_repo.create(new_user)

        membership = OrgToUser(
            user_id=created.id,
            org_id=org.id,
            role=UserRole.DEVELOPER,
        )
        db.add(membership)
        imported += 1

    await db.flush()

    logger.info(
        "slack_members_imported",
        imported=imported,
        skipped=len(skipped),
        by=current_user.email,
    )

    return SlackImportResponse(imported=imported, skipped=skipped)
