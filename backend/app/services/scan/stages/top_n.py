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

"""Stage 5 — Keep the top N communities by symbol count.

Final reducer. After hierarchical re-cluster + size-floor, this picks
the N largest meta-communities so the input fits Claude's reasoning
budget. Default N=150; the live synthesis pipeline currently caps at 50,
which is the gap we're closing.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import maybe_skipped_for_ingest
from app.services.scan.synthesis_payload import (
    build_synthesis_payload,
    estimate_payload_tokens,
)

logger = structlog.get_logger(__name__)


DEFAULT_N = 150
DEFAULT_SYNTHESIS_FILES_PER_META = 15


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Keep top N by ``symbol_count``. Stable: ties broken by label asc.

    Also computes the trimmed synthesis payload (15 files per community
    by default) and reports its char/token cost in extras so the operator
    can budget before promoting this config to the live pipeline.
    """
    if (skipped := maybe_skipped_for_ingest(config, io_label="communities → top N")) is not None:
        return skipped
    n = int(config.get("n", DEFAULT_N))
    synthesis_files = int(config.get("synthesis_files_per_meta", DEFAULT_SYNTHESIS_FILES_PER_META))
    sorted_input = sorted(
        communities,
        key=lambda c: (-c.symbol_count, c.label),
    )
    kept = sorted_input[:n]
    cut = sorted_input[n:]
    dropped = [
        c.model_copy(
            update={
                "drop_reason": _append_reason(c.drop_reason, f"top-N (cut at #{n})"),
            }
        )
        for c in cut
    ]

    payload = build_synthesis_payload(kept, files_per_meta=synthesis_files)
    payload_stats = estimate_payload_tokens(payload)

    extras: dict[str, Any] = {
        "n": n,
        "input_count": len(communities),
        "kept_symbol_total": sum(c.symbol_count for c in kept),
        "dropped_symbol_total": sum(c.symbol_count for c in cut),
        "synthesis_files_per_meta": synthesis_files,
        "synthesis_payload": payload_stats,
        "io_label": "communities → top N",
    }
    logger.info(
        "scan_top_n_done",
        repo=ctx.repo_name,
        n=n,
        kept=len(kept),
        dropped=len(dropped),
        synthesis_chars=payload_stats["chars"],
        synthesis_tokens=payload_stats["estimated_tokens"],
    )
    return StageOutput(communities=kept, dropped=dropped, extras=extras)


def _append_reason(existing: str | None, new: str) -> str:
    """Compose drop reasons preserving any earlier-stage annotation."""
    return f"{existing}; {new}" if existing else new
