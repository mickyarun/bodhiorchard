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

"""Re-encrypting stored org secrets under a new ENCRYPTION_KEY."""

from __future__ import annotations

import pytest

from app.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models.organization import Organization
from app.services.secret_rotation import rotate
from tests.integration.leave_support import Factory, setup_org

pytestmark = pytest.mark.integration


def _keys(monkeypatch: pytest.MonkeyPatch, current: str, previous: str = "") -> None:
    monkeypatch.setattr(settings.auth, "encryption_key", current)
    monkeypatch.setattr(settings.auth, "encryption_key_previous", previous)


async def test_every_org_secret_moves_to_the_new_key(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _, _ = await setup_org(pg_session_factory, "A")
    _keys(monkeypatch, "old-default")
    async with pg_session_factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        org.slack_bot_token = encrypt_secret("xoxb-1")
        org.claude_api_key_encrypted = encrypt_secret("sk-ant-1")
        org.config = {
            **(org.config or {}),
            "jira": {"api_token": encrypt_secret("jira-1"), "email": "a@b.dev"},
            "llm": {"cloud_api_key": encrypt_secret("cloud-1"), "preset": "fast"},
        }
        await db.commit()
    _keys(monkeypatch, "install-key", "old-default")
    async with pg_session_factory() as db:
        report = await rotate(db, dry_run=False)
    # Other tests' orgs may hold tokens under keys this test doesn't set.
    assert report.rotated >= 4 and not [f for f in report.failed if str(org_id) in f]
    # Readable with the new key alone; plain config values untouched.
    _keys(monkeypatch, "install-key")
    async with pg_session_factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        assert decrypt_secret(org.slack_bot_token or "") == "xoxb-1"
        assert decrypt_secret(org.claude_api_key_encrypted or "") == "sk-ant-1"
        assert decrypt_secret(org.config["jira"]["api_token"]) == "jira-1"
        assert decrypt_secret(org.config["llm"]["cloud_api_key"]) == "cloud-1"
        assert org.config["jira"]["email"] == "a@b.dev"
        assert org.config["llm"]["preset"] == "fast"
        # A second run finds nothing left (for this org or any other).
        assert (await rotate(db, dry_run=False)).rotated == 0


async def test_unreadable_secrets_are_reported_and_left_alone(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _, _ = await setup_org(pg_session_factory, "B")
    _keys(monkeypatch, "lost-key")
    stored = encrypt_secret("gh-secret")
    async with pg_session_factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        org.github_webhook_secret = stored
        await db.commit()
    _keys(monkeypatch, "install-key", "old-default")
    async with pg_session_factory() as db:
        report = await rotate(db, dry_run=False)
        org = await db.get(Organization, org_id)
        assert org is not None
        assert org.github_webhook_secret == stored
    assert any(f"org {org_id} github_webhook_secret" in item for item in report.failed)
