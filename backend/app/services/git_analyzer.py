"""Git history analyzer for extracting developer skill profiles.

Scans git log to determine per-author, per-module expertise based on
commit frequency, recency, and file-type distribution.
"""

import asyncio
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# How far back to scan by default
DEFAULT_SINCE = "6.months.ago"

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
    """Aggregated stats for a single author in a single module."""

    touch_count: int = 0
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
    skill_score: float
    last_touch: datetime | None


async def analyze_repo_skills(
    repo_path: str,
    since: str = DEFAULT_SINCE,
) -> list[DevSkillEntry]:
    """Scan git log for per-author, per-module skill data.

    Uses asyncio.create_subprocess_exec for safe subprocess execution.

    Args:
        repo_path: Absolute path to the git repository root.
        since: Git log --since value (e.g. "6.months.ago").

    Returns:
        List of DevSkillEntry objects with computed skill scores.
    """
    repo = Path(repo_path)
    if not repo.exists() or not (repo / ".git").exists():
        logger.error("git_analyzer_not_a_repo", path=repo_path)
        return []

    # Step 1: Get commit hashes with author info
    commits = await _get_commits(repo_path, since)
    if not commits:
        logger.info("git_analyzer_no_commits", repo=repo_path, since=since)
        return []

    logger.info("git_analyzer_commits_found", repo=repo_path, count=len(commits))

    # Step 2: For each commit, get changed files and accumulate per-author stats
    # author_key = email, module = top-level directory
    author_modules: dict[str, dict[str, ModuleStats]] = {}
    author_names: dict[str, str] = {}

    for commit_hash, email, name, commit_date in commits:
        author_names[email] = name
        files = await _get_commit_files(repo_path, commit_hash)

        for file_path in files:
            module = _file_to_module(file_path)
            lang = _file_to_language(file_path)

            if email not in author_modules:
                author_modules[email] = {}
            if module not in author_modules[email]:
                author_modules[email][module] = ModuleStats()

            stats = author_modules[email][module]
            stats.touch_count += 1
            if lang:
                stats.languages.add(lang)
            if commit_date and (stats.last_touch is None or commit_date > stats.last_touch):
                stats.last_touch = commit_date

    # Step 3: Compute skill scores
    now = datetime.now(UTC)
    entries: list[DevSkillEntry] = []

    for email, modules in author_modules.items():
        for module, stats in modules.items():
            recency_weight = _recency_weight(stats.last_touch, now)
            skill_score = min(1.0, stats.touch_count / 50.0) * recency_weight
            skill_score = round(skill_score, 2)

            entries.append(
                DevSkillEntry(
                    email=email,
                    author_name=author_names.get(email, email),
                    module=module,
                    languages=sorted(stats.languages),
                    touch_count=stats.touch_count,
                    skill_score=skill_score,
                    last_touch=stats.last_touch,
                )
            )

    logger.info(
        "git_analyzer_complete",
        repo=repo_path,
        authors=len(author_modules),
        entries=len(entries),
    )
    return entries


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
    since: str,
) -> list[tuple[str, str, str, datetime | None]]:
    """Get commit metadata from git log.

    Args:
        repo_path: Absolute path to the git repository root.
        since: Git log --since value.

    Returns:
        List of (hash, email, author_name, commit_date) tuples.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "log",
        "--format=%H|%ae|%an|%aI",
        "--no-merges",
        f"--since={since}",
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


async def _get_commit_files(repo_path: str, commit_hash: str) -> list[str]:
    """Get files changed in a specific commit.

    Args:
        repo_path: Absolute path to the git repository root.
        commit_hash: The commit SHA to inspect.

    Returns:
        List of file paths changed in the commit.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "diff-tree",
        "--no-commit-id",
        "-r",
        "--name-only",
        commit_hash,
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)

    if proc.returncode != 0:
        return []

    return [
        line
        for line in stdout.decode("utf-8", errors="replace").strip().split("\n")
        if line.strip()
    ]


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
