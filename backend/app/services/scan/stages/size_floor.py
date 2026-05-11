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

"""Stage 4 — Drop communities below a symbol-count threshold.

After hierarchical re-cluster, very small meta-communities are usually
glue/utility code that won't synthesise into a useful feature. Dropping
them shrinks the input set without losing real domain coverage.

Default threshold is 1 (effectively a no-op) because aggressive size
filtering hurts small repos disproportionately — a cron-job repo where
every script is its own 4-symbol community would lose half its features
at threshold=5. Operators tuning bigger codebases can raise it.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import maybe_skipped_for_ingest

logger = structlog.get_logger(__name__)


DEFAULT_THRESHOLD = 1


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Drop communities with ``symbol_count < threshold``.

    Threshold is inclusive — a community with exactly ``threshold``
    symbols is kept. Drop reasons are appended to existing ones (so
    Stage 2 reasons survive) and the dropped set carries them through
    for the UI's audit trail.
    """
    skipped = maybe_skipped_for_ingest(config, io_label="communities → above floor")
    if skipped is not None:
        return skipped
    threshold = int(config.get("threshold", DEFAULT_THRESHOLD))
    kept: list[Community] = []
    dropped: list[Community] = []

    for comm in communities:
        if comm.symbol_count < threshold:
            reason = f"size-floor (<{threshold} symbols)"
            existing = comm.drop_reason
            new_reason = f"{existing}; {reason}" if existing else reason
            dropped.append(comm.model_copy(update={"drop_reason": new_reason}))
        else:
            kept.append(comm)

    extras: dict[str, Any] = {
        "threshold": threshold,
        "input_count": len(communities),
        "io_label": "communities → above floor",
    }
    logger.info(
        "scan_size_floor_done",
        repo=ctx.repo_name,
        threshold=threshold,
        kept=len(kept),
        dropped=len(dropped),
    )
    return StageOutput(communities=kept, dropped=dropped, extras=extras)
