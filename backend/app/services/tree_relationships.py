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

"""Cross-repo relationship detection for the Living Tree Dashboard.

Creates inter-service arcs between repos that share branch/community
names (e.g. "User" in a core-backend repo and "User" in a payment-service repo). Pure
data transformation — no DB queries or subprocess calls.
"""

import structlog

from app.schemas.dashboard import RelationshipArc, TreeData

logger = structlog.get_logger(__name__)


def collect_cross_repo_relationships(tree: TreeData) -> None:
    """Create inter-service arcs between repos sharing community names.

    When two repos both have a community (branch) with the same name —
    e.g. "User" in a core-backend repo and "User" in a payment-service repo — it signals a
    shared domain concept. We emit a synthetic IMPORTS arc so the garden
    draws a visible connection between those trees.

    Args:
        tree: The tree data; ``tree.repos`` must be fully populated
            (branches assigned) before this function runs.
    """
    if len(tree.repos) < 2:
        return

    # Map community name → list of repo names that contain it
    comm_repos: dict[str, list[str]] = {}
    for repo in tree.repos:
        for branch in repo.branches:
            comm_repos.setdefault(branch.name, []).append(repo.repo_name)

    cross_count = 0
    shared_names: list[str] = []
    for comm_name, repos in comm_repos.items():
        if len(repos) < 2:
            continue
        shared_names.append(comm_name)
        # Create arcs between each pair of repos sharing this community
        for i in range(len(repos)):
            for j in range(i + 1, len(repos)):
                tree.relationships.append(
                    RelationshipArc(
                        source_branch=comm_name,
                        target_branch=comm_name,
                        source_repo=repos[i],
                        target_repo=repos[j],
                        rel_type="IMPORTS",
                        weight=3,
                    )
                )
                cross_count += 1

    logger.info(
        "cross_repo_relationships",
        count=cross_count,
        shared_communities=shared_names[:10],
        total_relationships=len(tree.relationships),
    )
