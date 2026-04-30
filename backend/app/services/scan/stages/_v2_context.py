# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Helpers for v2 stages that wrap legacy per-repo / global phase functions.

The reduction stages don't need any external context beyond the worktree
path. The skill / merge / persist / audit wrappers do — they need the
caller's ``org_id`` + ``scan_id`` so they can open a DB session and
call the legacy phase functions.

The v2 :class:`scan_runner` threads those values into the workflow's
per-stage config dict; this module reads them back out and returns
``None`` when the stage is being run in sandbox mode (sandbox runs
don't have an org/scan and should no-op these wrappers).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class V2RuntimeContext:
    """Resolved org + scan context for a wrapper stage."""

    org_id: uuid.UUID
    scan_id: uuid.UUID


def resolve_v2_context(config: dict[str, Any]) -> V2RuntimeContext | None:
    """Pull ``v2_org_id`` + ``v2_scan_id`` out of the config dict.

    Returns ``None`` when either is missing, which is the signal a
    wrapper stage should no-op (e.g. when invoked from a sandbox run
    that doesn't have an org/scan attached).
    """
    org_raw = config.get("v2_org_id")
    scan_raw = config.get("v2_scan_id")
    if org_raw is None or scan_raw is None:
        return None
    return V2RuntimeContext(
        org_id=_coerce_uuid(org_raw),
        scan_id=_coerce_uuid(scan_raw),
    )


def _coerce_uuid(value: Any) -> uuid.UUID:
    """Accept either a UUID instance or its string form."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


_SKIPPED_EXTRAS = {
    "reason": "v2_context_missing",
    "skipped_reason": "Sandbox run — v2 org/scan context not provided",
}


def skipped_v2_output() -> dict[str, Any]:
    """Standard ``extras`` payload for stages that no-op outside a v2 scan."""
    return dict(_SKIPPED_EXTRAS)
