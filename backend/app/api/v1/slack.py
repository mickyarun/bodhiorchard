# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Slack Events API webhook endpoint.

Receives Slack events (reactions, messages), verifies HMAC-SHA256 signatures,
deduplicates, and dispatches to the async job queue for triage processing.
"""

import hashlib
import hmac
import time

import structlog
from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.repositories.organization import OrganizationRepository
from app.schemas.jobs import TriageJobPayload
from app.schemas.slack import SlackEventWrapper, SlackMessageEvent, SlackReactionEvent
from app.services.job_queue import JOB_TRIAGE, create_job

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["slack"])

# ── Event deduplication ─────────────────────────────────────────────
# In-memory dict[event_id → timestamp] with 5-minute TTL.
_seen_events: dict[str, float] = {}
_DEDUP_TTL_SECONDS = 300


def _is_duplicate(event_id: str) -> bool:
    """Check and record an event ID. Returns True if already seen."""
    now = time.time()
    # Prune expired entries (lazy cleanup)
    expired = [eid for eid, ts in _seen_events.items() if now - ts > _DEDUP_TTL_SECONDS]
    for eid in expired:
        _seen_events.pop(eid, None)

    if event_id in _seen_events:
        return True
    _seen_events[event_id] = now
    return False


# ── HMAC-SHA256 verification ────────────────────────────────────────


def _verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> tuple[bool, str]:
    """Verify a Slack request signature.

    Args:
        signing_secret: The org's Slack signing secret (plaintext).
        timestamp: X-Slack-Request-Timestamp header value.
        body: Raw request body bytes.
        signature: X-Slack-Signature header value (v0=hex).

    Returns:
        Tuple of (is_valid, failure_reason). reason is empty on success.
    """
    now = time.time()
    drift = abs(now - int(timestamp))
    if drift > 300:
        return False, f"timestamp_drift={int(drift)}s"

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed = (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )
    if hmac.compare_digest(computed, signature):
        return True, ""
    return (
        False,
        f"hmac_mismatch secret_len={len(signing_secret)} "
        f"secret_prefix={signing_secret[:4]}*** "
        f"body_len={len(body)} "
        f"computed_suffix=...{computed[-8:]} "
        f"received_suffix=...{signature[-8:]}",
    )


# ── Org resolution ──────────────────────────────────────────────────


async def _resolve_org_by_team_id(db: AsyncSession, team_id: str) -> Organization | None:
    """Look up an organization by its Slack team ID.

    Args:
        db: Async database session.
        team_id: Slack workspace team_id.

    Returns:
        The matching Organization, or None.
    """
    return await OrganizationRepository(db).get_by_slack_team_id(team_id)


# ── Main webhook endpoint ──────────────────────────────────────────


@router.post("/events")
async def slack_events(
    request: Request,
) -> Response:
    """Slack Events API webhook.

    Handles:
    - url_verification (challenge handshake)
    - reaction_added (brain emoji → triage, checkmark → approval)
    - message (thread replies → triage continuation)

    Returns 200 immediately for all event callbacks; processing is dispatched
    to the async job queue to stay within Slack's 3-second timeout.
    """
    # Skip Slack retries immediately
    if request.headers.get("X-Slack-Retry-Num"):
        return Response(status_code=200)

    raw_body = await request.body()
    payload = SlackEventWrapper.model_validate_json(raw_body)

    # URL verification challenge (no signature check needed for initial setup)
    if payload.type == "url_verification":
        return Response(
            content=payload.challenge or "",
            media_type="text/plain",
            status_code=200,
        )

    # HMAC signature verification — mandatory for all event callbacks
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        logger.warning("slack_missing_signature_headers", team_id=payload.team_id)
        return Response(status_code=401)

    if not payload.team_id:
        logger.warning("slack_missing_team_id")
        return Response(status_code=400)

    from app.core.encryption import decrypt_secret

    async with AsyncSessionLocal() as db:
        org = await _resolve_org_by_team_id(db, payload.team_id)
        if not org or not org.slack_signing_secret:
            logger.warning("slack_org_not_found_or_no_secret", team_id=payload.team_id)
            return Response(status_code=401)

        signing_secret = decrypt_secret(org.slack_signing_secret)
        if not signing_secret:
            logger.warning(
                "slack_signing_secret_decrypt_failed",
                team_id=payload.team_id,
                encrypted_len=len(org.slack_signing_secret or ""),
            )
            return Response(status_code=401)

        valid, reason = _verify_slack_signature(signing_secret, timestamp, raw_body, signature)
        if not valid:
            logger.warning(
                "slack_signature_invalid",
                team_id=payload.team_id,
                reason=reason,
            )
            return Response(status_code=401)

    # Event deduplication
    if payload.event_id and _is_duplicate(payload.event_id):
        return Response(status_code=200)

    # Dispatch based on event type
    event_data = payload.event
    event_type = event_data.get("type", "")

    if event_type == "reaction_added":
        event = SlackReactionEvent.model_validate(event_data)
        if event.item.type == "message" and event.reaction in (
            "brain",
            "bug",
            "white_check_mark",
            "x",
        ):
            if event.reaction == "brain":
                triage_payload = TriageJobPayload(
                    team_id=payload.team_id or "",
                    action="start_triage",
                    event_type="reaction_added",
                    event_data=event.model_dump(),
                )
            elif event.reaction == "bug":
                triage_payload = TriageJobPayload(
                    team_id=payload.team_id or "",
                    action="start_bug_triage",
                    event_type="reaction_added",
                    event_data=event.model_dump(),
                )
            else:
                triage_payload = TriageJobPayload(
                    team_id=payload.team_id or "",
                    action="pm_approval",
                    event_type="reaction_added",
                    event_data=event.model_dump(),
                    approved=event.reaction == "white_check_mark",
                )
            create_job(JOB_TRIAGE, payload=triage_payload.model_dump())

    elif event_type == "message":
        event = SlackMessageEvent.model_validate(event_data)
        # Only handle thread replies from humans (not bot messages, not top-level)
        if event.thread_ts and not event.bot_id and not event.subtype:
            triage_payload = TriageJobPayload(
                team_id=payload.team_id or "",
                action="continue_triage",
                event_type="message",
                event_data=event.model_dump(),
            )
            create_job(JOB_TRIAGE, payload=triage_payload.model_dump())

    return Response(status_code=200)
