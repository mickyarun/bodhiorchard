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
"""Calendar sync settings: options plus the encrypted service account key.

Stored under ``org.config["leave_calendar"]``. The key is encrypted at
rest and never leaves the server; HR only ever sees the account's email.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret, encrypt_secret
from app.repositories.organization import OrganizationRepository
from app.schemas.leave_calendar_sync import (
    CalendarSyncOptions,
    CalendarSyncSettings,
    CalendarSyncUpdate,
)
from app.services.google.service_account import ServiceAccountKey, parse_key

logger = structlog.get_logger(__name__)
CONFIG_KEY = "leave_calendar"
_KEY_FIELD = "service_account_key"


@dataclass(frozen=True)
class CalendarSync:
    """What a sync needs: the options and a usable key (None = can't reach Google)."""

    options: CalendarSyncOptions
    key: ServiceAccountKey | None


def _section(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = (config or {}).get(CONFIG_KEY)
    return raw if isinstance(raw, dict) else {}


def _options(raw: dict[str, Any], org_id: uuid.UUID) -> CalendarSyncOptions:
    try:
        return CalendarSyncOptions.model_validate(raw)
    except ValidationError:
        logger.error("leave_calendar_settings_invalid", org_id=str(org_id))
        return CalendarSyncOptions()


def _key(raw: dict[str, Any], org_id: uuid.UUID) -> ServiceAccountKey | None:
    stored = raw.get(_KEY_FIELD)
    if not isinstance(stored, str) or not stored:
        return None
    plain = decrypt_secret(stored)
    if not plain:
        logger.error("leave_calendar_key_unreadable", org_id=str(org_id))
        return None
    return parse_key(plain)


async def load_options(db: AsyncSession, org_id: uuid.UUID) -> CalendarSyncOptions:
    """Just the options (e.g. where half days split), without touching the key."""
    return _options(_section(await OrganizationRepository(db).get_config(org_id)), org_id)


async def load_sync(db: AsyncSession, org_id: uuid.UUID) -> CalendarSync:
    """The org's options and key. Never raises: a bad key reads as "no key"."""
    raw = _section(await OrganizationRepository(db).get_config(org_id))
    try:
        key = _key(raw, org_id)
    except Exception:
        logger.error("leave_calendar_key_invalid", org_id=str(org_id), exc_info=True)
        key = None
    return CalendarSync(options=_options(raw, org_id), key=key)


async def load_settings(db: AsyncSession, org_id: uuid.UUID) -> CalendarSyncSettings:
    """Settings for HR's screen."""
    sync = await load_sync(db, org_id)
    return CalendarSyncSettings(
        **sync.options.model_dump(),
        service_account_email=sync.key.client_email if sync.key else None,
    )


async def save_settings(
    db: AsyncSession, org_id: uuid.UUID, update: CalendarSyncUpdate
) -> CalendarSyncSettings:
    """Save options and, if given, a new key (checked before it's stored)."""
    repo = OrganizationRepository(db)
    raw = _section(await repo.get_config(org_id))
    section: dict[str, Any] = CalendarSyncOptions.model_validate(
        update.model_dump(exclude={_KEY_FIELD})
    ).model_dump()
    if update.service_account_key:
        parse_key(update.service_account_key)  # GoogleAuthError if it isn't a key
        section[_KEY_FIELD] = encrypt_secret(update.service_account_key)
    elif raw.get(_KEY_FIELD):
        section[_KEY_FIELD] = raw[_KEY_FIELD]
    await repo.set_config_section(org_id, CONFIG_KEY, section)
    return await load_settings(db, org_id)
