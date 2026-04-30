# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-phase running totals across sub-stages.

A scan phase (e.g. ``CODE_INDEX``) may roll up multiple sub-stages.
Rather than emit a RUNNING/DONE pair per sub-stage (which would thrash
the timeline chip's status N times), the workflow opens an accumulator
when the phase starts, folds every sub-stage's outcome in, and emits a
single terminal observer call when the phase boundary is crossed.
"""

from __future__ import annotations

from typing import Any


class PhaseAccumulator:
    """Folds N sub-stage results into one phase-level summary."""

    __slots__ = (
        "all_skipped",
        "dropped_count",
        "extras",
        "input_count",
        "kept_count",
        "started_at",
        "sub_stages",
    )

    def __init__(self, *, started_at: float, input_count: int) -> None:
        self.started_at = started_at
        self.input_count = input_count
        self.kept_count = 0
        self.dropped_count = 0
        self.all_skipped = True
        self.sub_stages: list[dict[str, Any]] = []
        self.extras: dict[str, Any] = {}

    def record(
        self,
        *,
        stage_name: str,
        is_skipped: bool,
        kept: int,
        dropped: int,
        duration_ms: int,
        stage_extras: dict[str, Any],
    ) -> None:
        """Fold one sub-stage's result into the accumulator."""
        self.kept_count = kept
        self.dropped_count += dropped
        if not is_skipped:
            self.all_skipped = False
        self.sub_stages.append(
            {
                "name": stage_name,
                "status": "skipped_cache" if is_skipped else "done",
                "input_count": stage_extras.get("input_count"),
                "kept_count": kept,
                "dropped_count": dropped,
                "io_label": stage_extras.get("io_label"),
                "skipped_reason": stage_extras.get("skipped_reason"),
                "duration_ms": duration_ms,
            }
        )
        # Last sub-stage's extras win for top-level chip rendering, but
        # the sub_stages array preserves the full reduction story.
        self.extras = dict(stage_extras)

    def terminal_extras(self) -> dict[str, Any]:
        """Build the extras payload for the terminal observer call."""
        out = dict(self.extras)
        out["sub_stages"] = list(self.sub_stages)
        return out
