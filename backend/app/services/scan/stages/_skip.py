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

"""Helpers that turn skip-predicate decisions into uniform ``StageOutput`` payloads.

Stages call their per-stage predicate from ``_skip_predicates`` first. When
a predicate says skip, the stage hands the ``SkipDecision`` here to build
the standard ``StageOutput`` so every chip popover renders the same shape.

Reduction sub-stages (``extract`` → ``top_n``) don't run their own
predicate — they piggyback on ``ingest``'s decision via the
``ingest_skipped`` cumulative-config flag the workflow propagates after
``ingest`` returns.
"""

from __future__ import annotations

from typing import Any

from app.services.scan.stages import StageOutput
from app.services.scan.stages._skip_predicates import SkipDecision


def stage_output_for_skip(decision: SkipDecision, *, io_label: str) -> StageOutput:
    """Build the standard skipped ``StageOutput`` from a ``SkipDecision``.

    Caller checks ``decision.skip`` first; passing a ``skip=False`` decision
    here is a programming error.
    """
    extras: dict[str, Any] = {
        "skipped_unchanged": True,
        "skipped_reason": decision.reason or "skip predicate matched",
        "io_label": io_label,
        "input_count": 0,
        "kept_count": 0,
        "dropped_count": 0,
    }
    if decision.head_sha:
        extras["head_sha"] = decision.head_sha
    return StageOutput(communities=[], dropped=[], extras=extras)


def maybe_skipped_for_ingest(config: dict[str, Any], *, io_label: str) -> StageOutput | None:
    """Reduction-stage helper: skip iff ``ingest_skipped`` was set upstream.

    ``ingest`` decides via ``should_skip_gitnexus`` whether to invoke
    ``gitnexus analyze``. If it skipped, the workflow propagates
    ``ingest_skipped=True`` (plus the matching head_sha + reason) into
    ``cumulative_config``, and every downstream reduction stage reads
    those keys and short-circuits with the same metadata so the
    ``CODE_INDEX`` chip's sub-stage roll-up stays internally
    consistent.

    Returns ``None`` when the flag isn't set so the caller drops through
    to its real cypher work.
    """
    if not config.get("ingest_skipped"):
        return None
    reason = str(config.get("ingest_skip_reason") or "ingest cache hit")
    head_sha = config.get("ingest_head_sha")
    extras: dict[str, Any] = {
        "skipped_unchanged": True,
        "skipped_reason": reason,
        "io_label": io_label,
        "input_count": 0,
        "kept_count": 0,
        "dropped_count": 0,
    }
    if isinstance(head_sha, str) and head_sha:
        extras["head_sha"] = head_sha
    return StageOutput(communities=[], dropped=[], extras=extras)


__all__ = ["maybe_skipped_for_ingest", "stage_output_for_skip"]
