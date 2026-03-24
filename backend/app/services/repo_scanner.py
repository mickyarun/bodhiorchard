"""GitNexus integration and documentation extraction for codebase indexing.

Runs the GitNexus CLI (via npx) to analyze a repository, then queries the
knowledge graph for communities (feature clusters) and execution flows.
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from app.services.gitnexus_utils import find_npx as _find_npx  # noqa: I001
from app.services.gitnexus_utils import parse_cypher_community_list as _parse_cypher_community_list
from app.services.gitnexus_utils import parse_markdown_table as _parse_markdown_table
from app.services.gitnexus_utils import parse_single_column as _parse_single_column
from app.services.gitnexus_utils import run_cypher as _run_cypher
from app.services.gitnexus_utils import run_npx as _run_npx

logger = structlog.get_logger(__name__)


@dataclass
class FeatureEntry:
    """A feature cluster extracted from the GitNexus knowledge graph."""

    name: str
    overview: str
    files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class ProcessEntry:
    """An execution flow extracted from the GitNexus knowledge graph."""

    name: str
    step_count: int


@dataclass
class DocEntry:
    """A documentation file extracted from the repository."""

    title: str
    content: str
    source_ref: str


@dataclass
class GitNexusResult:
    """Structured output from a GitNexus indexing run."""

    repo_overview: str = ""
    features: list[FeatureEntry] = field(default_factory=list)
    processes: list[ProcessEntry] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    success: bool = False
    error: str | None = None


class GitNexusNotInstalledError(Exception):
    """Raised when npx/Node.js is not available to run GitNexus."""


## _find_npx, _run_npx_sync, _run_npx, _run_cypher are imported from gitnexus_utils


async def index_repo_with_gitnexus(
    repo_path: str,
    *,
    force: bool = True,
) -> GitNexusResult:
    """Run GitNexus analyze then query the knowledge graph for features.

    Steps:
    1. Run `gitnexus analyze` to build/update the knowledge graph
    2. Query communities (feature clusters) with their member files
    3. Query execution flows (processes)
    4. Read meta.json for stats
    5. Read README.md first paragraph as repo overview

    Args:
        repo_path: Absolute path to the git repository root.
        force: If True, pass ``--force`` to re-index even if unchanged.
            Incremental scans pass False so GitNexus skips if the source
            hash is unchanged (fast no-op).

    Returns:
        GitNexusResult with communities as features and execution flows.

    Raises:
        GitNexusNotInstalledError: If npx is not found on the system.
    """
    result = GitNexusResult()
    repo = Path(repo_path)
    repo_name = repo.name  # Directory name used by gitnexus --repo flag

    if not repo.exists() or not (repo / ".git").exists():
        result.error = f"Not a valid git repository: {repo_path}"
        return result

    npx = _find_npx()
    if not npx:
        raise GitNexusNotInstalledError(
            "Node.js (npx) is required for codebase indexing. "
            "Install Node.js from https://nodejs.org/ and restart Bodhigrove."
        )

    # Step 1: Run gitnexus analyze
    try:
        logger.info("gitnexus_starting", repo=repo_path, force=force)
        analyze_args = ["analyze"]
        if force:
            analyze_args.append("--force")
        analyze_args.append(str(repo))
        stdout, stderr, returncode = await _run_npx(
            npx,
            analyze_args,
            cwd=str(repo),
            timeout=300,
        )

        if returncode != 0:
            logger.warning("gitnexus_nonzero_exit", returncode=returncode, stderr=stderr[:500])
            result.error = f"GitNexus analyze failed (code {returncode}): {stderr[:200]}"
            return result

        logger.info("gitnexus_analyze_complete", repo=repo_path)
    except TimeoutError:
        result.error = "GitNexus analyze timed out after 300s"
        return result
    except (FileNotFoundError, OSError) as exc:
        raise GitNexusNotInstalledError(
            f"Failed to run GitNexus via npx: {exc}. "
            "Ensure Node.js is installed and npx is on your PATH."
        ) from exc

    # Step 1b: Run gitnexus setup (generates CLAUDE.md integration for the repo)
    try:
        setup_stdout, setup_stderr, setup_rc = await _run_npx(
            npx,
            ["setup"],
            cwd=str(repo),
            timeout=60,
        )
        if setup_rc != 0:
            logger.warning(
                "gitnexus_setup_nonzero", returncode=setup_rc, stderr=setup_stderr[:300]
            )
        else:
            logger.info("gitnexus_setup_complete", repo=repo_path)
    except TimeoutError:
        logger.warning("gitnexus_setup_timeout", repo=repo_path)
    except (FileNotFoundError, OSError):
        logger.warning("gitnexus_setup_failed", repo=repo_path)

    # Step 1c: Register gitnexus MCP server so Claude Code can use it
    from app.services.claude_runner import ensure_gitnexus_mcp

    await ensure_gitnexus_mcp()

    # Brief pause to let LadybugDB release the write lock before querying
    await asyncio.sleep(2)

    # Step 2: Read meta.json for stats
    meta_path = repo / ".gitnexus" / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            result.stats = meta.get("stats", {})
        except (json.JSONDecodeError, OSError):
            pass

    # Step 3: Query communities (feature clusters) from knowledge graph
    # Two-pass approach: Kuzu/LadybugDB doesn't allow ORDER BY on node properties
    # after aggregation, so we first get community list, then files per community.
    try:
        # 3a: Get top communities by symbol count
        comm_list_json, comm_list_stderr, rc = await _run_cypher(
            npx,
            "MATCH (c:Community) "
            "RETURN c.label AS community, c.symbolCount AS symbols "
            "ORDER BY symbols DESC LIMIT 50",
            cwd=str(repo),
            repo_name=repo_name,
        )

        logger.info(
            "gitnexus_cypher_community_list_raw",
            rc=rc,
            stdout_len=len(comm_list_json),
            stdout_preview=comm_list_json[:500] if comm_list_json else "(empty)",
            stderr=comm_list_stderr[:300] if comm_list_stderr else "(empty)",
        )

        if rc == 0 and comm_list_json.strip():
            comm_list_data = json.loads(comm_list_json)
            if "markdown" in comm_list_data:
                # Parse community names + symbols from the list query
                community_names = _parse_cypher_community_list(comm_list_data["markdown"])

                if community_names:
                    # 3b: Get files per community individually
                    # (gitnexus truncates cypher output at 64KB, so we
                    #  can't fetch all communities' files in one query)
                    community_files: dict[str, list[str]] = {}
                    unique_names = [name for name, _ in community_names]

                    for comm_name in unique_names:
                        # Escape single quotes in community name for cypher
                        safe_name = comm_name.replace("'", "\\'")
                        fj, _, frc = await _run_cypher(
                            npx,
                            f"MATCH (s)-[:CodeRelation]->(c:Community) "
                            f"WHERE c.label = '{safe_name}' "
                            f"RETURN DISTINCT s.filePath AS file "
                            f"LIMIT 30",
                            cwd=str(repo),
                            repo_name=repo_name,
                            timeout=15,
                        )
                        if frc == 0 and fj.strip():
                            try:
                                fd = json.loads(fj)
                                if "markdown" in fd:
                                    files = _parse_single_column(fd["markdown"])
                                    community_files[comm_name] = files
                            except json.JSONDecodeError:
                                pass

                    logger.info(
                        "gitnexus_community_files_loaded",
                        communities_with_files=len(community_files),
                    )

                    # Merge: community list + their files
                    result.features = _build_features(community_names, community_files)

            logger.info(
                "gitnexus_communities_loaded",
                count=len(result.features),
                repo=repo_path,
            )
        else:
            logger.warning(
                "gitnexus_cypher_communities_empty",
                rc=rc,
                repo=repo_path,
            )
    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("gitnexus_cypher_communities_failed", error=str(exc))

    # Step 4: Query execution flows (processes)
    try:
        processes_json, processes_stderr, rc = await _run_cypher(
            npx,
            "MATCH (p:Process) "
            "RETURN p.label AS process, p.stepCount AS steps "
            "ORDER BY p.stepCount DESC LIMIT 30",
            cwd=str(repo),
            repo_name=repo_name,
        )

        logger.info(
            "gitnexus_cypher_processes_raw",
            rc=rc,
            stdout_len=len(processes_json),
            stdout_preview=processes_json[:500] if processes_json else "(empty)",
            stderr=processes_stderr[:300] if processes_stderr else "(empty)",
        )

        if rc == 0 and processes_json.strip():
            processes_data = json.loads(processes_json)
            if "markdown" in processes_data:
                result.processes = _parse_cypher_processes(processes_data["markdown"])
            logger.info(
                "gitnexus_processes_loaded",
                count=len(result.processes),
                repo=repo_path,
            )
        else:
            logger.warning(
                "gitnexus_cypher_processes_empty",
                rc=rc,
                repo=repo_path,
            )
    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("gitnexus_cypher_processes_failed", error=str(exc))

    # Step 5: Build repo overview from README.md + stats
    readme = repo / "README.md"
    overview_parts: list[str] = []
    if result.stats:
        s = result.stats
        overview_parts.append(
            f"Codebase: {s.get('files', 0)} files, "
            f"{s.get('nodes', 0)} symbols, "
            f"{s.get('edges', 0)} relationships, "
            f"{s.get('communities', 0)} feature clusters, "
            f"{s.get('processes', 0)} execution flows."
        )
    if readme.exists():
        readme_content = readme.read_text(errors="replace")
        # Take first meaningful paragraph (skip headings)
        for para in readme_content.split("\n\n"):
            stripped = para.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 30:
                overview_parts.append(stripped[:1000])
                break
    result.repo_overview = "\n\n".join(overview_parts)

    result.success = True
    return result


## _parse_markdown_table, _parse_cypher_community_list, _parse_single_column
## are imported from gitnexus_utils


def _build_features(
    community_names: list[tuple[str, int]],
    community_files: dict[str, list[str]],
) -> list[FeatureEntry]:
    """Build FeatureEntry list from community names and file mappings.

    Args:
        community_names: List of (name, total_symbols) from the list query.
        community_files: Dict of community name → file paths from the files query.

    Returns:
        List of FeatureEntry objects.
    """
    features: list[FeatureEntry] = []
    for name, symbols in community_names:
        files = community_files.get(name, [])[:30]
        overview = f"{name} — {symbols} symbols across {len(files)} files."
        features.append(
            FeatureEntry(
                name=name,
                overview=overview,
                files=files,
                tags=[],
            )
        )
    return features


def _parse_cypher_processes(markdown: str) -> list[ProcessEntry]:
    """Parse the markdown table from a cypher process query.

    Expected columns: process, steps

    Args:
        markdown: Markdown table string from gitnexus cypher output.

    Returns:
        List of ProcessEntry objects.
    """
    processes: list[ProcessEntry] = []
    for row in _parse_markdown_table(markdown):
        if len(row) < 2:
            continue
        name = row[0]
        try:
            steps = int(row[1])
        except ValueError:
            steps = 0
        processes.append(ProcessEntry(name=name, step_count=steps))
    return processes


async def extract_repo_docs(repo_path: str) -> list[DocEntry]:
    """Find documentation files (README.md, docs/*.md) and return them.

    Excludes GitNexus-generated files (CLAUDE.md, AGENTS.md) since those
    contain agent instructions, not codebase documentation.

    Args:
        repo_path: Absolute path to the git repository root.

    Returns:
        List of DocEntry objects with title, content, and source reference.
    """
    docs: list[DocEntry] = []
    repo = Path(repo_path)

    # Top-level docs (skip CLAUDE.md and AGENTS.md — those are GitNexus agent instructions)
    for name in ["README.md", "CONTRIBUTING.md", "ARCHITECTURE.md"]:
        doc_path = repo / name
        if doc_path.exists():
            content = doc_path.read_text(errors="replace")
            if content.strip():
                docs.append(
                    DocEntry(
                        title=name.replace(".md", "").replace("-", " ").title(),
                        content=content[:10000],
                        source_ref=name,
                    )
                )

    # docs/ directory
    docs_dir = repo / "docs"
    if docs_dir.is_dir():
        for md_file in sorted(docs_dir.glob("**/*.md")):
            content = md_file.read_text(errors="replace")
            if content.strip():
                rel_path = str(md_file.relative_to(repo))
                title = md_file.stem.replace("-", " ").replace("_", " ").title()
                docs.append(
                    DocEntry(
                        title=title,
                        content=content[:10000],
                        source_ref=rel_path,
                    )
                )

    logger.info("extract_repo_docs", repo=repo_path, doc_count=len(docs))
    return docs


# ── Worktree management ────────────────────────────────────────────


async def run_git(args: list[str], cwd: str, timeout: int = 60) -> tuple[str, str, int]:
    """Run a git command asynchronously.

    Args:
        args: Git subcommand and arguments.
        cwd: Working directory for the command.
        timeout: Maximum seconds to wait.

    Returns:
        Tuple of (stdout, stderr, returncode).
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return (
        stdout.decode(errors="replace").strip(),
        stderr.decode(errors="replace").strip(),
        proc.returncode or 0,
    )


async def _detect_main_branch(repo_path: str) -> str | None:
    """Detect whether the repo uses 'main' or 'master' as its primary branch.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Branch name ('main' or 'master'), or None if neither found.
    """
    stdout, _, _ = await run_git(["branch", "-r"], cwd=repo_path)
    for candidate in ("origin/main", "origin/master"):
        if candidate in stdout:
            return candidate.split("/", 1)[1]
    return None


async def _detect_develop_branch(repo_path: str) -> str | None:
    """Detect whether the repo uses 'develop' or 'dev' as its development branch.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Branch name ('develop' or 'dev'), or None if neither found.
    """
    stdout, _, _ = await run_git(["branch", "-r"], cwd=repo_path)
    for candidate in ("origin/develop", "origin/dev"):
        if candidate in stdout:
            return candidate.split("/", 1)[1]
    return None


async def detect_uncommitted_changes(repo_path: str) -> bool:
    """Run git status --porcelain. Returns True if working tree is dirty.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        True if there are uncommitted changes.
    """
    stdout, _, _ = await run_git(["status", "--porcelain"], cwd=repo_path)
    return bool(stdout.strip())


async def list_remote_branches(repo_path: str) -> list[str]:
    """List all remote branch names (origin/main → 'main').

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Sorted list of unique branch names.
    """
    stdout, _, _ = await run_git(["branch", "-r"], cwd=repo_path)
    branches = []
    for line in stdout.splitlines():
        line = line.strip()
        if "->" in line or not line:
            continue
        if "/" in line:
            branches.append(line.split("/", 1)[1])
    return sorted(set(branches))


_FRONTEND_DEPS = frozenset(
    {
        "vue",
        "react",
        "react-dom",
        "next",
        "nuxt",
        "@angular/core",
        "svelte",
        "@sveltejs/kit",
        "vuetify",
        "@mui/material",
        "tailwindcss",
    }
)


def detect_repo_type(repo_path: str) -> str | None:
    """Detect if repo is 'frontend' or 'backend' by checking package.json deps.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        'frontend', 'backend', or None if detection fails.
    """
    pkg_path = Path(repo_path) / "package.json"
    if not pkg_path.exists():
        return "backend"
    try:
        pkg = json.loads(pkg_path.read_text())
        all_deps = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
        return "frontend" if all_deps & _FRONTEND_DEPS else "backend"
    except (json.JSONDecodeError, OSError):
        return None


async def ensure_repo_worktrees(repo_path: str) -> tuple[str | None, str | None]:
    """Create main + develop worktrees for a repo.

    Creates worktrees under ``<repo>/.bodhigrove/main/`` and
    ``<repo>/.bodhigrove/develop/``. Pulls both to latest.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Tuple of (main_worktree_path, develop_worktree_path).
        Either may be None if the branch doesn't exist.
    """
    repo = Path(repo_path)
    worktree_dir = repo / ".bodhigrove"
    worktree_dir.mkdir(exist_ok=True)

    main_branch = await _detect_main_branch(repo_path)
    develop_branch = await _detect_develop_branch(repo_path)

    results: list[str | None] = [None, None]

    for idx, (branch, dirname) in enumerate([(main_branch, "main"), (develop_branch, "develop")]):
        if branch is None:
            continue

        wt_path = worktree_dir / dirname
        if not wt_path.exists():
            _, stderr, rc = await run_git(["worktree", "add", str(wt_path), branch], cwd=repo_path)
            if rc != 0:
                logger.warning(
                    "worktree_add_failed",
                    branch=branch,
                    error=stderr[:200],
                )
                continue
        else:
            # Pull latest
            _, stderr, rc = await run_git(["pull"], cwd=str(wt_path))
            if rc != 0:
                logger.warning("worktree_pull_failed", branch=branch, error=stderr[:200])

        results[idx] = str(wt_path)

    logger.info(
        "worktrees_ensured",
        repo=repo_path,
        main=results[0] is not None,
        develop=results[1] is not None,
    )
    return results[0], results[1]


# ── Bodhigrove MCP server init ─────────────────────────────────────


async def init_bodhigrove_mcp_in_repo(repo_path: str, backend_url: str, mcp_token: str) -> bool:
    """Write .claude/settings.json with Bodhigrove MCP server config.

    Idempotent: skips if the bodhigrove entry already exists with the
    correct backend URL. Only updates when config is missing or stale.

    Args:
        repo_path: Absolute path to the git repository.
        backend_url: URL of the Bodhigrove backend (e.g. http://localhost:8000).
        mcp_token: Long-lived org-scoped MCP token.

    Returns:
        True if the file was written (changed), False if already up to date.
    """
    import contextlib

    repo = Path(repo_path)
    claude_dir = repo / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    bridge_script = str(Path(__file__).resolve().parents[1] / "mcp" / "stdio_bridge.py")

    settings: dict = {}
    if settings_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            settings = json.loads(settings_path.read_text())

    # Check if already configured with correct URL
    existing_mcp = settings.get("mcpServers", {}).get("bodhigrove", {})
    existing_env = existing_mcp.get("env", {})
    if (
        existing_env.get("BODHIGROVE_BACKEND_URL") == backend_url
        and existing_env.get("BODHIGROVE_MCP_TOKEN") == mcp_token
    ):
        logger.debug("bodhigrove_mcp_already_configured", repo=repo_path)
        return False

    settings.setdefault("mcpServers", {})
    settings["mcpServers"]["bodhigrove"] = {
        "command": "python3",
        "args": [bridge_script],
        "env": {
            "BODHIGROVE_BACKEND_URL": backend_url,
            "BODHIGROVE_MCP_TOKEN": mcp_token,
        },
    }

    settings_path.write_text(json.dumps(settings, indent=2))
    logger.info("bodhigrove_mcp_written", repo=repo_path)
    return True


# ── Git hook installation ──────────────────────────────────────────

_HOOK_MARKER = "# installed-by-bodhigrove"


def _build_pre_commit_hook(backend_url: str, org_id: str) -> str:
    """Build the pre-commit hook script content.

    The hook validates that BUD branches (bud-NNN/...) reference a BUD
    that exists in Bodhigrove. Non-BUD branches are allowed through.

    Args:
        backend_url: Public URL of the Bodhigrove backend.
        org_id: Organization UUID string (baked into hook for org scoping).

    Returns:
        Shell script string.
    """
    return (
        f"{_HOOK_MARKER} (pre-commit)\n"
        "BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)\n"
        "BUD_NUM=$(echo \"$BRANCH\" | sed -n 's/^bud-\\([0-9]*\\)\\/.*/\\1/p')\n"
        '[ -z "$BUD_NUM" ] && exit 0\n'
        "\n"
        'STATUS=$(curl -s -o /dev/null -w "%{http_code}" \\\n'
        f'  "{backend_url}/api/v1/public/{org_id}/bud-check/$BUD_NUM" 2>/dev/null)\n'
        'if [ "$STATUS" = "404" ]; then\n'
        '  echo "BUD-$BUD_NUM not found in Bodhigrove. Commit blocked."\n'
        "  exit 1\n"
        "fi\n"
    )


def _build_post_commit_hook(backend_url: str, org_id: str) -> str:
    """Build the post-commit hook script content.

    Reports each commit to Bodhigrove for tracking. Fire-and-forget
    (backgrounded, never blocks the commit). Uses printf for safe JSON
    construction to avoid shell injection from commit messages.

    Args:
        backend_url: Public URL of the Bodhigrove backend.
        org_id: Organization UUID string (baked into hook for org scoping).

    Returns:
        Shell script string.
    """
    # Uses a heredoc-style JSON body via printf to avoid shell injection.
    # The commit message is truncated and special chars are escaped via sed.
    return (
        f"{_HOOK_MARKER} (post-commit)\n"
        "BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)\n"
        "BUD_NUM=$(echo \"$BRANCH\" | sed -n 's/^bud-\\([0-9]*\\)\\/.*/\\1/p')\n"
        '[ -z "$BUD_NUM" ] && exit 0\n'
        "\n"
        "SHA=$(git rev-parse HEAD)\n"
        "# Escape special JSON chars in commit message to prevent injection\n"
        "MSG=$(git log -1 --format=%s | head -c 400 | "
        "sed 's/\\\\\\\\/\\\\\\\\\\\\\\\\/g; s/\"/\\\\\\\\\"/g')\n"
        "FILES=$(git diff-tree --no-commit-id --name-only -r HEAD | tr '\\n' ',')\n"
        "REPO_PATH=$(git rev-parse --show-toplevel)\n"
        "\n"
        "# Build JSON safely with printf\n"
        'JSON=$(printf \'{"bud_number":%s,"sha":"%s","message":"%s",'
        '"files":"%s","repo_path":"%s","branch":"%s"}\''
        ' "$BUD_NUM" "$SHA" "$MSG" "$FILES" "$REPO_PATH" "$BRANCH")\n'
        "\n"
        f'curl -s -X POST "{backend_url}/api/v1/public/{org_id}/bud-commit" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d "$JSON" \\\n'
        "  >/dev/null 2>&1 &\n"
    )


async def install_hooks(repo_path: str, backend_url: str, org_id: str) -> bool:
    """Install pre-commit and post-commit hooks in a repository.

    Writes hooks to ``.githooks/`` (committed to git) instead of
    ``.git/hooks/`` (local-only). Then sets ``core.hooksPath`` so git
    uses the committed directory. This way all devs pulling the repo
    get the hook scripts; they just need ``core.hooksPath`` configured
    once (done automatically by the Bodhigrove MCP server on init).

    Idempotent: checks for the marker string before writing.

    Args:
        repo_path: Absolute path to the git repository.
        backend_url: Public URL of the Bodhigrove backend.
        org_id: Organization UUID string (baked into hook URLs for scoping).

    Returns:
        True if hook files were written (changed), False if already up to date.
    """
    repo = Path(repo_path)
    hooks_dir = repo / ".githooks"
    hooks_dir.mkdir(exist_ok=True)

    changed = False
    for hook_name, builder in [
        ("pre-commit", _build_pre_commit_hook),
        ("post-commit", _build_post_commit_hook),
    ]:
        hook_path = hooks_dir / hook_name
        hook_content = builder(backend_url, org_id)

        if hook_path.exists():
            existing = hook_path.read_text()
            if _HOOK_MARKER in existing:
                continue  # Already installed
            # Append to existing hook
            with hook_path.open("a") as f:
                f.write(f"\n{hook_content}")
        else:
            hook_path.write_text(f"#!/bin/sh\n{hook_content}")

        hook_path.chmod(0o755)
        changed = True

    # Point git at the committed hooks directory (local config, per-clone)
    await run_git(["config", "core.hooksPath", ".githooks"], cwd=repo_path)

    logger.info("hooks_installed", repo=repo_path, changed=changed)
    return changed


# ── .gitignore management ──────────────────────────────────────────


def add_bodhigrove_gitignore(repo_path: str) -> bool:
    """Append .bodhigrove/ to .gitignore if not already present.

    Idempotent.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        True if the file was changed, False if already up to date.
    """
    gitignore = Path(repo_path) / ".gitignore"
    entry = ".bodhigrove/"

    if gitignore.exists():
        content = gitignore.read_text()
        if entry in content:
            return False
        if not content.endswith("\n"):
            content += "\n"
        content += f"{entry}\n"
        gitignore.write_text(content)
    else:
        gitignore.write_text(f"{entry}\n")

    logger.info("gitignore_updated", repo=repo_path)
    return True


# ── package.json prepare script ───────────────────────────────────

_PREPARE_CMD = "git config core.hooksPath .githooks"


def add_prepare_script(repo_path: str) -> bool:
    """Add a ``prepare`` script to package.json that sets core.hooksPath.

    This runs automatically on every ``npm install`` / ``yarn install``,
    ensuring all developers get Bodhigrove's git hooks without manual
    setup — the same pattern used by Husky.

    If the repo has no package.json, creates a minimal one.
    Idempotent: skips if prepare script already contains the command.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        True if package.json was changed, False if already up to date.
    """
    import contextlib

    pkg_path = Path(repo_path) / "package.json"

    pkg: dict = {}
    if pkg_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            pkg = json.loads(pkg_path.read_text())

    scripts = pkg.get("scripts", {})
    existing_prepare = scripts.get("prepare", "")

    # Already has our command
    if _PREPARE_CMD in existing_prepare:
        return False

    # Append to existing prepare script, or create new one
    if existing_prepare:
        scripts["prepare"] = f"{existing_prepare} && {_PREPARE_CMD}"
    else:
        scripts["prepare"] = _PREPARE_CMD

    pkg["scripts"] = scripts

    # For repos without package.json, create a minimal one
    if not pkg_path.exists():
        pkg.setdefault("private", True)

    pkg_path.write_text(json.dumps(pkg, indent=2) + "\n")
    logger.info("prepare_script_added", repo=repo_path)
    return True


# ── Commit Bodhigrove setup files ─────────────────────────────────


_SETUP_BRANCH = "bodhigrove/init-setup"

_SETUP_FILES = [
    ".claude/settings.json",
    ".gitignore",
    ".githooks/pre-commit",
    ".githooks/post-commit",
    "package.json",
]


async def commit_and_push_bodhigrove_setup(repo_path: str, base_branch: str) -> str | None:
    """Create a branch, commit Bodhigrove setup files, and push to origin.

    Creates ``bodhigrove/init-setup`` from the base branch, stages only
    the files Bodhigrove modifies, commits, and pushes. The team can
    then review via PR in their hosting platform.

    Idempotent: if the branch already exists on the remote, skips.

    Args:
        repo_path: Absolute path to the git repository.
        base_branch: Branch to create from (e.g. "main" or "master").

    Returns:
        The pushed branch name, or None if nothing to commit or push failed.
    """
    # Check if setup branch already exists on remote (already pushed before)
    stdout, _, _ = await run_git(["ls-remote", "--heads", "origin", _SETUP_BRANCH], cwd=repo_path)
    if _SETUP_BRANCH in stdout:
        logger.debug("bodhigrove_setup_branch_exists", repo=repo_path)
        return None

    # Remember current branch to switch back
    orig_branch, _, _ = await run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    orig_branch = orig_branch.strip()

    # Create setup branch from base
    _, stderr, rc = await run_git(["checkout", "-b", _SETUP_BRANCH, base_branch], cwd=repo_path)
    if rc != 0:
        logger.warning("bodhigrove_setup_branch_failed", error=stderr[:200])
        return None

    try:
        # Stage only files that have changes
        staged_any = False
        for filepath in _SETUP_FILES:
            full = Path(repo_path) / filepath
            if not full.exists():
                continue
            # Check untracked
            _, _, ls_rc = await run_git(["ls-files", "--error-unmatch", filepath], cwd=repo_path)
            is_untracked = ls_rc != 0
            # Check modified
            _, _, diff_rc = await run_git(["diff", "--quiet", "--", filepath], cwd=repo_path)
            is_modified = diff_rc != 0

            if is_modified or is_untracked:
                await run_git(["add", filepath], cwd=repo_path)
                staged_any = True

        if not staged_any:
            logger.debug("bodhigrove_setup_nothing_to_commit", repo=repo_path)
            return None

        # Commit
        _, stderr, rc = await run_git(
            [
                "commit",
                "-m",
                "chore(bodhigrove): add MCP tools, git hooks, and gitignore\n\n"
                "Auto-committed by Bodhigrove scan pipeline.\n"
                "- .claude/settings.json: Bodhigrove MCP server config\n"
                "- .githooks/: pre-commit (BUD validation) + post-commit (tracking)\n"
                "- package.json: prepare script sets core.hooksPath on npm install\n"
                "- .gitignore: exclude .bodhigrove/ worktrees",
            ],
            cwd=repo_path,
        )
        if rc != 0:
            logger.warning("bodhigrove_setup_commit_failed", error=stderr[:200])
            return None

        # Push to origin
        _, stderr, rc = await run_git(["push", "-u", "origin", _SETUP_BRANCH], cwd=repo_path)
        if rc != 0:
            logger.warning("bodhigrove_setup_push_failed", error=stderr[:200])
            return None

        logger.info(
            "bodhigrove_setup_pushed",
            repo=repo_path,
            branch=_SETUP_BRANCH,
        )
        return _SETUP_BRANCH
    finally:
        # Always switch to main branch (not the original feature branch)
        await run_git(["checkout", base_branch], cwd=repo_path)
