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

"""Helpers for stages that wrap legacy per-repo / global phase functions.

The reduction stages don't need any external context beyond the worktree
path. The skill / merge / persist / audit wrappers do — they need the
caller's ``org_id`` + ``scan_id`` so they can open a DB session and
call the legacy phase functions.

The :class:`scan_runner` threads those values into the workflow's
per-stage config dict; this module reads them back out and returns
``None`` when the stage is being run in sandbox mode (sandbox runs
don't have an org/scan and should no-op these wrappers).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class RuntimeContext:
    """Resolved org + scan context for a wrapper stage."""

    org_id: uuid.UUID
    scan_id: uuid.UUID


def resolve_runtime_context(config: dict[str, Any]) -> RuntimeContext | None:
    """Pull ``org_id`` + ``scan_id`` out of the config dict.

    Returns ``None`` when either is missing, which is the signal a
    wrapper stage should no-op (e.g. when invoked from a sandbox run
    that doesn't have an org/scan attached).
    """
    org_raw = config.get("org_id")
    scan_raw = config.get("scan_id")
    if org_raw is None or scan_raw is None:
        return None
    return RuntimeContext(
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
    "skipped_reason": "Sandbox run — org/scan context not provided",
}


def skipped_runtime_output() -> dict[str, Any]:
    """Standard ``extras`` payload for stages that no-op outside a scan."""
    return dict(_SKIPPED_EXTRAS)
