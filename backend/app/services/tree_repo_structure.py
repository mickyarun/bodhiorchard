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

"""Repo structure + branch discovery for the Living Tree Dashboard.

Builds per-repo ``RepoLimbData`` from the git working tree's directory
structure. Each top-level directory becomes a "branch" (visual limb)
on the tree, and a file-to-branch mapping dict is returned for use by
downstream collectors (git history, feature placement).

Note: Uses ``asyncio.create_subprocess_exec`` (the safe, non-shell
variant) for all git subprocess calls. No shell interpolation occurs.
"""

import asyncio

import structlog

from app.schemas.dashboard import BranchData, RepoLimbData, TreeData

logger = structlog.get_logger(__name__)

# Hardcoded branch count for single-repo visual balance
SINGLE_REPO_BRANCH_COUNT = 8


async def collect_repo_structure(
    tree: TreeData,
    tracked_repos: list[tuple[str, str]],
) -> dict[str, str]:
    """Build per-repo RepoLimbData from directory structure.

    Returns a file->branch_name mapping for use by collect_git_history.

    Args:
        tree: Mutable tree accumulator.
        tracked_repos: List of (path, name) tuples for tracked repositories.

    Returns:
        A dict mapping relative file paths to their branch names.
    """
    file_branch_map: dict[str, str] = {}
    is_single_repo = len(tracked_repos) == 1

    for repo_path, repo_name in tracked_repos:
        repo_limb = RepoLimbData(repo_name=repo_name, repo_path=repo_path)

        if is_single_repo:
            await _load_hardcoded_branches(repo_limb, repo_path, file_branch_map)
        else:
            await _load_branches_from_directories(repo_limb, repo_path, file_branch_map)

        tree.repos.append(repo_limb)

    return file_branch_map


async def _load_hardcoded_branches(
    repo_limb: RepoLimbData,
    repo_path: str,
    file_branch_map: dict[str, str],
) -> None:
    """Create hardcoded 6-8 branches from top-level dirs for a single-repo tree."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-files",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        files = stdout.decode().strip().splitlines()

        dir_counts: dict[str, int] = {}
        for f in files:
            parts = f.split("/", 1)
            if len(parts) >= 2:
                top_dir = parts[0]
                if top_dir.startswith("."):
                    continue
                dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
                file_branch_map[f] = top_dir
            else:
                file_branch_map[f] = "root"
                dir_counts["root"] = dir_counts.get("root", 0) + 1

        sorted_dirs = sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)
        target = min(SINGLE_REPO_BRANCH_COUNT, max(len(sorted_dirs), 6))

        if len(sorted_dirs) > target:
            main_dirs = sorted_dirs[: target - 1]
            other_count = sum(c for _, c in sorted_dirs[target - 1 :])
            main_dirs.append(("other", other_count))
            merged_names = {name for name, _ in sorted_dirs[target - 1 :]}
            for f, branch in list(file_branch_map.items()):
                if branch in merged_names:
                    file_branch_map[f] = "other"
            sorted_dirs = main_dirs
        elif len(sorted_dirs) < 6:
            generic_names = ["core", "utils", "config", "docs", "tests", "scripts"]
            for name in generic_names:
                if len(sorted_dirs) >= 6:
                    break
                if name not in dict(sorted_dirs):
                    sorted_dirs.append((name, 0))

        for dir_name, count in sorted_dirs:
            repo_limb.branches.append(
                BranchData(
                    name=dir_name,
                    file_count=count,
                    commit_count=0,
                    health="healthy",
                )
            )

        repo_limb.total_files = len(files)
        logger.info(
            "hardcoded_branches_loaded",
            count=len(repo_limb.branches),
            repo=repo_path,
        )

    except Exception:
        logger.warning("hardcoded_branches_failed", path=repo_path)


async def _load_branches_from_directories(
    repo_limb: RepoLimbData,
    repo_path: str,
    file_branch_map: dict[str, str],
) -> None:
    """Create branches from top-level directory structure as fallback."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-files",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        files = stdout.decode().strip().splitlines()

        dir_counts: dict[str, int] = {}
        for f in files:
            parts = f.split("/", 1)
            if len(parts) >= 2:
                top_dir = parts[0]
                if top_dir.startswith("."):
                    continue
                dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
                file_branch_map[f] = top_dir
            else:
                file_branch_map[f] = "root"
                dir_counts["root"] = dir_counts.get("root", 0) + 1

        sorted_dirs = sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)

        if len(sorted_dirs) > 20:
            main_dirs = sorted_dirs[:19]
            other_count = sum(c for _, c in sorted_dirs[19:])
            main_dirs.append(("other", other_count))
            merged_names = {name for name, _ in sorted_dirs[19:]}
            for f, branch in list(file_branch_map.items()):
                if branch in merged_names:
                    file_branch_map[f] = "other"
            sorted_dirs = main_dirs

        for dir_name, count in sorted_dirs:
            repo_limb.branches.append(
                BranchData(
                    name=dir_name,
                    file_count=count,
                    commit_count=0,
                    health="healthy",
                )
            )

        repo_limb.total_files = len(files)
        logger.info(
            "directory_branches_loaded",
            count=len(sorted_dirs),
            repo=repo_path,
        )

    except Exception:
        logger.warning("directory_branches_failed", path=repo_path)
