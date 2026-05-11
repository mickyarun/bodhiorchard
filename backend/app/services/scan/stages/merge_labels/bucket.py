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

"""Fold same-labelled communities into a single ``Community``.

Symbol-weighted aggregation:
* ``symbol_count`` summed across the bucket.
* ``files`` deduplicated union, preserving rank order from the largest
  fragment first, capped at ``files_per_label``.
* ``cohesion`` symbol-weighted-averaged so the merged value reflects
  combined cluster quality (None when no member reports cohesion).
* ``community_id`` of the merged row is the largest fragment's id;
  ``source_community_ids`` records every absorbed id for traceability.
* ``drop_reason`` preserved only when *every* constituent already had
  one (defensive — usually drop reasons are set by later stages).
"""

from __future__ import annotations

from app.schemas.scan import Community


def merge_bucket(
    label: str,
    members: list[Community],
    files_per_label: int,
) -> Community:
    """Fold one same-label bucket into a single ``Community``."""
    members_sorted = sorted(members, key=lambda c: c.symbol_count, reverse=True)
    anchor = members_sorted[0]

    total_symbols = sum(m.symbol_count for m in members_sorted)
    cohesion = _weighted_cohesion(members_sorted)
    files = _union_files(members_sorted, cap=files_per_label)
    source_ids = [m.community_id for m in members_sorted if m.community_id]

    drop_reasons = [m.drop_reason for m in members_sorted if m.drop_reason]
    drop_reason = drop_reasons[0] if len(drop_reasons) == len(members_sorted) else None

    return Community(
        label=label,
        heuristic_label=anchor.heuristic_label,
        symbol_count=total_symbols,
        cohesion=cohesion,
        files=files,
        drop_reason=drop_reason,
        community_id=anchor.community_id,
        source_community_ids=source_ids,
    )


def _weighted_cohesion(members: list[Community]) -> float | None:
    """Symbol-weighted average of cohesion across members with non-null cohesion.

    Falls back to ``None`` when no member reports cohesion — better than
    silently bucketing zero, which would mislead the UI.
    """
    weighted_sum = 0.0
    weight_total = 0
    for m in members:
        if m.cohesion is None:
            continue
        weighted_sum += m.cohesion * m.symbol_count
        weight_total += m.symbol_count
    if weight_total == 0:
        return None
    return weighted_sum / weight_total


def _union_files(members: list[Community], *, cap: int) -> list[str]:
    """Deduplicated union of files, preserving rank order from the largest fragment."""
    seen: set[str] = set()
    out: list[str] = []
    for member in members:
        for f in member.files:
            if f in seen:
                continue
            seen.add(f)
            out.append(f)
            if len(out) >= cap:
                return out
    return out
