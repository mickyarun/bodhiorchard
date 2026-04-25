# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Frozen value objects shared by every scan phase.

A phase function takes one immutable ``ScanContext`` and returns a
plain dict (the ``PhaseOutput``). The dict becomes the
``scan_phase_checkpoints.payload`` column. Phases never share mutable
state via closures or passed-in sessions — that's the architectural
invariant the package depends on.

Per-repo phases get a context with ``repo_id`` / ``repo_path`` /
``repo_name`` / ``sha`` populated. Global phases get those four set to
``None`` so the same ``run_checkpointed_phase`` machinery can wrap both.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScanContext:
    """Immutable per-phase invocation context.

    Frozen so a phase body cannot accidentally mutate fields and have
    that mutation leak across the gather boundary into a sibling
    coroutine — the exact bug class that produced the parallel-session
    failure documented in the plan file.
    """

    scan_id: uuid.UUID
    org_id: uuid.UUID
    parent_scan_id: uuid.UUID | None = None
    repo_id: uuid.UUID | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    sha: str | None = None
    full_rescan: bool = False

    @property
    def is_per_repo(self) -> bool:
        """True when this context carries a concrete repo, not the global stripe."""
        return self.repo_id is not None


PhaseOutput = dict[str, Any]
PhaseFn = Callable[[ScanContext], Awaitable[PhaseOutput]]
