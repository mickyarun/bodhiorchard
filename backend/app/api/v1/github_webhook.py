"""GitHub webhook endpoint for PR event processing.

Receives GitHub webhook events, verifies HMAC-SHA256 signatures,
and dispatches to the event handler for PR tracking and BUD automation.
"""

import hashlib
import hmac

import structlog
from fastapi import APIRouter, Request, Response

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.models.tracked_repository import TrackedRepository

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

    logger.debug(
        "github_webhook_received",
        github_event=event_type,
        has_signature=bool(signature),
        body_len=len(body),
    )

    if not signature or not event_type:
        return Response(status_code=400, content="Missing signature or event header")

    # Parse payload to resolve org from repository
    import json

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

        # Dispatch to handler
        from app.services.github_webhook_handler import handle_github_event

        await handle_github_event(
            org_id=org.id,
            repo=repo,
            event_type=event_type,
            payload=payload,
            db=db,
        )

    return Response(status_code=200, content="OK")


async def _resolve_org_from_repo(
    db: "AsyncSession",  # noqa: F821
    full_name: str,
) -> tuple[TrackedRepository | None, "Organization | None"]:  # noqa: F821
    """Look up org from a GitHub repo full name (cross-org search)."""
    from sqlalchemy import select

    from app.models.organization import Organization

    stmt = (
        select(TrackedRepository)
        .where(TrackedRepository.github_repo_full_name == full_name)
        .limit(1)
    )
    result = await db.execute(stmt)
    repo = result.scalar_one_or_none()
    if not repo:
        return None, None

    org = await db.get(Organization, repo.org_id)
    return repo, org
