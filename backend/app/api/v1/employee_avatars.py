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

"""Profile photos: upload, remove, serve, import from Slack.

**The GET is deliberately unauthenticated.** Two consumers cannot send a
JWT: a browser ``<img src>`` tag, and Slack, which fetches image blocks
from its own servers when rendering a celebration post. The photo is
therefore served to anyone holding its URL. What keeps that acceptable:

* The URL is keyed by a random per-upload ``avatar_key``, not the user id —
  the URL is posted into Slack, where every channel member (guests too)
  can read it, so it must not double as an identifier.
* Every upload is decoded and re-encoded (``normalise_avatar_image``):
  EXIF/GPS is stripped and only genuine image pixels are ever served.
* Responses carry ``nosniff`` and a sandboxing CSP, as bug attachments do.
* An unknown key and a missing file both return the same 404.

Writes stay authenticated: the photo's owner or ``employees:manage``.
"""

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    PermissionSet,
    get_current_user,
    get_db,
    get_permission_set,
    require_permissions,
)
from app.core.encryption import decrypt_secret
from app.core.paths import sanitize_filename
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.schemas.employee import AvatarRead
from app.services.avatars import (
    AVATAR_CONTENT_TYPE,
    AvatarImageError,
    avatar_storage_path,
    new_avatar_key,
    normalise_avatar_image,
    public_avatar_path,
    sync_slack_photos,
)
from app.services.employees.access import access_for
from app.services.file_storage import FileStorageError, get_file_storage
from app.services.upload_policy import AVATAR_POLICY, UploadPolicyError

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["employee-avatars"])

_SERVE_HEADERS = {
    # The key changes on every upload, so a long max-age never serves a
    # stale photo.
    "Cache-Control": "public, max-age=86400",
    # Never let a browser second-guess the declared image type.
    "X-Content-Type-Options": "nosniff",
    # Belt and braces if someone opens the URL directly in a tab.
    "Content-Security-Policy": "default-src 'none'; sandbox",
}


class SlackPhotoSyncRequest(BaseModel):
    """Options for importing photos from Slack."""

    # Also replace photos that previously came from Slack. Uploads made
    # here are never replaced either way.
    overwrite: bool = False


class SlackPhotoSyncRead(BaseModel):
    """Outcome of importing photos from Slack."""

    updated: int
    skipped_no_photo: int
    skipped_has_photo: int


def _may_edit(perms: PermissionSet, actor_id: uuid.UUID, subject_id: uuid.UUID) -> bool:
    """Your own photo is always yours to change; HR can change anyone's.

    Delegates to ``access_for`` so this route and the ``can_edit_avatar``
    flag the profile page reads cannot drift apart.
    """
    return access_for(perms, actor_id, subject_id).edit_avatar


async def _delete_stored(path: str, *, user_id: uuid.UUID) -> None:
    """Best-effort removal of a replaced or removed photo's bytes."""
    try:
        await get_file_storage().delete(path)
    except FileStorageError:
        logger.warning("avatar_storage_delete_failed", user_id=str(user_id), exc_info=True)


@router.post(
    "/{user_id}/avatar",
    response_model=AvatarRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_avatar(
    user_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> AvatarRead:
    """Replace one member's profile photo.

    Validation runs cheapest-first — permission, type from the filename,
    size, then a full decode — so an unsupported file is rejected before
    it is read or processed. The previous photo's bytes are deleted only
    after the new ones are stored.
    """
    if not _may_edit(perms, current_user.id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change your own profile photo.",
        )

    user_repo = UserRepository(db, org_id=current_user.org_id)
    user = await user_repo.get_by_id_with_membership(user_id, current_user.org_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    safe_name = sanitize_filename(file.filename, fallback="avatar.png")
    try:
        AVATAR_POLICY.resolve_mime(safe_name)
    except UploadPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Read one byte past the cap so an oversized file is caught without
    # buffering all of it.
    data = await file.read(AVATAR_POLICY.max_bytes + 1)
    if len(data) > AVATAR_POLICY.max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{AVATAR_POLICY.label} exceeds the {AVATAR_POLICY.max_mb} MB limit.",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That file is empty.")

    try:
        clean = await asyncio.to_thread(normalise_avatar_image, data)
    except AvatarImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    key = new_avatar_key()
    try:
        stored_path = await get_file_storage().upload(
            org_id=str(current_user.org_id),
            relative_path=avatar_storage_path(key),
            data=clean,
            content_type=AVATAR_CONTENT_TYPE,
            policy=AVATAR_POLICY,
        )
    except FileStorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    previous_path = user.avatar_storage_path
    user.avatar_storage_path = stored_path
    user.avatar_key = key
    user.avatar_url = public_avatar_path(key)
    await db.flush()
    # Each upload has a fresh key, so the old object would otherwise be
    # orphaned — an unreachable copy of someone's photo left in storage.
    if previous_path and previous_path != stored_path:
        await _delete_stored(previous_path, user_id=user_id)

    logger.info(
        "avatar_uploaded",
        user_id=str(user_id),
        by=str(current_user.id),
        bytes_in=len(data),
        bytes_stored=len(clean),
    )
    return AvatarRead(avatar_url=user.avatar_url)


@router.delete("/{user_id}/avatar", response_model=AvatarRead)
async def delete_avatar(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> AvatarRead:
    """Remove a member's photo, falling the UI back to their initials."""
    if not _may_edit(perms, current_user.id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change your own profile photo.",
        )

    user_repo = UserRepository(db, org_id=current_user.org_id)
    user = await user_repo.get_by_id_with_membership(user_id, current_user.org_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    previous_path = user.avatar_storage_path
    user.avatar_storage_path = None
    user.avatar_key = None
    user.avatar_url = None
    await db.flush()
    if previous_path:
        await _delete_stored(previous_path, user_id=user_id)
    return AvatarRead(avatar_url=None)


@router.post(
    "/avatars/sync-slack",
    response_model=SlackPhotoSyncRead,
    dependencies=[
        Depends(require_permissions("employees:manage", "org:edit_settings", mode="any"))
    ],
)
async def import_slack_photos(
    body: SlackPhotoSyncRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SlackPhotoSyncRead:
    """Pull profile photos from Slack for every linked member.

    Open to HR (``employees:manage``) and admins / the owner
    (``org:edit_settings``) — the same people who can open the
    Celebrations page this is run from — rather than behind
    ``integrations:configure``, which HR does not hold.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    if not org.slack_bot_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connect Slack in Settings → Connections first.",
        )
    result = await sync_slack_photos(
        db,
        org_id=org.id,
        bot_token=decrypt_secret(org.slack_bot_token),
        overwrite=bool(body and body.overwrite),
    )
    logger.info(
        "slack_photos_imported",
        org_id=str(org.id),
        updated=result.updated,
        by_user_id=str(current_user.id),
    )
    return SlackPhotoSyncRead(
        updated=result.updated,
        skipped_no_photo=result.skipped_no_photo,
        skipped_has_photo=result.skipped_has_photo,
    )


@router.get("/avatars/{key}")
async def serve_avatar(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream a profile photo by its public key. Unauthenticated — see module docstring.

    Returns the same 404 for a malformed key, an unknown key and a file
    that has gone missing, so the response reveals nothing.
    """
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No photo.")
    if len(key) != 32 or not all(c in "0123456789abcdef" for c in key):
        raise not_found
    user = await UserRepository(db).get_by_avatar_key(key)
    if user is None or not user.avatar_storage_path:
        raise not_found

    try:
        data, _stored_type = await get_file_storage().download(user.avatar_storage_path)
    except FileStorageError:
        logger.warning("avatar_download_failed", user_id=str(user.id), exc_info=True)
        raise not_found from None

    # Every stored photo was re-encoded to JPEG; declare that rather than
    # whatever the storage backend guesses.
    return Response(content=data, media_type=AVATAR_CONTENT_TYPE, headers=_SERVE_HEADERS)
