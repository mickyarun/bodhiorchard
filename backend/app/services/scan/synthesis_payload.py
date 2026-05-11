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

"""Build the trimmed payload that the live synthesis pipeline will send to Claude.

Computes and reports the exact payload shape so an operator can see
token cost before committing. This is also where we make a deliberate
split:

* Stage outputs keep up to ``files_per_meta`` (~30) files per community
  because file-path heuristics (Stage 2 ``filter_infra``) need a wide
  sample to reliably detect test/infra clusters.
* The synthesis payload trims to ~15 files per community because Claude
  reads them as evidence of feature scope, and the marginal signal of
  files 16-30 is tiny relative to the token cost.

We also surface ``source_count`` (how many original Leiden fragments
fed this community) and ``cohesion`` (the merge-weighted average), so
the synthesis prompt can hint to Claude which buckets are likely
single-feature (high cohesion + low source_count) vs. composites that
should be split into multiple features (low cohesion + many sources).
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.scan import Community

# Rough chars/token. OpenAI tokenisers and Claude's tokeniser hover
# around 3.5-4.0 chars/token for English code-flavoured text. 4 keeps
# the estimate slightly optimistic — fine for budgeting decisions.
_CHARS_PER_TOKEN = 4


def build_synthesis_payload(
    communities: list[Community],
    *,
    files_per_meta: int = 15,
) -> list[dict[str, Any]]:
    """Trim final-stage communities into the exact dicts a synthesis call would send.

    Order matches the input (typically already sorted by symbol_count
    descending from Stage 6 ``top_n``). Drops ``drop_reason`` rows so
    the payload only contains kept communities.
    """
    payload: list[dict[str, Any]] = []
    for c in communities:
        if c.drop_reason:
            continue
        payload.append(
            {
                "label": c.label,
                "symbol_count": c.symbol_count,
                "source_count": len(c.source_community_ids),
                "cohesion": _round_or_none(c.cohesion),
                "files": c.files[:files_per_meta],
            }
        )
    return payload


def estimate_payload_tokens(payload: list[dict[str, Any]]) -> dict[str, int]:
    """Return char + token estimates for a payload.

    Uses ``json.dumps`` with no indentation — that's what an actual
    synthesis call would serialise. Real cost depends on Claude's
    tokeniser, but the chars/4 heuristic is within ~10% in practice.
    """
    serialised = json.dumps(payload, separators=(",", ":"))
    chars = len(serialised)
    return {
        "chars": chars,
        "estimated_tokens": chars // _CHARS_PER_TOKEN,
        "community_count": len(payload),
    }


def _round_or_none(value: float | None) -> float | None:
    """Round cohesion to 3dp for readability, preserve None."""
    return None if value is None else round(value, 3)
