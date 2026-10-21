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
"""The Slack app's OAuth client, stored under ``org.config["slack_status"]``.

The secret is encrypted at rest and never sent back to the browser.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.repositories.organization import OrganizationRepository
from app.schemas.leave_slack_status import SlackStatusSettings, SlackStatusUpdate

CONFIG_KEY = "slack_status"
CALLBACK_PATH = "/api/v1/slack/status/callback"


@dataclass(frozen=True)
class StatusClient:
    """What the OAuth flow needs; ``ready`` once it's on and complete."""

    enabled: bool
    client_id: str
    client_secret: str

    @property
    def ready(self) -> bool:
        """Switched on, with an id and a secret that decrypts."""
        return self.enabled and bool(self.client_id) and bool(self.client_secret)


def redirect_url() -> str:
    """Slack sends people back here after they approve."""
    return f"{settings.public_url.rstrip('/')}{CALLBACK_PATH}"


def _section(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = (config or {}).get(CONFIG_KEY)
    return raw if isinstance(raw, dict) else {}


async def load_client(db: AsyncSession, org_id: uuid.UUID) -> StatusClient:
    """The org's OAuth client (secret decrypted)."""
    raw = _section(await OrganizationRepository(db).get_config(org_id))
    secret = raw.get("client_secret")
    return StatusClient(
        enabled=bool(raw.get("enabled")),
        client_id=str(raw.get("client_id") or ""),
        client_secret=decrypt_secret(secret) if isinstance(secret, str) else "",
    )


async def load_settings(db: AsyncSession, org_id: uuid.UUID) -> SlackStatusSettings:
    """HR's view of the settings."""
    client = await load_client(db, org_id)
    return SlackStatusSettings(
        enabled=client.enabled,
        client_id=client.client_id,
        has_client_secret=bool(client.client_secret),
        redirect_url=redirect_url(),
    )


async def save_settings(
    db: AsyncSession, org_id: uuid.UUID, update: SlackStatusUpdate
) -> SlackStatusSettings:
    """Save; a blank secret keeps the stored one."""
    repo = OrganizationRepository(db)
    raw = _section(await repo.get_config(org_id))
    secret = (
        encrypt_secret(update.client_secret) if update.client_secret else raw.get("client_secret")
    )
    section = {"enabled": update.enabled, "client_id": update.client_id, "client_secret": secret}
    await repo.set_config_section(org_id, CONFIG_KEY, section)
    return await load_settings(db, org_id)
