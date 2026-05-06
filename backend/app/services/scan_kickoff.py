# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Single seam for onboard-time scan kickoffs.

Every onboarding flow (GitHub-App bulk import, single PAT clone,
local pre-cloned path) ultimately needs the same "register-then-scan"
shape. The scan runner already handles incremental-vs-full per repo
through its ``head_sha`` mismatch check inside ingest, so callers
hand off ``(org_id, repo_ids)`` and the helper threads the rest:

1. Embedding pre-flight via :func:`embedding_service.check`. A down
   embedding service surfaces as a non-fatal warning string — the
   scan is skipped, the wizard / job tells the user to fix it.
2. :func:`start_scan` with the default ``RunConfig`` (so
   ``full_rescan`` stays ``False``). Forcing the flag here would
   override the runner's already-correct gate.

Not used by event-driven kickoffs (BUD close, PR-merge webhook) or
the admin ``POST /scans`` endpoint — they have their own intent
(incremental on a subset) and config plumbing.
"""

from __future__ import annotations

import uuid

import structlog

from app.schemas.scan import RunConfig
from app.services.embedding_service import embedding_service
from app.services.scan.runner import start_scan

logger = structlog.get_logger(__name__)


async def kick_off_onboard_scan(
    *,
    org_id: uuid.UUID,
    repo_ids: list[uuid.UUID],
) -> tuple[uuid.UUID | None, str | None]:
    """Embedding pre-flight + a single ``start_scan`` for the onboard set.

    Args:
        org_id: Tenant scope for the scan.
        repo_ids: Tracked-repo IDs to include in the scan. Empty list
            is a no-op — returns ``(None, None)``.

    Returns:
        ``(scan_id, embedding_warning)``. Either or both may be ``None``:

        * empty ``repo_ids`` → ``(None, None)``
        * embedding service down → ``(None, warning_text)``
        * happy path → ``(scan_id, None)``

    Raises:
        ScanAlreadyActiveError: propagated unchanged from
            :func:`start_scan` so the caller can map it to its own
            failure surface (HTTP 409, job FAILED, …).
    """
    if not repo_ids:
        return None, None

    embed_ok, embed_err = await embedding_service.check()
    if not embed_ok:
        warning = (
            f"Embedding service unavailable ({embed_err}). "
            "Scan skipped — trigger it manually from Settings after fixing."
        )
        logger.warning("scan_kickoff_embedding_unavailable", error=embed_err)
        return None, warning

    scan_id = await start_scan(
        org_id=org_id,
        repo_ids=repo_ids,
        config=RunConfig(),
    )
    logger.info(
        "scan_kickoff_started",
        org_id=str(org_id),
        scan_id=str(scan_id),
        repo_count=len(repo_ids),
    )
    return scan_id, None
