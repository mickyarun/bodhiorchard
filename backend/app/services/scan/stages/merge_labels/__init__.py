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

# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Stage 1.5 — Merge same-labelled communities.

The code indexer (``app.services.code_indexer.label_cluster``) names
each cluster with a single TF-IDF-derived path token. Two distinct
clusters can land on the same label when the repo organises the same
domain across multiple roots — e.g. ATOACore has clusters from
``src/services/ais/``, ``src/repository/ais/`` and ``src/utils/ais/``
all labelled ``ais`` after the per-cluster merge_by_dir step.
Downstream stages then either fragment the synthesis input or — worse
— quietly cannibalise the smaller fragments inside hierarchical
re-cluster, hiding important areas behind a sibling's name.

This stage runs *before* infra filtering so we operate on a
deduplicated set everywhere downstream. Bucket-by-label folds them
into one community per label, weighted-aggregating their stats, with
the unioned file set capped at ``files_per_label`` so Stage 2's
file-path heuristic still has signal.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import maybe_skipped_for_ingest
from app.services.scan.stages.merge_labels.bucket import merge_bucket

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Bucket by ``label`` and fold same-labelled communities into one row.

    Config:
        - ``files_per_label`` (int, default 30): cap on the unioned file
          list per merged community. Larger buckets see more files,
          which helps Stage 2's file-path heuristic detect test clusters.
    """
    if (
        skipped := maybe_skipped_for_ingest(config, io_label="communities → de-duped communities")
    ) is not None:
        return skipped
    if not communities:
        return StageOutput(communities=[], dropped=[], extras={"reason": "no input"})

    files_per_label = int(config.get("files_per_label", 30))
    merged, duplicate_label_count = _merge_buckets(communities, files_per_label)

    extras: dict[str, Any] = {
        "input_count": len(communities),
        "merged_count": len(merged),
        "labels_with_duplicates": duplicate_label_count,
        "files_per_label": files_per_label,
        "io_label": "communities → de-duped communities",
    }
    logger.info(
        "scan_merge_labels_done",
        repo=ctx.repo_name,
        input_count=len(communities),
        merged_count=len(merged),
        labels_with_duplicates=duplicate_label_count,
    )
    return StageOutput(communities=merged, dropped=[], extras=extras)


def _merge_buckets(
    communities: list[Community],
    files_per_label: int,
) -> tuple[list[Community], int]:
    """Bucket by label, fold each bucket, and sort by symbol_count desc."""
    buckets: dict[str, list[Community]] = defaultdict(list)
    for comm in communities:
        buckets[comm.label].append(comm)

    merged: list[Community] = []
    duplicate_label_count = 0
    for label, members in buckets.items():
        if len(members) > 1:
            duplicate_label_count += 1
        merged.append(merge_bucket(label, members, files_per_label))
    merged.sort(key=lambda c: c.symbol_count, reverse=True)
    return merged, duplicate_label_count


__all__ = ["run"]
