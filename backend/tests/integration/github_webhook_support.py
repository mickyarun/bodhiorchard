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

"""Signed GitHub deliveries and recorders for the webhook integration tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest

from app.core.encryption import encrypt_secret
from tests.integration.scan_features_bugs_support import Factory, new_org, new_repo

SECRET = "webhook-secret-for-tests"


def merged_pr_payload(
    full_name: str,
    *,
    number: int = 1,
    base: str = "main",
    merged: bool = True,
    bud_ref: str = "feature/login",
) -> bytes:
    """A ``pull_request.closed`` body for ``full_name`` as GitHub serialises it."""
    payload = {
        "action": "closed",
        "repository": {"full_name": full_name},
        "pull_request": {
            "id": 900_000 + number,
            "number": number,
            "title": "Ship login",
            "html_url": f"https://github.com/{full_name}/pull/{number}",
            "head": {"ref": bud_ref, "sha": "h" * 40},
            "base": {"ref": base, "sha": "b" * 40},
            "state": "closed",
            "user": {"login": "octo", "id": 1},
            "merged": merged,
            "merged_at": "2026-10-01T10:00:00Z",
            "merge_commit_sha": "m" * 40,
        },
    }
    return json.dumps(payload).encode()


def signed_headers(body: bytes, delivery: str, *, secret: str = SECRET) -> dict[str, str]:
    """Headers GitHub sends with ``body`` signed under ``secret``."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": f"sha256={digest}",
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }


async def tracked_repo(
    factory: Factory,
    *,
    secret: str | None = SECRET,
    main_branch: str | None = "main",
    **cols: Any,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    """A new org whose webhook secret is ``secret``, tracking one GitHub repo."""
    stored = encrypt_secret(secret) if secret else None
    org = await new_org(factory, github_webhook_secret=stored)
    full_name = f"acme/{uuid.uuid4().hex[:12]}"
    repo = await new_repo(
        factory, org, github_repo_full_name=full_name, main_branch=main_branch, **cols
    )
    return org, repo, full_name


@dataclass
class WebhookCalls:
    """What the endpoint handed to the event handler and the stream publisher."""

    handled: int = 0
    published: list[tuple[uuid.UUID, uuid.UUID, str]] = field(default_factory=list)
    publish_error: Exception | None = None

    @classmethod
    def install(
        cls, monkeypatch: pytest.MonkeyPatch, module: ModuleType, factory: Factory
    ) -> WebhookCalls:
        """Point ``module`` at ``factory`` and wrap its handler and publisher."""
        calls = cls()
        real_handler = module.handle_github_event

        async def _handle(**kwargs: Any) -> None:
            calls.handled += 1
            await real_handler(**kwargs)

        async def _publish(*, org_id: uuid.UUID, repo_id: uuid.UUID, delivery_id: str) -> bool:
            if calls.publish_error is not None:
                raise calls.publish_error
            calls.published.append((org_id, repo_id, delivery_id))
            return True

        monkeypatch.setattr(module, "AsyncSessionLocal", factory)
        monkeypatch.setattr(module, "handle_github_event", _handle)
        monkeypatch.setattr(module, "publish_pr_merge_delivery", _publish)
        return calls
