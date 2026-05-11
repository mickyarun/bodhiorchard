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

"""GitHub webhook endpoint for PR event processing.

Receives GitHub webhook events, verifies HMAC-SHA256 signatures,
and dispatches to the event handler for PR tracking and BUD automation.
"""

import hashlib
import hmac
import json
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.webhook_log import WebhookLogRepository
from app.schemas.settings import GitHubAppStatus
from app.services.event_bus import publish as event_publish
from app.services.github_webhook_handler import handle_github_event

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["github-webhooks"])

# GitHub event types that target the App installation itself rather than a
# specific repository — these payloads carry no top-level ``repository``,
# only ``installation.app_id`` / ``installation.id``.
EVENT_INSTALLATION = "installation"
EVENT_INSTALLATION_REPOSITORIES = "installation_repositories"
_INSTALL_EVENTS = frozenset({EVENT_INSTALLATION, EVENT_INSTALLATION_REPOSITORIES})

# ``installation`` action values we care about. Anything else is logged
# and acked with 200 OK so GitHub stops retrying.
ACTION_CREATED = "created"
ACTION_UNSUSPEND = "unsuspend"
ACTION_NEW_PERMISSIONS_ACCEPTED = "new_permissions_accepted"
ACTION_DELETED = "deleted"
ACTION_SUSPEND = "suspend"
_ACTIONS_SET_INSTALL_ID = frozenset(
    {ACTION_CREATED, ACTION_UNSUSPEND, ACTION_NEW_PERMISSIONS_ACCEPTED}
)
_ACTIONS_CLEAR_INSTALL_ID = frozenset({ACTION_DELETED, ACTION_SUSPEND})


def _verify_github_signature(secret: str, body: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    expected = (
        "sha256="
        + hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(request: Request) -> Response:
    """Receive and process GitHub webhook events.

    No auth dependency — verified via HMAC-SHA256 signature.
    Processes inline (no LLM calls, just DB writes).
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = (request.headers.get("X-GitHub-Delivery") or "").strip()

    logger.debug(
        "github_webhook_received",
        github_event=event_type,
        delivery_id=delivery_id,
        has_signature=bool(signature),
        body_len=len(body),
    )

    if not signature or not event_type:
        return Response(status_code=400, content="Missing signature or event header")

    if not delivery_id:
        # Loud failure: never silently skip a webhook. Without a
        # delivery ID we cannot dedupe, so refusing the request is
        # safer than dispatching potentially-replayed work.
        logger.warning(
            "webhook_missing_delivery_id",
            github_event=event_type,
            body_len=len(body),
        )
        return JSONResponse(
            status_code=400,
            content={"detail": "missing X-GitHub-Delivery header"},
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Response(status_code=400, content="Invalid JSON")

    # Installation-scoped events (App install / uninstall / repo-list
    # changes) carry no top-level ``repository`` — resolve the org by
    # ``installation.app_id`` instead and persist the install_id.
    if event_type in _INSTALL_EVENTS:
        return await _handle_install_event(
            body=body,
            signature=signature,
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
        )

    repo_full_name = payload.get("repository", {}).get("full_name", "")
    if not repo_full_name:
        return Response(status_code=200, content="No repository in payload")

    # Resolve org from tracked repo's github_repo_full_name
    async with AsyncSessionLocal() as db:
        repo, org = await _resolve_org_from_repo(db, repo_full_name)
        if not repo or not org:
            logger.debug("github_webhook_unknown_repo", repo=repo_full_name)
            return Response(status_code=200, content="Repository not tracked")

        # Verify signature with org's webhook secret
        if not org.github_webhook_secret:
            logger.warning("github_webhook_no_secret", org_id=str(org.id))
            return Response(status_code=200, content="No webhook secret configured")

        secret = decrypt_secret(org.github_webhook_secret)
        if not secret:
            logger.warning(
                "github_webhook_decrypt_failed",
                org_id=str(org.id),
                secret_len=len(org.github_webhook_secret or ""),
            )
            return Response(status_code=401, content="Invalid signature")
        if not _verify_github_signature(secret, body, signature):
            logger.warning(
                "github_webhook_bad_signature",
                org_id=str(org.id),
                sig_header=signature[:20] + "..." if signature else "MISSING",
                body_len=len(body),
            )
            return Response(status_code=401, content="Invalid signature")

        # Auto-detect installation_id from webhook payload
        install_id = payload.get("installation", {}).get("id")
        if install_id and not org.github_app_installation_id:
            org.github_app_installation_id = install_id
            await db.flush()
            logger.info("github_installation_id_auto_detected", install_id=install_id)

        # Idempotency check: GitHub retries on any non-2xx, so a
        # successfully-dispatched delivery may arrive again. Recording
        # the delivery before dispatch (and rolling back with the
        # dispatch on error) gives "at-least-once with skip-on-success"
        # semantics: retries after success short-circuit; retries after
        # failure re-attempt.
        log_repo = WebhookLogRepository(db, org_id=org.id)
        fresh = await log_repo.record_delivery(
            delivery_id=delivery_id,
            event_type=event_type,
            org_id=org.id,
            payload_summary={
                "repo": repo_full_name,
                "action": payload.get("action"),
            },
        )
        if not fresh:
            logger.info(
                "webhook_duplicate_delivery",
                delivery_id=delivery_id,
                event_type=event_type,
                org_id=str(org.id),
            )
            return JSONResponse(
                status_code=200,
                content={"status": "duplicate"},
            )

        # Dispatch to handler
        await handle_github_event(
            org_id=org.id,
            repo=repo,
            event_type=event_type,
            payload=payload,
            db=db,
        )

    return Response(status_code=200, content="OK")


async def _handle_install_event(
    *,
    body: bytes,
    signature: str,
    event_type: str,
    delivery_id: str,
    payload: dict[str, Any],
) -> Response:
    """Process ``installation`` / ``installation_repositories`` deliveries.

    These events have no ``repository`` field — the only org-routing
    handle is ``installation.app_id``. We resolve the org via that, then
    follow the same verify-record-persist pattern as the repo-scoped
    path so the two share idempotency semantics.
    """
    installation = payload.get("installation") or {}
    app_id = installation.get("app_id")
    install_id = installation.get("id")
    action = payload.get("action")

    if not isinstance(app_id, int):
        logger.debug(
            "github_install_webhook_missing_app_id",
            github_event=event_type,
            delivery_id=delivery_id,
        )
        return Response(status_code=200, content="No app_id in payload")

    async with AsyncSessionLocal() as db:
        org = await OrganizationRepository(db).get_by_github_app_id(app_id)
        if org is None:
            logger.info(
                "github_install_webhook_no_matching_org",
                github_event=event_type,
                app_id=app_id,
                delivery_id=delivery_id,
                action=repr(action),
            )
            return Response(status_code=200, content="No matching org")

        if not org.github_webhook_secret:
            logger.warning("github_webhook_no_secret", org_id=str(org.id))
            return Response(status_code=200, content="No webhook secret configured")

        secret = decrypt_secret(org.github_webhook_secret)
        if not secret or not _verify_github_signature(secret, body, signature):
            logger.warning(
                "github_install_webhook_bad_signature",
                org_id=str(org.id),
                github_event=event_type,
                action=repr(action),
            )
            return Response(status_code=401, content="Invalid signature")

        log_repo = WebhookLogRepository(db, org_id=org.id)
        fresh = await log_repo.record_delivery(
            delivery_id=delivery_id,
            event_type=event_type,
            org_id=org.id,
            payload_summary={
                "app_id": app_id,
                "installation_id": install_id,
                "action": action,
            },
        )
        if not fresh:
            logger.info(
                "webhook_duplicate_delivery",
                delivery_id=delivery_id,
                event_type=event_type,
                org_id=str(org.id),
            )
            return JSONResponse(status_code=200, content={"status": "duplicate"})

        await _apply_install_state(
            db=db,
            org=org,
            event_type=event_type,
            action=action,
            install_id=install_id,
        )
        await db.commit()

    return Response(status_code=200, content="OK")


async def _apply_install_state(
    *,
    db: AsyncSession,
    org: Organization,
    event_type: str,
    action: str | None,
    install_id: int | None,
) -> None:
    """Mutate ``org.github_app_installation_id`` per event/action.

    Splits the persistence rules out of the HTTP handler so the side
    effects can be unit-tested without spinning up the request layer.
    """
    previous = org.github_app_installation_id

    if event_type == EVENT_INSTALLATION and action in _ACTIONS_CLEAR_INSTALL_ID:
        if previous is not None:
            org.github_app_installation_id = None
            await db.flush()
            logger.info(
                "github_installation_removed",
                org_id=str(org.id),
                action=repr(action),
                previous_install_id=previous,
            )
        return

    # Both ``installation.<set-actions>`` and any
    # ``installation_repositories`` action: refresh install_id so a
    # stale-None state heals itself, and a re-install with a new
    # installation_id overwrites the old one.
    is_set_action = (
        event_type == EVENT_INSTALLATION and action in _ACTIONS_SET_INSTALL_ID
    ) or event_type == EVENT_INSTALLATION_REPOSITORIES

    if not is_set_action:
        logger.debug(
            "github_install_webhook_action_ignored",
            org_id=str(org.id),
            github_event=event_type,
            action=repr(action),
        )
        return

    if not isinstance(install_id, int):
        logger.debug(
            "github_install_webhook_missing_install_id",
            org_id=str(org.id),
            github_event=event_type,
            action=repr(action),
        )
        return

    if previous == install_id:
        return

    org.github_app_installation_id = install_id
    await db.flush()
    logger.info(
        "github_installation_id_set",
        org_id=str(org.id),
        github_event=event_type,
        action=repr(action),
        previous_install_id=previous,
        install_id=install_id,
    )
    # Push to ``org:{org.id}:install`` so the frontend's ``useInstallSocket``
    # flips AWAITING_INSTALL → READY without waiting for its 30 s poll
    # fallback. snake_case payload matches the WS event convention used
    # by xp/scan/notifications publishers; ``InstallEvent`` on the
    # frontend mirrors these field names.
    install_topic = f"org:{org.id}:install"
    event_publish(
        install_topic,
        {
            "event_type": "install_set",
            "status": GitHubAppStatus.READY.value,
            "installation_id": install_id,
        },
    )
    logger.info("github_install_event_published", topic=install_topic)


async def _resolve_org_from_repo(
    db: AsyncSession,
    full_name: str,
) -> tuple[TrackedRepository | None, Organization | None]:
    """Look up org from a GitHub repo full name (cross-org search)."""
    repo = await TrackedRepoRepository(db).get_by_github_full_name(full_name)
    if not repo:
        return None, None
    org = await OrganizationRepository(db).get_by_id(repo.org_id)
    return repo, org
