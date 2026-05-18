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

"""Cross-repo relationship arcs from real ``feature_to_repo`` links.

Previously this module emitted synthetic IMPORTS arcs whenever two repos
shared a top-level directory name (e.g. both had ``src/``) as a fallback
when the GitNexus pre-link path was active. That heuristic over-fired —
every repo in a workspace touches generic directory names, so the garden
filled with arcs that didn't correspond to any real dependency.

The dropped pre-link stage has been replaced by the synthesis pipeline's
``backend_link`` step, which writes PRIMARY + BACKEND rows into the
``feature_to_repo`` junction. ``collect_features`` already surfaces those
links as ``FeatureItem.linked_repos`` (primary first, then backends), so
this module now derives arcs from that field — a pure data transform
with no new DB queries.
"""

import structlog

from app.schemas.dashboard import RelationshipArc, TreeData

logger = structlog.get_logger(__name__)


def collect_cross_repo_relationships(tree: TreeData) -> None:
    """Emit one CALLS arc per unique cross-repo feature.

    Reads ``tree.features`` (already populated by ``collect_features``)
    and emits one ``RelationshipArc`` per ``(feature, primary_repo,
    backend_repo)`` triple. The first entry of ``linked_repos`` is the
    PRIMARY repo (where the feature lives); the rest are BACKEND repos
    whose API routes the feature calls. The frontend fans multiple arcs
    sharing the same repo pair into separate visible curves using
    ``feature_title`` as the grouping key.

    Args:
        tree: The tree data; ``tree.features`` and ``tree.repos`` must
            be populated first (this runs in step 10 of ``tree_data``).
    """
    if len(tree.repos) < 2:
        return

    # Build branch label per repo from the existing "first branch"
    # convention so ``RelationshipArc.source_branch`` / ``target_branch``
    # match how the rest of the tree describes a repo. Frontend
    # ``REL_COLORS`` reads only ``rel_type`` so branch names are
    # cosmetic for the arc itself but populate hover/inspect details.
    branch_by_repo: dict[str, str] = {}
    for repo in tree.repos:
        if repo.branches:
            branch_by_repo[repo.repo_name] = repo.branches[0].name

    # Dedupe by title — ``tree.features`` contains a primary row plus one
    # shadow row per backend repo for each feature; we only want to draw
    # arcs from the single canonical view of each feature.
    seen_titles: set[str] = set()
    arc_count = 0
    for feat in tree.features:
        if feat.title in seen_titles:
            continue
        seen_titles.add(feat.title)
        if len(feat.linked_repos) < 2:
            continue

        primary = feat.linked_repos[0]
        for backend in feat.linked_repos[1:]:
            if primary == backend:
                continue
            tree.relationships.append(
                RelationshipArc(
                    source_branch=branch_by_repo.get(primary, ""),
                    target_branch=branch_by_repo.get(backend, ""),
                    source_repo=primary,
                    target_repo=backend,
                    rel_type="CALLS",
                    weight=1,
                    feature_title=feat.title,
                )
            )
            arc_count += 1

    logger.info(
        "cross_repo_relationships",
        arc_count=arc_count,
        feature_count=len(seen_titles),
    )
