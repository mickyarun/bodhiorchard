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

"""Git history metrics + health scoring for the Living Tree Dashboard.

Collects commit data from ``git log``, assigns evergreen colors to leaves,
computes branch + repo health from bug prevalence, and classifies each
repo's visual growth stage (sprout / sapling / medium / mature).

Note: Uses ``asyncio.create_subprocess_exec`` (the safe, non-shell
variant) for all git subprocess calls. No shell interpolation occurs.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog

from app.schemas.dashboard import BranchData, LeafData, RepoLimbData, TreeData

logger = structlog.get_logger(__name__)


async def collect_git_history(
    tree: TreeData,
    tracked_repos: list[tuple[str, str]],
    file_branch_map: dict[str, str],
    bugged_modules: set[str],
) -> None:
    """Collect commit data from git log for leaves and project age.

    Uses the evergreen color model:
    - bugged files -> wilted (brown)
    - <=7 days -> freshGreen (bright)
    - <=30 days -> mediumGreen
    - >30 days -> deepGreen (stable, healthy)

    Args:
        tree: Mutable tree accumulator.
        tracked_repos: List of (path, name) tuples.
        file_branch_map: File-to-branch mapping from repo_structure.
        bugged_modules: Set of module names flagged by bugs.
    """
    now = datetime.now(UTC)

    for repo_path, _repo_name in tracked_repos:
        repo_limb = next((r for r in tree.repos if r.repo_path == repo_path), None)
        if not repo_limb:
            continue

        repo_branches = repo_limb.branches

        try:
            # Get total file count
            proc = await asyncio.create_subprocess_exec(
                "git",
                "ls-files",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            files = stdout.decode().strip().splitlines()
            file_count = len(files)
            tree.total_files += file_count
            repo_limb.total_files = file_count

            # Get first commit date for project age
            proc = await asyncio.create_subprocess_exec(
                "git",
                "log",
                "--reverse",
                "--format=%aI",
                "-1",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            first_date_str = stdout.decode().strip()
            if first_date_str:
                first_date = datetime.fromisoformat(first_date_str)
                age = (now - first_date).days
                tree.project_age_days = max(tree.project_age_days, age)

            # Get recent commits (last 90 days) for leaves
            since_date = (now - timedelta(days=90)).strftime("%Y-%m-%d")
            proc = await asyncio.create_subprocess_exec(
                "git",
                "log",
                f"--since={since_date}",
                "--format=%H %aI",
                "--name-only",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            lines = stdout.decode().strip().splitlines()

            current_date: datetime | None = None
            leaf_count = 0
            max_leaves = 200
            total_commits = 0

            for line in lines:
                if not line.strip():
                    continue
                parts = line.split(" ", 2)
                if len(parts) >= 2 and len(parts[0]) == 40:
                    try:
                        current_date = datetime.fromisoformat(parts[1])
                        total_commits += 1
                    except ValueError:
                        current_date = None
                elif current_date and leaf_count < max_leaves:
                    file_path = line.strip()
                    age_days = (now - current_date).days

                    is_bugged = _is_file_bugged(file_path, bugged_modules)
                    if is_bugged:
                        color = "wilted"
                    elif age_days <= 7:
                        color = "freshGreen"
                    elif age_days <= 30:
                        color = "mediumGreen"
                    else:
                        color = "deepGreen"

                    branch_name = _file_to_branch(file_path, repo_branches, file_branch_map)
                    for branch in repo_branches:
                        if branch.name == branch_name:
                            branch.leaves.append(
                                LeafData(
                                    path=file_path,
                                    age_days=age_days,
                                    color=color,
                                    branch_name=branch_name,
                                    has_bug=is_bugged,
                                )
                            )
                            branch.commit_count += 1
                            leaf_count += 1
                            break

            repo_limb.total_commits = total_commits

        except Exception:
            logger.warning("git_history_collect_failed", path=repo_path)

    # Compute branch health (bug-based)
    for repo_limb in tree.repos:
        for branch in repo_limb.branches:
            branch.health = _compute_branch_health(branch)
        repo_limb.health = _compute_repo_health(repo_limb)


def classify_repo_growth_stage(repo_limb: RepoLimbData) -> str:
    """Classify a repo's visual growth stage based on size and activity.

    Returns:
        One of ``"sprout"``, ``"sapling"``, ``"medium"``, ``"mature"``.
    """
    files = repo_limb.total_files
    branches = len(repo_limb.branches)
    commits = repo_limb.total_commits

    if files < 20 and commits < 50:
        return "sprout"
    if files < 100 and branches < 5:
        return "sapling"
    if files < 500:
        return "medium"
    return "mature"


# ─── Private helpers ──────────────────────────────────────────────────────


def _is_file_bugged(file_path: str, bugged_modules: set[str]) -> bool:
    """Check if a file belongs to a bugged module."""
    file_lower = file_path.lower()
    for module in bugged_modules:
        module_lower = module.lower()
        if file_lower.startswith(module_lower + "/") or file_lower == module_lower:
            return True
        first_component = file_path.split("/")[0].lower()
        if first_component == module_lower:
            return True
    return False


def _file_to_branch(
    file_path: str,
    branches: list[BranchData],
    file_branch_map: dict[str, str],
) -> str:
    """Map a file path to the best-matching branch name."""
    if file_path in file_branch_map:
        return file_branch_map[file_path]

    parts = file_path.split("/")
    if len(parts) >= 2:
        module = parts[0]
        for branch in branches:
            if module.lower() in branch.name.lower():
                return branch.name
    return branches[0].name if branches else "root"


def _compute_branch_health(branch: BranchData) -> str:
    """Classify branch health based on bug presence."""
    bugged_leaves = sum(1 for leaf in branch.leaves if leaf.has_bug)
    branch.bug_count = bugged_leaves
    total = len(branch.leaves)

    if bugged_leaves > 0:
        ratio = bugged_leaves / max(total, 1)
        if ratio >= 0.3:
            return "wilted"
        return "dormant"

    if total == 0:
        return "dormant"

    fresh = sum(1 for leaf in branch.leaves if leaf.color in ("freshGreen", "mediumGreen"))
    if fresh / total >= 0.3:
        return "thriving"
    return "healthy"


def _compute_repo_health(repo_limb: RepoLimbData) -> str:
    """Compute overall repo health from its branches."""
    if not repo_limb.branches:
        return "dormant"

    healths = [b.health for b in repo_limb.branches]
    if "wilted" in healths:
        return "wilted"
    if all(h == "dormant" for h in healths):
        return "dormant"
    if any(h == "thriving" for h in healths):
        return "thriving"
    return "healthy"
