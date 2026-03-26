"""Repository setup: MCP init, hooks, gitignore, package.json, commit/push, PR creation.

Handles all the file-level setup that Bodhigrove performs on a tracked
repository: writing ``.claude/settings.json``, installing git hooks,
updating ``.gitignore``, adding a ``prepare`` script to ``package.json``,
and committing + pushing the result as a PR-ready branch.
"""

import json
import shutil
from pathlib import Path

import structlog

from app.services.git_operations import (
    _detect_develop_branch,
    _detect_main_branch,
    _run_shell_cmd,
    run_git,
)

logger = structlog.get_logger(__name__)


# ── Constants ──────────────────────────────────────────────────────

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

_HOOK_MARKER = "# installed-by-bodhigrove"

_PREPARE_CMD = "git config core.hooksPath .githooks"

_SETUP_BRANCH = "bodhigrove/init-setup"
_BG_START = "<!-- bodhigrove:start -->"
_BG_END = "<!-- bodhigrove:end -->"

_BODHIGROVE_CLAUDE_SECTION = """\
<!-- bodhigrove:start -->
---

## Bodhigrove — Development Workflow

This repo is tracked by Bodhigrove. MCP tools are auto-configured in `.claude/settings.json`.

### Always Do

- **Report progress** via `update_task_status` MCP tool when working on BUD tasks.
  Use the BUD number as `task_id` (e.g. `"1"` for BUD-001).
- **Branch naming:** Use `bud-NNN/<description>` branches (e.g. `bud-001/notification-redesign`).
  Pre-commit hooks validate BUD existence.
- **After each TODO step**, report what you did:
  ```
  update_task_status(task_id="1", status="in_progress", message="Implemented auth middleware")
  ```
- **On completion**, include effectiveness self-assessment:
  ```
  update_task_status(task_id="1", status="completed", message="Done",
    effectiveness={confidence: 8, complexity: "medium", test_coverage: "partial"})
  ```

### Available MCP Tools

| Tool | When to use |
|------|-------------|
| `update_task_status` | Report progress on BUD work (in_progress/completed/failed/blocked) |
| `get_bud_context` | Fetch BUD requirements, tech spec, and designs |
| `get_knowledge` | Search the organization's knowledge base |
| `get_design_system` | Fetch design tokens (colors, typography, components) |

### Commit Tracking

- Commits on `bud-NNN/` branches are automatically tracked by Bodhigrove
- Post-commit hooks report author, files, and message to the team dashboard
<!-- bodhigrove:end -->
"""

_SETUP_FILES = [
    ".claude/settings.json",
    ".gitignore",
    ".githooks/pre-commit",
    ".githooks/post-commit",
    "package.json",
    "CLAUDE.md",
    ".claude/skills/",
]


def append_bodhigrove_claude_instructions(repo_path: str) -> bool:
    """Append Bodhigrove workflow instructions to CLAUDE.md.

    Inserts after ``<!-- gitnexus:end -->`` if present, otherwise appends
    at end of file. Uses ``<!-- bodhigrove:start/end -->`` markers for
    idempotent updates.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        True if CLAUDE.md was modified, False if unchanged.
    """
    claude_md = Path(repo_path) / "CLAUDE.md"
    if not claude_md.exists():
        return False

    content = claude_md.read_text()

    # Already has Bodhigrove section — check if content changed
    if _BG_START in content:
        start = content.index(_BG_START)
        end = content.index(_BG_END) + len(_BG_END) if _BG_END in content else len(content)
        existing = content[start:end]
        new_section = _BODHIGROVE_CLAUDE_SECTION.strip()
        if existing.strip() == new_section:
            return False  # Already up to date
        # Replace existing section
        content = content[:start] + new_section + "\n" + content[end:]
    else:
        # Insert after gitnexus:end or append at end
        gitnexus_end = "<!-- gitnexus:end -->"
        if gitnexus_end in content:
            idx = content.index(gitnexus_end) + len(gitnexus_end)
            section = _BODHIGROVE_CLAUDE_SECTION.strip()
            content = content[:idx] + "\n\n" + section + "\n" + content[idx:]
        else:
            content = content.rstrip() + "\n\n" + _BODHIGROVE_CLAUDE_SECTION.strip() + "\n"

    claude_md.write_text(content)
    return True


# ── Repo type detection ───────────────────────────────────────────


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


# ── Worktree management ───────────────────────────────────────────


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
        "FILES=$(git diff-tree --no-commit-id --name-only -r HEAD | tr '\\n' ',' | "
        "sed 's/\\\\\\\\/\\\\\\\\\\\\\\\\/g; s/\"/\\\\\\\\\"/g')\n"
        "REPO_PATH=$(git rev-parse --show-toplevel | "
        "sed 's/\\\\\\\\/\\\\\\\\\\\\\\\\/g; s/\"/\\\\\\\\\"/g')\n"
        "AUTHOR=$(git log -1 --format='%an' | head -c 200 | "
        "sed 's/\\\\\\\\/\\\\\\\\\\\\\\\\/g; s/\"/\\\\\\\\\"/g')\n"
        "EMAIL=$(git log -1 --format='%ae' | head -c 200 | "
        "sed 's/\\\\\\\\/\\\\\\\\\\\\\\\\/g; s/\"/\\\\\\\\\"/g')\n"
        "BRANCH_ESC=$(echo \"$BRANCH\" | "
        "sed 's/\\\\\\\\/\\\\\\\\\\\\\\\\/g; s/\"/\\\\\\\\\"/g')\n"
        "\n"
        "# Build JSON safely with printf\n"
        'JSON=$(printf \'{"bud_number":%s,"sha":"%s","message":"%s",'
        '"files":"%s","repo_path":"%s","branch":"%s",'
        '"author":"%s","author_email":"%s"}\''
        ' "$BUD_NUM" "$SHA" "$MSG" "$FILES" "$REPO_PATH" "$BRANCH_ESC"'
        ' "$AUTHOR" "$EMAIL")\n'
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

        full_content = f"#!/bin/sh\n{hook_content}"
        if hook_path.exists():
            existing = hook_path.read_text()
            if _HOOK_MARKER in existing:
                if existing.strip() == full_content.strip():
                    continue  # Already up to date
                # Overwrite with updated hook content
                hook_path.write_text(full_content)
            else:
                # Append to existing non-Bodhigrove hook
                with hook_path.open("a") as f:
                    f.write(f"\n{hook_content}")
        else:
            hook_path.write_text(full_content)

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
    # Check if setup branch already exists on remote
    stdout, _, _ = await run_git(["ls-remote", "--heads", "origin", _SETUP_BRANCH], cwd=repo_path)
    branch_exists_remote = _SETUP_BRANCH in stdout

    # Remember current branch to switch back
    orig_branch, _, _ = await run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    orig_branch = orig_branch.strip()

    if branch_exists_remote:
        # Fetch and check out existing branch to add any new files (e.g. GitNexus config)
        await run_git(["fetch", "origin", _SETUP_BRANCH], cwd=repo_path)
        _, stderr, rc = await run_git(["checkout", _SETUP_BRANCH], cwd=repo_path)
        if rc != 0:
            # Local branch may not exist yet — create from remote
            _, stderr, rc = await run_git(
                ["checkout", "-b", _SETUP_BRANCH, f"origin/{_SETUP_BRANCH}"], cwd=repo_path
            )
        if rc != 0:
            logger.warning("bodhigrove_setup_checkout_failed", error=stderr[:200])
            return None
    else:
        # Try checking out existing local branch first
        _, stderr, rc = await run_git(["checkout", _SETUP_BRANCH], cwd=repo_path)
        if rc != 0:
            # Branch doesn't exist locally — create from base
            _, stderr, rc = await run_git(
                ["checkout", "-b", _SETUP_BRANCH, base_branch], cwd=repo_path
            )
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
                "chore(bodhigrove): add MCP tools, git hooks, and config\n\n"
                "Auto-committed by Bodhigrove scan pipeline.\n"
                "- .claude/settings.json: Bodhigrove MCP server config\n"
                "- .githooks/: pre-commit (BUD validation) + post-commit (tracking)\n"
                "- package.json: prepare script sets core.hooksPath on npm install\n"
                "- .gitignore: exclude .bodhigrove/ worktrees\n"
                "- CLAUDE.md: GitNexus code intelligence integration\n"
                "- .claude/skills/: GitNexus agent skill definitions",
            ],
            cwd=repo_path,
        )
        if rc != 0:
            logger.warning("bodhigrove_setup_commit_failed", error=stderr[:200])
            return None

        # Push to origin (force-with-lease when updating existing branch)
        push_cmd = ["push", "-u", "origin", _SETUP_BRANCH]
        if branch_exists_remote:
            push_cmd = ["push", "--force-with-lease", "-u", "origin", _SETUP_BRANCH]
        _, stderr, rc = await run_git(push_cmd, cwd=repo_path)
        if rc != 0:
            # No remote or push failed — merge setup into base branch directly
            logger.info("bodhigrove_setup_no_remote_merging", repo=repo_path)
            await run_git(["checkout", base_branch], cwd=repo_path)
            _, merge_err, merge_rc = await run_git(
                ["merge", _SETUP_BRANCH, "--no-edit"], cwd=repo_path,
            )
            if merge_rc == 0:
                await run_git(["branch", "-d", _SETUP_BRANCH], cwd=repo_path)
                logger.info("bodhigrove_setup_merged_locally", repo=repo_path)
                return _SETUP_BRANCH
            logger.warning(
                "bodhigrove_setup_merge_failed", repo=repo_path, error=merge_err[:200],
            )
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


async def create_setup_pr(repo_path: str, base_branch: str, pushed_branch: str) -> str | None:
    """Create a pull request for the Bodhigrove setup branch via ``gh`` CLI.

    Falls back gracefully when ``gh`` is not installed or not authenticated.

    Args:
        repo_path: Absolute path to the git repository.
        base_branch: Target branch for the PR (e.g. "main").
        pushed_branch: Source branch that was pushed (e.g. "bodhigrove/init-setup").

    Returns:
        PR URL if created or already exists, None if ``gh`` is unavailable.
    """
    if not shutil.which("gh"):
        logger.info("gh_cli_not_found", repo=repo_path)
        return None

    # Check if PR already exists for this branch
    try:
        stdout, _, rc = await _run_shell_cmd(
            ["gh", "pr", "view", pushed_branch, "--json", "url", "-q", ".url"],
            cwd=repo_path,
        )
        if rc == 0 and stdout.strip():
            logger.info(
                "setup_pr_already_exists",
                repo=repo_path,
                url=stdout.strip(),
            )
            return stdout.strip()
    except (TimeoutError, OSError):
        pass

    # Create the PR
    try:
        stdout, stderr, rc = await _run_shell_cmd(
            [
                "gh",
                "pr",
                "create",
                "--base",
                base_branch,
                "--head",
                pushed_branch,
                "--title",
                "chore: add Bodhigrove MCP tools, git hooks, and config",
                "--body",
                "## Summary\n\n"
                "Auto-generated by Bodhigrove scan pipeline.\n\n"
                "- `.claude/settings.json` — Bodhigrove MCP server config\n"
                "- `.githooks/` — pre-commit (BUD validation) + "
                "post-commit (tracking)\n"
                "- `package.json` — prepare script sets `core.hooksPath`\n"
                "- `.gitignore` — exclude `.bodhigrove/` worktrees\n"
                "- `CLAUDE.md` — GitNexus code intelligence integration\n"
                "- `.claude/skills/` — GitNexus agent skill definitions\n",
            ],
            cwd=repo_path,
            timeout=30,
        )
        if rc == 0 and stdout.strip():
            logger.info("setup_pr_created", repo=repo_path, url=stdout.strip())
            return stdout.strip()
        logger.warning(
            "setup_pr_create_failed",
            repo=repo_path,
            rc=rc,
            stderr=stderr[:300],
        )
    except (TimeoutError, OSError) as exc:
        logger.warning("setup_pr_create_error", repo=repo_path, error=str(exc))

    return None
