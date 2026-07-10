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

"""Git history analyzer for extracting developer skill profiles.

Scans git log to determine per-author, per-module expertise based on
commit frequency, recency, and file-type distribution.
"""

import asyncio
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# How far back to scan by default
DEFAULT_SINCE = "6.months.ago"

# When the ``since`` window is empty, ``analyze_repo_skills`` retries over full
# history. Cap that walk to the most-recent N commits so the per-commit numstat
# subprocess fan-out can't blow up on a repo with tens of thousands of commits;
# the newest commits are also the most relevant for a skill profile.
_FULL_HISTORY_FALLBACK_MAX_COMMITS = 2000

# Weighted lines that saturate a skill_score to 1.0. Tuned so a developer
# who wrote ~1k lines of feature code recently lands at score 1.0, and a
# developer with a few hundred old lines stays well above the downstream
# ``list_active_skill_devs`` floor of 0.1.
_SCORE_NORMALIZER = 1000.0

# Directories/files to skip during skill analysis (tooling, not code)
_SKIP_SKILL_PATHS = frozenset(
    {
        ".claude",
        ".githooks",
        ".bodhiorchard",
        ".github",
        ".vscode",
        ".idea",
    }
)

# Generated / lock / minified files that bloat line counts without
# reflecting authorship. Matched by basename suffix.
_NOISE_BASENAMES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "poetry.lock",
        "uv.lock",
        "Gemfile.lock",
        "composer.lock",
    }
)
_NOISE_SUFFIXES = (".min.js", ".min.css", ".map")


# Extension-to-language mapping
LANG_MAP: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".js": "JavaScript",
    ".tsx": "React/TSX",
    ".jsx": "React/JSX",
    ".vue": "Vue",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
}


@dataclass
class ModuleStats:
    """Aggregated stats for a single author in a single module.

    ``weighted_contribution`` is the sum of ``lines_added * recency_weight``
    over each commit — recency is baked in per-commit so older commits
    decay individually rather than the whole score being scaled by
    ``last_touch``.
    """

    touch_count: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    weighted_contribution: float = 0.0
    languages: set[str] = field(default_factory=set)
    last_touch: datetime | None = None


@dataclass
class DevSkillEntry:
    """Final skill entry for one author in one module."""

    email: str
    author_name: str
    module: str
    languages: list[str]
    touch_count: int
    lines_added: int
    lines_removed: int
    skill_score: float
    last_touch: datetime | None
    feature_id: uuid.UUID | None = None


# (feature_name, path_prefixes, feature_id)
FeatureMapEntry = tuple[str, list[str], uuid.UUID]
FeatureMap = list[FeatureMapEntry]


def _file_to_feature(
    file_path: str,
    feature_map: FeatureMap,
) -> tuple[str, uuid.UUID] | None:
    """Map a file path to a feature name via strict code_locations prefix match.

    Relies on code_locations paths from the junction table (populated by
    the LLM during synthesis). No fuzzy fallback — if a file doesn't match
    any feature's code_locations prefixes, it is skipped.

    Args:
        file_path: Relative file path from repo root.
        feature_map: List of (feature_name, [path_prefixes], feature_id)
            sorted by prefix length descending (longest first).

    Returns:
        Tuple of (feature_name, feature_id), or None if unmatched.
    """
    for feat_name, prefixes, feat_id in feature_map:
        for prefix in prefixes:
            if file_path.startswith(prefix):
                return feat_name, feat_id
    return None


async def analyze_repo_skills(
    repo_path: str,
    since: str = DEFAULT_SINCE,
    feature_map: FeatureMap | None = None,
    branch: str | None = None,
) -> list[DevSkillEntry]:
    """Scan git log for per-author, per-module skill data.

    Uses asyncio.create_subprocess_exec for safe subprocess execution.

    Args:
        repo_path: Absolute path to the git repository root.
        since: Git log --since value (e.g. "6.months.ago").
        feature_map: Optional feature-name-to-paths mapping. When provided,
            files are mapped to feature names instead of directory names.
        branch: Optional branch to walk instead of HEAD. Gitflow repos
            should pass ``develop_branch`` so squash-merged authorship
            survives — main only retains the squasher's name.

    Returns:
        List of DevSkillEntry objects with computed skill scores.
    """
    repo = Path(repo_path)
    if not repo.exists() or not (repo / ".git").exists():
        logger.error("git_analyzer_not_a_repo", path=repo_path)
        return []

    # Step 1: Get commit hashes with author info.
    commits = await _get_commits(repo_path, since, branch=branch)
    if not commits:
        # Fallback: nothing in the recent window. Common on a first-time scan
        # of a repo whose history predates ``since`` (or a low-activity /
        # sample repo). Retry over history (most-recent N, capped) so skill
        # profiles still populate — the per-commit recency weighting below
        # already down-weights old work, so including old commits is safe and
        # strictly better than emitting zero profiles. The cap keeps the
        # numstat fan-out bounded on deep histories.
        commits = await _get_commits(
            repo_path,
            since=None,
            branch=branch,
            max_count=_FULL_HISTORY_FALLBACK_MAX_COMMITS,
        )
        if commits:
            logger.info(
                "git_analyzer_full_history_fallback",
                repo=repo_path,
                since=since,
                branch=branch,
                count=len(commits),
            )
    if not commits:
        logger.info("git_analyzer_no_commits", repo=repo_path, since=since, branch=branch)
        return []

    logger.info(
        "git_analyzer_commits_found",
        repo=repo_path,
        count=len(commits),
        branch=branch,
    )

    # Step 2: For each commit, accumulate per-author stats weighted by
    # the commit's own age. Per-commit weighting (instead of a single
    # last_touch multiplier) lets an old high-volume initial commit
    # dominate over many small recent fixes.
    now = datetime.now(UTC)
    author_modules: dict[str, dict[str, ModuleStats]] = {}
    author_names: dict[str, str] = {}
    module_feature_ids: dict[str, uuid.UUID | None] = {}

    for commit_hash, email, name, commit_date in commits:
        author_names[email] = name
        commit_weight = _recency_weight(commit_date, now)
        numstat = await _get_commit_numstat(repo_path, commit_hash)

        for file_path, added, deleted in numstat:
            if _should_skip_path(file_path):
                continue

            lang = _file_to_language(file_path)
            if lang is None:
                continue  # Code files only — drops fixtures, lock files, data dumps

            if feature_map:
                match = _file_to_feature(file_path, feature_map)
                if match is None:
                    continue
                module, feat_id = match
                module_feature_ids[module] = feat_id
            else:
                module = _file_to_module(file_path)

            stats = author_modules.setdefault(email, {}).setdefault(module, ModuleStats())
            stats.touch_count += 1
            stats.lines_added += added
            stats.lines_removed += deleted
            stats.weighted_contribution += added * commit_weight
            stats.languages.add(lang)
            if commit_date and (stats.last_touch is None or commit_date > stats.last_touch):
                stats.last_touch = commit_date

    # Step 3: Compute skill scores from accumulated weighted contribution
    entries: list[DevSkillEntry] = []
    for email, modules in author_modules.items():
        for module, stats in modules.items():
            skill_score = round(min(1.0, stats.weighted_contribution / _SCORE_NORMALIZER), 2)
            entries.append(
                DevSkillEntry(
                    email=email,
                    author_name=author_names.get(email, email),
                    module=module,
                    languages=sorted(stats.languages),
                    touch_count=stats.touch_count,
                    lines_added=stats.lines_added,
                    lines_removed=stats.lines_removed,
                    skill_score=skill_score,
                    last_touch=stats.last_touch,
                    feature_id=module_feature_ids.get(module),
                )
            )

    logger.info(
        "git_analyzer_complete",
        repo=repo_path,
        authors=len(author_modules),
        entries=len(entries),
    )
    return entries


def _should_skip_path(file_path: str) -> bool:
    """Return True for tooling directories, dotfiles, or noise files."""
    fp = Path(file_path)
    if not fp.parts:
        return True
    top_dir = fp.parts[0]
    if top_dir in _SKIP_SKILL_PATHS or top_dir.startswith("."):
        return True
    name = fp.name
    if name in _NOISE_BASENAMES:
        return True
    return any(name.endswith(suffix) for suffix in _NOISE_SUFFIXES)


async def get_head_sha(repo_path: str) -> str | None:
    """Get the current HEAD commit SHA for a repository.

    Args:
        repo_path: Absolute path to the git repository root.

    Returns:
        The HEAD SHA string, or None on failure.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()
    except (TimeoutError, FileNotFoundError, OSError):
        pass
    return None


@dataclass
class DiffResult:
    """Result of a git diff between two commits."""

    changed_files: list[str]
    deleted_files: list[str]
    total_repo_files: int


async def get_diff_since(repo_path: str, since_sha: str) -> DiffResult:
    """Get detailed diff between a commit SHA and HEAD.

    Uses --name-status to distinguish modified/added vs deleted files,
    and counts total tracked files for the 30% threshold check.

    Args:
        repo_path: Absolute path to the git repository root.
        since_sha: The starting commit SHA.

    Returns:
        DiffResult with changed files, deleted files, and total file count.
    """
    changed: list[str] = []
    deleted: list[str] = []
    total_files = 0

    # Get diff with status codes (M=modified, A=added, D=deleted, R=renamed)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--name-status",
            f"{since_sha}..HEAD",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0:
            for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t", 2)
                if len(parts) < 2:
                    continue
                status_code = parts[0].strip()
                file_path = parts[1].strip()
                if status_code.startswith("D"):
                    deleted.append(file_path)
                else:
                    changed.append(file_path)
                    # For renames (R100\told\tnew), also mark old path as deleted
                    if status_code.startswith("R") and len(parts) == 3:
                        deleted.append(file_path)
                        changed.append(parts[2].strip())
    except (TimeoutError, FileNotFoundError, OSError):
        pass

    # Count total tracked files for threshold calculation
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-files",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            total_files = len(
                [
                    line
                    for line in stdout.decode("utf-8", errors="replace").strip().split("\n")
                    if line.strip()
                ]
            )
    except (TimeoutError, FileNotFoundError, OSError):
        pass

    return DiffResult(
        changed_files=changed,
        deleted_files=deleted,
        total_repo_files=total_files,
    )


async def get_changed_files_since(repo_path: str, since_sha: str) -> list[str]:
    """Get files changed between a commit SHA and HEAD (simple list).

    Args:
        repo_path: Absolute path to the git repository root.
        since_sha: The starting commit SHA.

    Returns:
        List of changed file paths relative to the repo root.
    """
    diff = await get_diff_since(repo_path, since_sha)
    return diff.changed_files + diff.deleted_files


async def _get_commits(
    repo_path: str,
    since: str | None,
    branch: str | None = None,
    max_count: int | None = None,
) -> list[tuple[str, str, str, datetime | None]]:
    """Get commit metadata from git log.

    Args:
        repo_path: Absolute path to the git repository root.
        since: Git log --since value.
        branch: Optional branch to walk. ``None`` walks HEAD as ``git log``
            does by default. If the named branch doesn't exist, falls
            back to HEAD so misconfigured repos still produce output.

    Returns:
        List of (hash, email, author_name, commit_date) tuples.
    """
    walk_ref = await _resolve_walk_ref(repo_path, branch)
    # ``since=None`` walks the entire history (no time window) — used by the
    # full-history fallback in ``analyze_repo_skills`` when the recent window
    # is empty.
    git_args = ["git", "log", walk_ref, "--format=%H|%ae|%an|%aI", "--no-merges"]
    if since is not None:
        git_args.append(f"--since={since}")
    if max_count is not None:
        # Cap the walk (most-recent N) so the per-commit numstat fan-out in
        # ``analyze_repo_skills`` stays bounded on deep histories.
        git_args.append(f"--max-count={max_count}")
    proc = await asyncio.create_subprocess_exec(
        *git_args,
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)

    if proc.returncode != 0:
        return []

    commits: list[tuple[str, str, str, datetime | None]] = []
    for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        commit_hash, email, name, date_str = parts
        try:
            commit_date = datetime.fromisoformat(date_str)
        except ValueError:
            commit_date = None
        commits.append((commit_hash.strip(), email.strip(), name.strip(), commit_date))

    return commits


async def _get_commit_numstat(repo_path: str, commit_hash: str) -> list[tuple[str, int, int]]:
    """Get per-file line-change counts for one commit.

    Runs ``git diff-tree --numstat -M`` and parses the output into
    ``(path, added, deleted)`` triples. The ``-M`` flag is essential:
    without it, a directory rename re-attributes every line of the
    moved files to whoever did the rename.

    Binary files (numstat emits ``-\\t-`` for them) are filtered out
    so they don't contribute to line totals.

    Args:
        repo_path: Absolute path to the git repository root.
        commit_hash: The commit SHA to inspect.

    Returns:
        List of (path, lines_added, lines_removed) triples.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "diff-tree",
        "--no-commit-id",
        "-r",
        "-M",
        "--root",
        "-z",
        "--numstat",
        commit_hash,
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)

    if proc.returncode != 0:
        return []

    return _parse_numstat_z(stdout.decode("utf-8", errors="replace"))


def _parse_numstat_z(raw: str) -> list[tuple[str, int, int]]:
    """Parse ``git diff-tree --numstat -z`` output into (path, added, deleted).

    The ``-z`` format avoids the three rename-encoding shapes that
    plain ``--numstat`` produces (``old => new``, ``dir/{old => new}/f``,
    ``{old => new}``) by emitting each record NUL-terminated:

    - Non-rename: ``"<added>\\t<deleted>\\t<path>\\0"``
    - Rename:     ``"<added>\\t<deleted>\\t\\0<old>\\0<new>\\0"`` — the
      tail is empty after the second tab, then ``<old>`` and ``<new>``
      arrive as the next two NUL-delimited chunks.

    Binary files emit ``-\\t-`` and are filtered out.
    """
    chunks = raw.split("\0")
    results: list[tuple[str, int, int]] = []
    i = 0
    while i < len(chunks):
        head = chunks[i]
        if not head:
            i += 1
            continue
        fields = head.split("\t")
        if len(fields) < 3:
            i += 1
            continue
        added_s, deleted_s, inline_path = fields[0], fields[1], fields[2]
        if added_s == "-" or deleted_s == "-":
            i += 1 if inline_path else 3
            continue
        try:
            added = int(added_s)
            deleted = int(deleted_s)
        except ValueError:
            i += 1
            continue
        if inline_path:
            results.append((inline_path, added, deleted))
            i += 1
        elif i + 2 < len(chunks):
            # Rename: <old>, <new> follow as separate NUL records;
            # credit the new path so future commits aggregate cleanly.
            results.append((chunks[i + 2], added, deleted))
            i += 3
        else:
            i += 1
    return results


async def _resolve_walk_ref(repo_path: str, branch: str | None) -> str:
    """Resolve which ref ``git log`` should walk.

    Returns ``branch`` when it exists locally; otherwise falls back to
    ``HEAD`` so a missing/misconfigured branch can't silently produce
    zero commits. ``None`` always means HEAD.
    """
    if not branch:
        return "HEAD"
    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/heads/{branch}",
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=10)
    except TimeoutError:
        return "HEAD"
    if proc.returncode == 0:
        return branch
    logger.warning("git_analyzer_branch_missing", repo=repo_path, branch=branch, fallback="HEAD")
    return "HEAD"


def _file_to_module(file_path: str) -> str:
    """Map a file path to its top-level module name.

    Args:
        file_path: Relative file path from repo root.

    Returns:
        The first directory component, or "root" for top-level files.
    """
    parts = Path(file_path).parts
    if len(parts) <= 1:
        return "root"
    return parts[0]


def _file_to_language(file_path: str) -> str | None:
    """Detect the programming language from file extension.

    Args:
        file_path: Relative file path.

    Returns:
        Language name string, or None if unknown.
    """
    suffix = Path(file_path).suffix.lower()
    return LANG_MAP.get(suffix)


def _recency_weight(last_touch: datetime | None, now: datetime) -> float:
    """Compute a recency weight between 0.3 and 1.0.

    More recent contributions get higher weight. Contributions older than
    6 months get the minimum weight of 0.3.

    Args:
        last_touch: The datetime of the last contribution.
        now: The current datetime.

    Returns:
        Weight value between 0.3 and 1.0.
    """
    if last_touch is None:
        return 0.3

    # Make both timezone-aware for comparison
    if last_touch.tzinfo is None:
        last_touch = last_touch.replace(tzinfo=UTC)

    days_ago = (now - last_touch).days
    if days_ago <= 0:
        return 1.0

    # Exponential decay: half-life of ~90 days, minimum 0.3
    decay = math.exp(-days_ago / 130.0)
    return max(0.3, decay)
