# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-scan configuration helpers for the v2 orchestrator.

Loads org-level Scan-tuning settings + mints the MCP credentials each
synthesis subprocess needs. Pulled out of ``runner.py`` so the public
orchestrator surface stays focused on lifecycle (start / resume /
cancel) rather than setup plumbing.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.config import settings as app_settings
from app.mcp.auth import create_internal_mcp_token
from app.repositories.organization import OrganizationRepository
from app.scan.session import with_session

logger = structlog.get_logger(__name__)

# Defaults read by the synthesize / merge stages when the org hasn't
# customised its Scan tuning. Kept in sync with the frontend's
# ``V2ConfigResponse`` defaults so a fresh org sees identical numbers
# in the UI vs the backend.
_DEFAULT_TIMEOUT_SECONDS = 300
_DEFAULT_MERGE_TIMEOUT_SECONDS = 300
_DEFAULT_MAX_TURNS = 40


def mint_mcp_credentials(*, org_id: uuid.UUID) -> dict[str, str]:
    """Build the MCP backend URL + scan-scoped MCP token for synthesis.

    Returns an empty dict on failure so the synthesize stage falls back
    to the ``mcp_credentials_missing`` skip path rather than crashing
    the scan.
    """
    try:
        token = create_internal_mcp_token(org_id)
        return {
            "mcp_backend_url": app_settings.mcp_backend_url,
            "mcp_token": token,
        }
    except Exception:
        logger.exception("scan_mcp_credentials_mint_failed", org_id=str(org_id))
        return {}


async def load_scan_cfg(org_id: uuid.UUID) -> dict[str, Any]:
    """Read the Scan-tuning section of the org config.

    Returns the keys the synthesize / merge stages care about with safe
    fallbacks. Pre-loaded once at fanout setup so the per-repo workers
    don't each hit the DB just to learn the same numbers.
    """
    try:
        async with with_session(org_id) as db:
            org = await OrganizationRepository(db).get_by_id(org_id)
            scan_cfg = dict((org.config or {}).get("scan", {})) if org else {}
    except Exception:
        logger.exception("scan_load_scan_cfg_failed", org_id=str(org_id))
        scan_cfg = {}
    return {
        "timeout_seconds": int(scan_cfg.get("timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS),
        "merge_timeout_seconds": int(
            scan_cfg.get("merge_timeout_seconds") or _DEFAULT_MERGE_TIMEOUT_SECONDS
        ),
        "max_turns": int(scan_cfg.get("max_turns") or _DEFAULT_MAX_TURNS),
    }
