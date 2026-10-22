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
from typing import Any

import structlog
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = structlog.get_logger(__name__)

__all__ = [
    "AVATAR_CONTENT_TYPE",
    "AVATAR_PREFIX",
    "AvatarImageError",
    "SlackPhotoSync",
    "absolute_avatar_url",
    "avatar_storage_path",
    "new_avatar_key",
    "normalise_avatar_image",
    "public_avatar_path",
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
# Refuse decompression bombs well before Pillow's own (warning-only) limit.
_MAX_SOURCE_PIXELS = 40_000_000


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
        with Image.open(io.BytesIO(data)) as source:
            width, height = source.size
            if width * height > _MAX_SOURCE_PIXELS:
                raise AvatarImageError("That image is too large to process.")
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
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
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
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    if "gravatar.com" in url:
        return None
    return url


@dataclass(frozen=True)
class SlackPhotoSync:
    """Outcome of importing photos from Slack."""

    updated: int
    skipped_no_photo: int
    skipped_has_photo: int


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
    updated = skipped_no_photo = skipped_has_photo = 0
    for user in await UserRepository(db, org_id=org_id).list_by_org(org_id):
        if not user.slack_id or (wanted is not None and user.id not in wanted):
            continue
        url = photos.get(user.slack_id)
        if not url:
            skipped_no_photo += 1
            continue
        if user.avatar_storage_path or user.avatar_url == url:
            skipped_has_photo += 1
            continue
        if user.avatar_url and not overwrite:
            skipped_has_photo += 1
            continue
        user.avatar_url = url
        updated += 1
    await db.flush()
    return SlackPhotoSync(
        updated=updated,
        skipped_no_photo=skipped_no_photo,
        skipped_has_photo=skipped_has_photo,
    )
