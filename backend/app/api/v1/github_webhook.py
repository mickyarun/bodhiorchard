# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""GitHub webhook endpoint for PR event processing.

Receives GitHub webhook events, verifies HMAC-SHA256 signatures,
and dispatches to the event handler for PR tracking and BUD automation.
"""

import hashlib
import hmac
import json

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
from app.services.github_webhook_handler import handle_github_event

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["github-webhooks"])


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
