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

"""Profile photos: processing, storage layout, URL shapes, Slack import.

``users.avatar_url`` holds one of two things:

* An **absolute** URL — a Slack CDN address pulled in by the Slack photo
  import. Used verbatim everywhere.
* A **root-relative** path into this API (``/api/v1/employees/avatars/{key}``)
  — an upload we serve ourselves. The frontend uses it as-is; Slack cannot,
  because Slack's own servers fetch the image, so
  :func:`absolute_avatar_url` resolves it against ``PUBLIC_URL`` first.

The path is built from ``users.avatar_key`` — a random value minted per
upload — never from the user's id, because the URL ends up in every
celebration post where any channel member (guests included) can read it.

Storing the relative form means a deployment that changes domain does not
have to rewrite every row.
"""

from __future__ import annotations

import io
import secrets
from collections.abc import Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlparse

import structlog
from PIL import Image, ImageOps
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

if TYPE_CHECKING:
    from app.services.employees.access import EmployeeAccess

logger = structlog.get_logger(__name__)

__all__ = [
    "AVATAR_CONTENT_TYPE",
    "AVATAR_PREFIX",
    "AvatarImageError",
    "SlackPhotoSync",
    "absolute_avatar_url",
    "adopt_slack_photo",
    "avatar_storage_path",
    "may_edit_avatar",
    "new_avatar_key",
    "normalise_avatar_image",
    "public_avatar_path",
    "shared_member_ids",
    "slack_photo_url",
    "sync_slack_photos",
]

AVATAR_PREFIX = "avatars"
# Every stored photo is re-encoded to this, whatever was uploaded. JPEG is
# the format Slack's image accessory renders most reliably.
AVATAR_CONTENT_TYPE = "image/jpeg"
_AVATAR_EXTENSION = ".jpg"
# Rendered at 64px in the app and 72px in Slack; 512 leaves headroom for
# high-density screens without serving a 12-megapixel phone original.
_AVATAR_MAX_EDGE = 512
# Accept today's phone cameras (48-50 MP sensors) while refusing anything
# larger: Pillow only *errors* at ~179 MP, and a decoded RGB image costs
# ~3 bytes a pixel. JPEGs — nearly every phone photo — are decoded through
# ``draft()`` at a fraction of full size, so the cap mostly bounds PNG/WebP.
_MAX_SOURCE_PIXELS = 64_000_000
# Decode only these. Pillow otherwise sniffs any of ~40 formats from the
# bytes, whatever the filename says — including EPS, which shells out to
# Ghostscript. The extension check alone cannot stop a renamed file.
_ALLOWED_FORMATS = ("PNG", "JPEG", "GIF", "WEBP")


class AvatarImageError(ValueError):
    """The upload is not an image we can safely decode."""


def new_avatar_key() -> str:
    """A fresh 32-hex-char key for one uploaded photo."""
    return secrets.token_hex(16)


def avatar_storage_path(key: str) -> str:
    """Where one photo's bytes live inside the org's storage namespace."""
    return f"{AVATAR_PREFIX}/{key}{_AVATAR_EXTENSION}"


def public_avatar_path(key: str) -> str:
    """The root-relative URL stored in ``users.avatar_url`` after an upload.

    The key changes on every upload, so the URL itself busts browser and
    Slack caches when someone replaces their photo.
    """
    return f"/api/v1/employees/{AVATAR_PREFIX}/{key}"


def normalise_avatar_image(data: bytes) -> bytes:
    """Decode, sanitise and re-encode an uploaded photo.

    The served photo is public, so it must carry nothing but pixels:

    * **Metadata is dropped.** Phone photos routinely embed EXIF GPS —
      often a home address. Re-encoding writes no EXIF/XMP/ICC at all.
    * **Orientation is applied first**, so stripping the EXIF orientation
      tag does not leave the photo sideways.
    * **Only real images survive.** Anything Pillow cannot decode is
      rejected, so a renamed HTML or script file can never be served back.
    * **Size is bounded** to ``_AVATAR_MAX_EDGE`` on the long edge; an
      animated GIF keeps its first frame.

    CPU-bound — call it via ``asyncio.to_thread``.

    Raises:
        AvatarImageError: The bytes are not a decodable image, or are
            implausibly large once decoded.
    """
    try:
        with Image.open(io.BytesIO(data), formats=_ALLOWED_FORMATS) as source:
            width, height = source.size
            if width * height > _MAX_SOURCE_PIXELS:
                raise AvatarImageError("That image is too large to process.")
            if source.format == "JPEG":
                # Let libjpeg decode at 1/2, 1/4 or 1/8 scale: a 48 MP phone
                # photo then needs a few MB of memory instead of ~150 MB.
                source.draft("RGB", (_AVATAR_MAX_EDGE * 2, _AVATAR_MAX_EDGE * 2))
            # Typed ``Image | None`` (``None`` only for ``in_place=True``).
            image = ImageOps.exif_transpose(source) or source
            if image.mode not in ("RGB", "L"):
                # Flatten transparency onto white rather than black.
                rgba = image.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, (255, 255, 255))
                flattened.paste(rgba, mask=rgba.split()[3])
                image = flattened
            image = image.convert("RGB")
            image.thumbnail((_AVATAR_MAX_EDGE, _AVATAR_MAX_EDGE))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue()
    except AvatarImageError:
        raise
    except Exception as exc:
        # Deliberately broad: decoders raise more than OSError/ValueError
        # (Pillow's PNG plugin raises SyntaxError on a corrupt chunk), and
        # every one of them means "not an image we will serve" — a 400 for
        # the uploader, never a 500.
        raise AvatarImageError("That file isn't an image we can read.") from exc


def absolute_avatar_url(avatar_url: str | None) -> str | None:
    """Resolve a stored avatar value to something a third party can fetch.

    Absolute URLs pass through. Relative paths are joined onto
    ``PUBLIC_URL``; if that is still the localhost default the result is
    unreachable from outside, so ``None`` is returned rather than handing
    Slack a URL it will fail to load and render as a broken image.
    """
    if not avatar_url:
        return None
    if avatar_url.startswith(("http://", "https://")):
        return avatar_url
    base = settings.public_url.rstrip("/")
    if "localhost" in base or "127.0.0.1" in base:
        return None
    return f"{base}{avatar_url}"


def slack_photo_url(profile: dict[str, Any]) -> str | None:
    """The best photo URL in a Slack ``profile`` object, or ``None``.

    Returns ``None`` for members who never set a picture: Slack then serves
    a generated letter tile, and importing that would replace our own
    initials avatar with a worse-looking copy of it. ``is_custom_image`` is
    Slack's flag for this; the gravatar check catches older payloads that
    omit the flag.
    """
    if profile.get("is_custom_image") is False:
        return None
    url = profile.get("image_512") or profile.get("image_192") or profile.get("image_72")
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    # Compare the host itself — a substring test would also reject (or, in a
    # sanitiser, accept) hosts like ``gravatar.com.example``.
    if host == "gravatar.com" or host.endswith(".gravatar.com"):
        return None
    return url


class _HasPhoto(Protocol):
    """The two photo columns ``adopt_slack_photo`` reads and writes."""

    avatar_url: str | None
    avatar_storage_path: str | None


def adopt_slack_photo(user: _HasPhoto, url: str, *, overwrite: bool = False) -> bool:
    """Give ``user`` their Slack photo ``url``; True if it changed.

    An upload made here always wins — someone who chose a photo meant it —
    so a stored file is never replaced. ``overwrite`` only lets a newer
    Slack photo replace an older one. Every path that copies a Slack photo
    onto a member goes through this rule.
    """
    if user.avatar_storage_path or user.avatar_url == url:
        return False
    if user.avatar_url and not overwrite:
        return False
    user.avatar_url = url
    return True


@dataclass(frozen=True)
class SlackPhotoSync:
    """Outcome of importing photos from Slack."""

    updated: int
    skipped_no_photo: int
    skipped_has_photo: int
    # Members who also belong to another org: their photo is shared, so one
    # org's Slack must not overwrite what the other org shows.
    skipped_shared: int = 0


async def sync_slack_photos(
    db: AsyncSession,
    *,
    org_id: Any,
    bot_token: str,
    overwrite: bool = False,
    only_user_ids: Collection[Any] | None = None,
) -> SlackPhotoSync:
    """Copy Slack profile photos onto linked members.

    The single implementation behind both the "Import photos from Slack"
    action and the photo adoption that follows linking members to Slack.
    URLs come from Slack's own API, never from the client.

    A self-hosted upload always wins, ``overwrite`` or not — someone who
    uploaded a photo here meant it. ``overwrite`` only replaces photos that
    themselves came from Slack.

    Args:
        db: Session to write through; the caller commits.
        org_id: Tenant whose members are updated.
        bot_token: Decrypted Slack bot token.
        overwrite: Replace existing Slack-sourced photos too.
        only_user_ids: Restrict to these members (e.g. just-linked ones).
    """
    from app.repositories.user import UserRepository
    from app.services import slack_client

    photos: dict[str, str] = {}
    for member in await slack_client.users_list(bot_token):
        if member.get("is_bot") or member.get("deleted"):
            continue
        url = slack_photo_url(member.get("profile") or {})
        if url:
            photos[member["id"]] = url

    wanted = set(only_user_ids) if only_user_ids is not None else None
    members = [
        u
        for u in await UserRepository(db, org_id=org_id).list_by_org(org_id)
        if u.slack_id and (wanted is None or u.id in wanted)
    ]
    shared = await shared_member_ids(db, [u.id for u in members])
    updated = skipped_no_photo = skipped_has_photo = skipped_shared = 0
    for user in members:
        if user.id in shared:
            skipped_shared += 1
            continue
        assert user.slack_id is not None  # filtered above; narrows for mypy
        url = photos.get(user.slack_id)
        if not url:
            skipped_no_photo += 1
            continue
        if not adopt_slack_photo(user, url, overwrite=overwrite):
            skipped_has_photo += 1
            continue
        updated += 1
    await db.flush()
    return SlackPhotoSync(
        updated=updated,
        skipped_no_photo=skipped_no_photo,
        skipped_has_photo=skipped_has_photo,
        skipped_shared=skipped_shared,
    )


async def shared_member_ids(db: AsyncSession, user_ids: Collection[Any]) -> set[Any]:
    """Which of ``user_ids`` belong to more than one org.

    ``users`` rows — and so the photo on them — are shared across every org
    a person belongs to. For those people only they may change their own
    photo; same rule as Slack links in ``slack_identity``.
    """
    if not user_ids:
        return set()
    from app.models.user import OrgToUser

    rows = await db.execute(
        select(OrgToUser.user_id)
        .where(OrgToUser.user_id.in_(list(user_ids)))
        .group_by(OrgToUser.user_id)
        .having(func.count() > 1)
    )
    return {row[0] for row in rows.all()}


async def may_edit_avatar(db: AsyncSession, access: EmployeeAccess, subject_id: Any) -> bool:
    """Whether the caller described by ``access`` may change ``subject_id``'s photo.

    Your own photo is always yours. HR (``access.edit_avatar``) may change
    someone else's only if that person belongs to this org alone — their
    ``users`` row, and so the photo, is otherwise shown in another org too.
    The profile page's ``can_edit_avatar`` flag and the upload/delete routes
    both call this, so the button and the API cannot disagree.
    """
    if not access.edit_avatar:
        return False
    if access.is_self:
        return True
    return subject_id not in await shared_member_ids(db, [subject_id])
