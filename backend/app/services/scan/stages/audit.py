# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage AUDIT — End-of-scan diagnostics (global, runs once per scan).

Wraps ``app.scan.audit.audit_scan``. Reads from committed checkpoints
+ DB to detect any anomalies (repos that ended up with clusters but no
synthesized features, orphan features without repo links). Warn-only:
audit failures never abort the scan.

Called last from :mod:`scan_runner._run_global_phases`.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._v2_context import resolve_v2_context, skipped_v2_output

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Run end-of-scan audit; record findings in extras."""
    v2 = resolve_v2_context(config)
    if v2 is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_v2_output())

    from app.scan.audit import audit_scan
    from app.scan.context import ScanContext

    # ScanContext is the legacy global-stripe shape: ``scan_id`` and
    # ``org_id`` are required, ``repo_id`` is left None for the
    # global-audit invocation (the audit walks every repo's checkpoints).
    audit_ctx = ScanContext(scan_id=v2.scan_id, org_id=v2.org_id)
    try:
        report = await audit_scan(audit_ctx)
    except Exception as exc:
        logger.warning(
            "scan_audit_failed",
            scan_id=str(v2.scan_id),
            error=str(exc)[:300],
        )
        return StageOutput(
            communities=communities,
            dropped=[],
            extras={"audit_run": False, "error": str(exc)[:300]},
        )

    extras = {
        "audit_run": True,
        "is_clean": report.is_clean,
        "missing_repo_synth": len(report.missing_repo_synth),
        "orphan_features": len(report.orphan_features),
    }
    logger.info(
        "scan_audit_done",
        scan_id=str(v2.scan_id),
        is_clean=report.is_clean,
        anomalies=len(report.missing_repo_synth) + len(report.orphan_features),
    )
    return StageOutput(communities=communities, dropped=[], extras=extras)
