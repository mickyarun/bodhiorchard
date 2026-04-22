# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Repository setup: MCP init, hooks, gitignore, package.json, commit/push, PR creation.

Handles all the file-level setup that Bodhiorchard performs on a tracked
repository: writing ``.claude/settings.json``, installing git hooks,
updating ``.gitignore``, adding a ``prepare`` script to ``package.json``,
and committing + pushing the result as a PR-ready branch.
"""

import json
import shutil
import textwrap
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

_HOOK_MARKER = "# installed-by-bodhiorchard"

_PREPARE_CMD = "git config core.hooksPath .githooks"

_SETUP_BRANCH = "bodhiorchard/init-setup"
_BG_START = "<!-- bodhiorchard:start -->"
_BG_END = "<!-- bodhiorchard:end -->"

_BODHIORCHARD_CLAUDE_SECTION = """\
<!-- bodhiorchard:start -->
---

## Bodhiorchard — Development Workflow

This repo is tracked by Bodhiorchard. MCP tools are configured in `.mcp.json`.

### MCP Setup

Before starting any BUD work, verify Bodhiorchard MCP is connected:
1. Check that `get_bud_context` tool is available
2. If NOT available, set up your token:
   - Go to Bodhiorchard Settings → Integrations → MCP Token
   - Copy your token
   - Run: `export BODHIORCHARD_MCP_TOKEN="your-token"` in your shell profile
   - Restart Claude Code

### Always Do

- **Branch naming:** Use `bud-NNN/<description>` branches (e.g. `bud-001/notification-redesign`).
  Pre-commit hooks validate BUD existence.

### Available MCP Tools

| Tool | When to use |
|------|-------------|
| `get_bud_plan` | Fetch your assigned TODOs on a `bud-NNN/` branch (call on session start) |
| `takeover_todo` | Claim a TODO before implementing it (REQUIRED) |
| `complete_todo` | Mark a TODO completed with a summary of what you implemented |
| `get_bud_context` | Fetch BUD requirements, tech spec, and designs |
| `get_knowledge` | Search the organization's knowledge base |
| `get_design_system` | Fetch design tokens (colors, typography, components) |

### TODO Workflow (STRICT — follow exactly)

When you start a session on a `bud-NNN/` branch:

1. Call `get_bud_plan(bud_number=NNN)` to see the plan and your assigned TODOs.
   - TODOs marked `"yours": true` are for you.
   - TODOs marked `"skip": true` are assigned to other developers — do NOT implement them.
2. For each of your TODOs, in order:
   a. Call `takeover_todo(bud_number=NNN, sequence=X)`.
      - On **success**: you now have the `context_md` — proceed to implement.
      - On **failure**: skip this TODO and move to the next one (someone else has it).
   b. Implement the TODO using the returned `context_md` and the tech spec.
   c. Call `complete_todo(bud_number=NNN, sequence=X, summary="…")` when done.
      The summary should be a short description of what you built (1-2 sentences).
3. NEVER implement a TODO without a successful `takeover_todo` call first.
4. NEVER implement a TODO marked `"skip": true` — another developer is working on it.
5. If `get_bud_plan` shows no TODOs assigned to you, stop and ask the user / team lead.

### Cross-developer Awareness

`get_bud_plan` also returns `other_branches` — branches by other developers
on the same BUD, with the files they've touched. If you're editing shared
code, consider `git fetch` + `git diff origin/<their-branch> -- <file>` to
stay consistent with their work.

### Commit Tracking

- Commits on `bud-NNN/` branches are automatically tracked by Bodhiorchard
- Post-commit hooks report author, files, and message to the team dashboard

### Claude Code Hooks (Automatic)

Claude Code hooks in `.claude/hooks/` run automatically — no developer action needed:
- **SessionStart**: Auto-detects your identity and active BUD from branch name
- **PostToolUse**: Automatically tracks commits and file changes
- **Stop**: Reports activity summaries after each Claude response
- **UserPromptSubmit**: Detects BUD references in your prompts

These hooks use your `BODHIORCHARD_MCP_TOKEN` for authentication.
If the token is not set, hooks silently do nothing.
<!-- bodhiorchard:end -->
"""

assert _BODHIORCHARD_CLAUDE_SECTION.lstrip().startswith(_BG_START), "Marker mismatch"
assert _BODHIORCHARD_CLAUDE_SECTION.rstrip().endswith(_BG_END), "Marker mismatch"

_CLAUDE_HOOK_MARKER = "# bodhiorchard-claude-hook"

_SETUP_FILES = [
    ".claude/settings.json",
    ".mcp.json",
    ".gitignore",
    ".githooks/pre-commit",
    ".githooks/post-commit",
    ".claude/hooks/_common.sh",
    ".claude/hooks/session-start.sh",
    ".claude/hooks/session-end.sh",
    ".claude/hooks/post-commit-track.sh",
    ".claude/hooks/file-change-track.sh",
    ".claude/hooks/tool-error-track.sh",
    ".claude/hooks/api-error-track.sh",
    ".claude/hooks/activity-report.sh",
    ".claude/hooks/detect-bud-prompt.sh",
    ".claude/hooks/subagent-start.sh",
    ".claude/hooks/subagent-stop.sh",
    "package.json",
    "CLAUDE.md",
    ".claude/skills/",
]


def append_bodhiorchard_claude_instructions(repo_path: str) -> bool:
    """Append Bodhiorchard workflow instructions to CLAUDE.md.

    Inserts after ``<!-- gitnexus:end -->`` if present, otherwise appends
    at end of file. Uses ``<!-- bodhiorchard:start/end -->`` markers for
    idempotent updates.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        True if CLAUDE.md was modified, False if unchanged.
    """
    claude_md = Path(repo_path) / "CLAUDE.md"
    if not claude_md.exists():
        # Create CLAUDE.md with just the Bodhiorchard section
        claude_md.write_text(_BODHIORCHARD_CLAUDE_SECTION.strip() + "\n")
        return True

    content = claude_md.read_text()

    # Already has Bodhiorchard section — check if content changed
    if _BG_START in content:
        start = content.index(_BG_START)
        if _BG_END not in content:
            logger.warning(
                "bodhiorchard_claude_md_malformed",
                repo=repo_path,
                detail="start marker without end marker — skipping",
            )
            return False
        end = content.index(_BG_END) + len(_BG_END)
        existing = content[start:end]
        new_section = _BODHIORCHARD_CLAUDE_SECTION.strip()
        if existing.strip() == new_section:
            return False  # Already up to date
        # Replace existing section, avoid accumulating blank lines
        content = content[:start] + new_section + "\n" + content[end:].lstrip("\n")
    else:
        # Insert after gitnexus:end or append at end
        gitnexus_end = "<!-- gitnexus:end -->"
        if gitnexus_end in content:
            idx = content.index(gitnexus_end) + len(gitnexus_end)
            section = _BODHIORCHARD_CLAUDE_SECTION.strip()
            content = content[:idx] + "\n\n" + section + "\n" + content[idx:]
        else:
            content = content.rstrip() + "\n\n" + _BODHIORCHARD_CLAUDE_SECTION.strip() + "\n"

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

    Creates worktrees under ``<repo>/.bodhiorchard/main/`` and
    ``<repo>/.bodhiorchard/develop/``. Pulls both to latest.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Tuple of (main_worktree_path, develop_worktree_path).
        Either may be None if the branch doesn't exist.
    """
    repo = Path(repo_path)
    worktree_dir = repo / ".bodhiorchard"
    worktree_dir.mkdir(exist_ok=True)

    main_branch = await _detect_main_branch(repo_path)
    develop_branch = await _detect_develop_branch(repo_path)

    # Detect current branch to avoid worktree conflict
    current_branch, _, _ = await run_git(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path,
    )
    current_branch = current_branch.strip()

    results: list[str | None] = [None, None]

    for idx, (branch, dirname) in enumerate([(main_branch, "main"), (develop_branch, "develop")]):
        if branch is None:
            continue

        # If this branch is already checked out, use repo path directly
        if branch == current_branch:
            results[idx] = repo_path
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


# ── Bodhiorchard MCP server init ─────────────────────────────────────


async def init_bodhiorchard_mcp_in_repo(repo_path: str, backend_url: str) -> bool:
    """Write .mcp.json and .claude/settings.json with Bodhiorchard MCP config.

    Copies the MCP bridge script into the repo at .bodhiorchard/mcp_bridge.py
    and writes config with a relative path. Token is NOT included — developers
    set BODHIORCHARD_MCP_TOKEN env var themselves.

    Args:
        repo_path: Absolute path to the git repository.
        backend_url: URL of the Bodhiorchard backend.

    Returns:
        True if the file was written (changed), False if already up to date.
    """
    import contextlib

    repo = Path(repo_path)
    source_bridge = Path(__file__).resolve().parents[1] / "mcp" / "stdio_bridge.py"
    dest_dir = repo / ".bodhiorchard"
    dest_bridge = dest_dir / "mcp_bridge.py"

    # Build config (token NOT included — developer sets env var)
    mcp_json_path = repo / ".mcp.json"
    mcp_config = {
        "mcpServers": {
            "bodhiorchard": {
                "command": "python3",
                "args": [".bodhiorchard/mcp_bridge.py"],
                "env": {
                    "BODHIORCHARD_BACKEND_URL": backend_url,
                },
            },
        },
    }

    # Check if config matches exactly (catches stale tokens, format changes)
    expected_json = json.dumps(mcp_config, indent=2)
    if mcp_json_path.exists() and dest_bridge.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            if mcp_json_path.read_text().strip() == expected_json.strip():
                logger.debug("bodhiorchard_mcp_already_configured", repo=repo_path)
                return False

    # Copy bridge script (after early-return check)
    dest_dir.mkdir(exist_ok=True)
    shutil.copy2(source_bridge, dest_bridge)

    mcp_json_path.write_text(json.dumps(mcp_config, indent=2))

    # Also keep .claude/settings.json for backward compatibility
    claude_dir = repo / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    settings: dict = {}
    if settings_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            settings = json.loads(settings_path.read_text())

    settings.setdefault("mcpServers", {})
    # Overwrite with token-free config (replaces any stale token from old setups)
    settings["mcpServers"]["bodhiorchard"] = mcp_config["mcpServers"]["bodhiorchard"]
    settings_path.write_text(json.dumps(settings, indent=2))

    logger.info("bodhiorchard_mcp_written", repo=repo_path)
    return True


# ── Git hook installation ──────────────────────────────────────────


def _build_pre_commit_hook(backend_url: str, org_id: str) -> str:
    """Build the pre-commit hook script content.

    The hook validates that BUD branches (bud-NNN/...) reference a BUD
    that exists in Bodhiorchard. Non-BUD branches are allowed through.

    Args:
        backend_url: Public URL of the Bodhiorchard backend.
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
        '  echo "BUD-$BUD_NUM not found in Bodhiorchard. Commit blocked."\n'
        "  exit 1\n"
        "fi\n"
    )


def _build_post_commit_hook(backend_url: str, org_id: str) -> str:
    """Build the post-commit hook script content.

    Reports each commit to Bodhiorchard via /mcp/dev-activity (authenticated).
    Sources _common.sh from .claude/hooks/ for shared utilities.
    Fire-and-forget (backgrounded, never blocks the commit).

    Args:
        backend_url: Public URL of the Bodhiorchard backend.
        org_id: Organization UUID string (unused, kept for API compat).

    Returns:
        Shell script string.
    """
    return textwrap.dedent("""\
        {marker} (post-commit)
        # Source shared utilities from Claude hooks dir
        HOOKS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.claude/hooks"
        if [ -f "$HOOKS_DIR/_common.sh" ]; then
          . "$HOOKS_DIR/_common.sh"
        else
          exit 0
        fi

        BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
        BUD_NUM=$(get_bud_from_branch)
        SHA=$(git rev-parse HEAD)
        EMAIL=$(get_git_email)
        MSG=$(git log -1 --format=%s | head -c 400)
        FILES=$(git diff-tree --no-commit-id --name-only -r HEAD | tr '\\n' ',')
        REPO=$(git rev-parse --show-toplevel 2>/dev/null)

        # Find active Claude session ID from session temp file
        ACTIVE_SID=""
        for SF in /tmp/.bodhiorchard-session-*.json; do
          [ -f "$SF" ] || continue
          ACTIVE_SID=$(python3 -c "
import json
try:
    d=json.load(open('$SF')); print(d.get('session_id',''))
except: pass
" 2>/dev/null)
          [ -n "$ACTIVE_SID" ] && break
        done
        SESSION_ID="${{ACTIVE_SID:-git-hook}}"

        J=$(build_json session_id "$SESSION_ID" event_type commit \\
          author_email "$EMAIL" branch "$BRANCH" repo_path "$REPO" \\
          message "$MSG" commit_sha "$SHA" files_changed "$FILES")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
    """).format(marker=_HOOK_MARKER)


async def install_hooks(repo_path: str, backend_url: str, org_id: str) -> bool:
    """Install pre-commit and post-commit hooks in a repository.

    Writes hooks to ``.githooks/`` (committed to git) instead of
    ``.git/hooks/`` (local-only). Then sets ``core.hooksPath`` so git
    uses the committed directory. This way all devs pulling the repo
    get the hook scripts; they just need ``core.hooksPath`` configured
    once (done automatically by the Bodhiorchard MCP server on init).

    Idempotent: checks for the marker string before writing.

    Args:
        repo_path: Absolute path to the git repository.
        backend_url: Public URL of the Bodhiorchard backend.
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
                # Append to existing non-Bodhiorchard hook
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


# ── Claude Code hook installation ─────────────────────────────────

# Hook scripts are stored as plain text with {backend_url} as the only
# substitution. This avoids the f-string + shell escaping nightmare that
# caused 422 errors from malformed JSON.


def _build_common_sh(backend_url: str) -> str:
    """Build the shared utility script sourced by all hooks."""
    return textwrap.dedent("""\
        {marker}
        # Shared utilities for Bodhiorchard hooks.
        # Sourced by individual hook scripts — not executed directly.

        BACKEND_URL="{url}"
        TOKEN="${{BODHIORCHARD_MCP_TOKEN:-}}"

        escape_json() {{
          printf '%s' "$1" | sed 's/\\\\/\\\\\\\\/g; s/"/\\\\"/g' | tr '\\n\\r\\t' '   '
        }}

        sanitize_path() {{
          printf '%s' "$1" | tr -cd 'a-zA-Z0-9_-'
        }}

        get_sid() {{
          printf '%s' "$1" | grep -o '"session_id":"[^"]*"' | head -1 | cut -d'"' -f4
        }}

        get_bud_from_branch() {{
          RAW=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | \\
            sed -n 's/^bud-\\([0-9][0-9]*\\)\\/.*/\\1/p')
          # Strip leading zeros for valid JSON numbers (POSIX)
          [ -n "$RAW" ] && printf '%d' "$RAW" || echo ""
        }}

        get_git_email() {{
          git config user.email 2>/dev/null || echo ""
        }}

        get_git_name() {{
          git config user.name 2>/dev/null || echo ""
        }}

        # Build JSON from key=value pairs. Usage: build_json key1 val1 key2 val2 ...
        build_json() {{
          J='{{'
          SEP=""
          while [ $# -ge 2 ]; do
            KEY="$1"; VAL="$2"; shift 2
            if [ "$KEY" = "_int" ]; then
              # Next pair is an integer field: _int bud_number 42
              KEY="$VAL"; VAL="$1"; shift
              J="$J${{SEP}}\\"$KEY\\":$VAL"
            else
              J="$J${{SEP}}\\"$KEY\\":\\"$(escape_json "$VAL")\\""
            fi
            SEP=","
          done
          printf '%s}}' "$J"
        }}

        # Fire-and-forget POST with Bearer auth. No-op if no token.
        bg_post() {{
          [ -z "$TOKEN" ] && return 0
          curl -s -X POST "$BACKEND_URL/mcp/dev-activity" \\
            -H "Content-Type: application/json" \\
            -H "Authorization: Bearer $TOKEN" \\
            --connect-timeout 5 --max-time 10 \\
            -d "$1" >/dev/null 2>&1 &
        }}

        # Read a field from the session context file
        session_file() {{
          echo "${{TMPDIR:-/tmp}}/.bodhiorchard-session-$1.json"
        }}

        session_get() {{
          # session_get <session_id> <field>
          F=$(session_file "$1")
          PAT=$(printf '"%s":"[^"]*"' "$2")
          [ -f "$F" ] && grep -o "$PAT" "$F" | head -1 | cut -d'"' -f4
        }}

        # Re-detect BUD from current branch and update session file
        refresh_session_bud() {{
          SID="$1"
          SF=$(session_file "$SID")
          [ -f "$SF" ] || return 0
          NEW_BUD=$(get_bud_from_branch)
          OLD_BUD=$(session_get "$SID" bud_number)
          if [ "$NEW_BUD" != "$OLD_BUD" ] && [ -n "$NEW_BUD" ]; then
            TMP="$SF.tmp"
            sed 's/"bud_number":"[^"]*"/"bud_number":"'"$NEW_BUD"'"/' \\
              "$SF" > "$TMP" 2>/dev/null && mv "$TMP" "$SF"
            rm -f "$TMP"
          fi
          # Also update branch
          CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
          OLD_BRANCH=$(session_get "$SID" branch)
          if [ "$CUR_BRANCH" != "$OLD_BRANCH" ]; then
            TMP="$SF.tmp"
            sed 's/"branch":"[^"]*"/"branch":"'"$(escape_json "$CUR_BRANCH")"'"/' \\
              "$SF" > "$TMP" 2>/dev/null && mv "$TMP" "$SF"
            rm -f "$TMP"
          fi
        }}
    """).format(marker=_CLAUDE_HOOK_MARKER, url=backend_url)


def _build_session_start_sh() -> str:
    """Build the SessionStart hook — injects identity and BUD context."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")
        [ -z "$SESSION_ID" ] && exit 0

        NAME=$(get_git_name)
        EMAIL=$(get_git_email)
        BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
        BUD_NUM=$(get_bud_from_branch)

        # Write session context for later hooks (escape values for safe JSON)
        ENAME=$(escape_json "$NAME")
        EEMAIL=$(escape_json "$EMAIL")
        EBRANCH=$(escape_json "$BRANCH")
        SF=$(session_file "$SESSION_ID")
        printf '{{"session_id":"%s","name":"%s","email":"%s","branch":"%s","bud_number":"%s"}}' \\
          "$SESSION_ID" "$ENAME" "$EEMAIL" "$EBRANCH" "$BUD_NUM" > "$SF"

        # Inject context into Claude
        echo "Developer: $NAME ($EMAIL)"
        echo "Branch: $BRANCH"
        if [ -n "$BUD_NUM" ]; then
          echo "Active BUD: BUD-$(printf '%03d' "$BUD_NUM")"
        else
          echo "No active BUD from branch. Mention a BUD in your prompt if working on one."
        fi

        # Extract model and source from Claude Code input
        MODEL=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(d.get('model',''))
except: pass
" 2>/dev/null)

        # Report to backend with model in metadata
        J=$(build_json session_id "$SESSION_ID" event_type session_start \\
          author_email "$EMAIL" branch "$BRANCH" \\
          repo_path "$(pwd)" message "Session started")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        [ -n "$MODEL" ] && \\
          J=$(printf '%s' "$J" | \\
          sed "s/}}$/,\\"metadata\\":{{\\"model\\":\\"$(escape_json "$MODEL")\\"}}}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_session_end_sh() -> str:
    """Build the SessionEnd hook — reports session end."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")
        [ -z "$SESSION_ID" ] && exit 0

        EMAIL=$(session_get "$SESSION_ID" email)
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"
        [ -z "$BUD_NUM" ] && BUD_NUM=$(get_bud_from_branch)

        J=$(build_json session_id "$SESSION_ID" event_type session_end \\
          author_email "$EMAIL" branch "$BRANCH" \\
          repo_path "$(pwd)" message "Session ended")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"

        # Clean up session file
        rm -f "$(session_file "$SESSION_ID")"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_post_commit_track_sh() -> str:
    """Build the PostToolUse(Bash) hook — tracks git commits."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)

        # Only process git commit commands
        CMD=$(printf '%s' "$INPUT" | grep -o '"command":"[^"]*"' | head -1 | cut -d'"' -f4)
        case "$CMD" in *git\\ commit*|*git\\ -c*commit*) ;; *) exit 0 ;; esac

        SHA=$(git rev-parse HEAD 2>/dev/null || exit 0)
        BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
        BUD_NUM=$(get_bud_from_branch)
        EMAIL=$(get_git_email)
        MSG=$(git log -1 --format=%s 2>/dev/null | head -c 400)
        FILES=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | tr '\\n' ',')
        REPO=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        J=$(build_json session_id "$SESSION_ID" event_type commit \\
          author_email "$EMAIL" branch "$BRANCH" repo_path "$REPO" \\
          message "$MSG" commit_sha "$SHA" files_changed "$FILES")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_file_change_track_sh() -> str:
    """Build the PostToolUse(Edit|Write) hook — tracks file changes."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        # Extract file_path from tool_input
        FPATH=$(printf '%s' "$INPUT" | grep -o '"file_path":"[^"]*"' | head -1 | cut -d'"' -f4)
        [ -z "$FPATH" ] && exit 0

        TOOL=$(printf '%s' "$INPUT" | grep -o '"tool_name":"[^"]*"' | head -1 | cut -d'"' -f4)
        refresh_session_bud "$SESSION_ID"
        EMAIL=$(session_get "$SESSION_ID" email)
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"
        [ -z "$BUD_NUM" ] && BUD_NUM=$(get_bud_from_branch)
        REPO=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

        J=$(build_json session_id "$SESSION_ID" event_type file_change \\
          author_email "$EMAIL" branch "$BRANCH" repo_path "$REPO" \\
          file_path "$FPATH" message "$TOOL: $FPATH")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_tool_error_track_sh() -> str:
    """Build the PostToolUseFailure hook — tracks tool errors."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        TOOL=$(printf '%s' "$INPUT" | grep -o '"tool_name":"[^"]*"' | head -1 | cut -d'"' -f4)
        ERR=$(printf '%s' "$INPUT" | grep -o '"error":"[^"]*"' | \\
          head -1 | cut -d'"' -f4 | head -c 500)
        EMAIL=$(session_get "$SESSION_ID" email)
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"
        [ -z "$BUD_NUM" ] && BUD_NUM=$(get_bud_from_branch)

        J=$(build_json session_id "$SESSION_ID" event_type tool_error \\
          author_email "$EMAIL" branch "$BRANCH" repo_path "$(pwd)" \\
          message "$TOOL failed: $ERR")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_api_error_track_sh() -> str:
    """Build the StopFailure hook — tracks API errors."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        ERR=$(printf '%s' "$INPUT" | grep -o '"error":"[^"]*"' | head -1 | cut -d'"' -f4)
        EMAIL=$(session_get "$SESSION_ID" email)
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        [ -z "$BUD_NUM" ] && BUD_NUM=$(get_bud_from_branch)

        J=$(build_json session_id "$SESSION_ID" event_type api_error \\
          author_email "$EMAIL" branch "$BRANCH" repo_path "$(pwd)" message "API: $ERR")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_activity_report_sh() -> str:
    """Build the Stop hook — reports activity summary."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        refresh_session_bud "$SESSION_ID"
        EMAIL=$(session_get "$SESSION_ID" email)
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"
        [ -z "$BUD_NUM" ] && BUD_NUM=$(get_bud_from_branch)

        # Extract summary from last assistant message (handles escapes, newlines)
        SUMMARY=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(d.get('last_assistant_message','')[:500])
except: pass
" 2>/dev/null)

        J=$(build_json session_id "$SESSION_ID" event_type activity_summary \\
          author_email "$EMAIL" branch "$BRANCH" \\
          repo_path "$(pwd)" message "$SUMMARY")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_detect_bud_prompt_sh() -> str:
    """Build the UserPromptSubmit hook — detects BUD references + captures prompt."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        # Extract prompt text (handles escapes via Python)
        PROMPT=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(d.get('prompt','')[:500])
except: pass
" 2>/dev/null)

        # Detect BUD references in prompt
        RAW_REF=$(echo "$PROMPT" | grep -ioE 'bud[- #]*([0-9]+)' | head -1 | grep -oE '[0-9]+')
        BUD_REF=$([ -n "$RAW_REF" ] && printf '%d' "$RAW_REF" || echo "")

        if [ -n "$BUD_REF" ]; then
          SF=$(session_file "$SESSION_ID")
          if [ -f "$SF" ]; then
            TMP="$SF.tmp"
            sed 's/"bud_number":"[^"]*"/"bud_number":"'"$BUD_REF"'"/' \\
              "$SF" > "$TMP" 2>/dev/null && mv "$TMP" "$SF"
            rm -f "$TMP"
          fi
        fi

        # Post user prompt event (captures what the developer asked)
        [ -z "$PROMPT" ] && exit 0
        EMAIL=$(session_get "$SESSION_ID" email)
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        [ -z "$BUD_NUM" ] && BUD_NUM="$BUD_REF"
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"

        J=$(build_json session_id "$SESSION_ID" event_type user_prompt \\
          author_email "$EMAIL" branch "$BRANCH" \\
          repo_path "$(pwd)" message "$PROMPT")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_subagent_start_sh() -> str:
    """Build the SubagentStart hook — tracks when Claude spawns sub-agents."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        AGENT_TYPE=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(d.get('agent_type',''))
except: pass
" 2>/dev/null)
        [ -z "$AGENT_TYPE" ] && exit 0

        EMAIL=$(session_get "$SESSION_ID" email)
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"
        [ -z "$BUD_NUM" ] && BUD_NUM=$(get_bud_from_branch)

        J=$(build_json session_id "$SESSION_ID" event_type subagent_start \\
          author_email "$EMAIL" branch "$BRANCH" \\
          repo_path "$(pwd)" message "Agent: $AGENT_TYPE")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


def _build_subagent_stop_sh() -> str:
    """Build the SubagentStop hook — tracks sub-agent completion with summary."""
    return textwrap.dedent("""\
        {marker}
        #!/bin/sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        . "$SCRIPT_DIR/_common.sh"

        INPUT=$(cat)
        SESSION_ID=$(sanitize_path "$(get_sid "$INPUT")")

        AGENT_TYPE=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(d.get('agent_type',''))
except: pass
" 2>/dev/null)
        SUMMARY=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(d.get('last_assistant_message','')[:500])
except: pass
" 2>/dev/null)

        EMAIL=$(session_get "$SESSION_ID" email)
        BUD_NUM=$(session_get "$SESSION_ID" bud_number)
        BRANCH=$(session_get "$SESSION_ID" branch)
        BRANCH="${{BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")}}"
        [ -z "$BUD_NUM" ] && BUD_NUM=$(get_bud_from_branch)

        MSG="Agent $AGENT_TYPE done"
        [ -n "$SUMMARY" ] && MSG="$SUMMARY"

        J=$(build_json session_id "$SESSION_ID" event_type subagent_stop \\
          author_email "$EMAIL" branch "$BRANCH" \\
          repo_path "$(pwd)" message "$MSG")
        [ -n "$BUD_NUM" ] && \\
          J=$(printf '%s' "$J" | sed "s/}}$/,\\"bud_number\\":$BUD_NUM}}/")
        bg_post "$J"
        exit 0
    """).format(marker=_CLAUDE_HOOK_MARKER)


async def install_claude_hooks(repo_path: str, backend_url: str) -> bool:
    """Install Claude Code hook scripts in a repository.

    Writes hooks to ``.claude/hooks/`` and configures them in
    ``.claude/settings.json``. Scripts use ``$BODHIORCHARD_MCP_TOKEN``
    for auth — no org_id baked in.

    Idempotent: checks for marker string before writing.

    Args:
        repo_path: Absolute path to the git repository.
        backend_url: Public URL of the Bodhiorchard backend.

    Returns:
        True if hook files were written (changed), False if already up to date.
    """
    repo = Path(repo_path)
    hooks_dir = repo / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts = [
        ("_common.sh", _build_common_sh(backend_url)),
        ("session-start.sh", _build_session_start_sh()),
        ("session-end.sh", _build_session_end_sh()),
        ("post-commit-track.sh", _build_post_commit_track_sh()),
        ("file-change-track.sh", _build_file_change_track_sh()),
        ("tool-error-track.sh", _build_tool_error_track_sh()),
        ("api-error-track.sh", _build_api_error_track_sh()),
        ("activity-report.sh", _build_activity_report_sh()),
        ("detect-bud-prompt.sh", _build_detect_bud_prompt_sh()),
        ("subagent-start.sh", _build_subagent_start_sh()),
        ("subagent-stop.sh", _build_subagent_stop_sh()),
    ]

    changed = False
    for filename, content in scripts:
        hook_path = hooks_dir / filename
        if hook_path.exists():
            existing = hook_path.read_text()
            if _CLAUDE_HOOK_MARKER in existing and existing.strip() == content.strip():
                continue
        hook_path.write_text(content)
        hook_path.chmod(0o755)
        changed = True

    # Add hooks configuration to .claude/settings.json
    import contextlib

    settings_path = repo / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            settings = json.loads(settings_path.read_text())

    hooks_config = {
        "SessionStart": [
            {
                "matcher": "startup",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/session-start.sh",
                        "timeout": 10,
                    },
                ],
            },
        ],
        "SessionEnd": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/session-end.sh",
                        "timeout": 10,
                    },
                ],
            },
        ],
        "PostToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/post-commit-track.sh",
                        "timeout": 15,
                    },
                ],
            },
            {
                "matcher": "Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/file-change-track.sh",
                        "timeout": 10,
                    },
                ],
            },
        ],
        "PostToolUseFailure": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/tool-error-track.sh",
                        "timeout": 10,
                    },
                ],
            },
        ],
        "StopFailure": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/api-error-track.sh",
                        "timeout": 10,
                    },
                ],
            },
        ],
        "Stop": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/activity-report.sh",
                        "timeout": 10,
                    },
                ],
            },
        ],
        "UserPromptSubmit": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/detect-bud-prompt.sh",
                        "timeout": 5,
                    },
                ],
            },
        ],
        "SubagentStart": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/subagent-start.sh",
                        "timeout": 5,
                    },
                ],
            },
        ],
        "SubagentStop": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "sh .claude/hooks/subagent-stop.sh",
                        "timeout": 10,
                    },
                ],
            },
        ],
    }

    if settings.get("hooks") != hooks_config:
        settings["hooks"] = hooks_config
        settings_path.write_text(json.dumps(settings, indent=2))
        changed = True

    logger.info("claude_hooks_installed", repo=repo_path, changed=changed)
    return changed


# ── .gitignore management ──────────────────────────────────────────


def add_bodhiorchard_gitignore(repo_path: str) -> bool:
    """Append .bodhiorchard/ to .gitignore if not already present.

    Idempotent.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        True if the file was changed, False if already up to date.
    """
    gitignore = Path(repo_path) / ".gitignore"
    entry = ".bodhiorchard/"

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
    ensuring all developers get Bodhiorchard's git hooks without manual
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


# ── Commit Bodhiorchard setup files ─────────────────────────────────


async def commit_and_push_bodhiorchard_setup(repo_path: str, base_branch: str) -> str | None:
    """Create a branch, commit Bodhiorchard setup files, and push to origin.

    Creates ``bodhiorchard/init-setup`` from the base branch, stages only
    the files Bodhiorchard modifies, commits, and pushes. The team can
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

    # Earlier scan phases write Bodhiorchard's own files (MCP config, git
    # hooks, a ``prepare`` script in package.json) directly into the
    # working tree. Those uncommitted changes will collide with the
    # upcoming branch switch — git refuses to checkout when it would
    # overwrite dirty files. Stash everything (including untracked) so the
    # switch is clean; we pop the stash back in the ``finally`` below so
    # the staging step below still has the files to commit.
    _, _, dirty_rc = await run_git(
        ["diff-index", "--quiet", "HEAD", "--"], cwd=repo_path
    )
    _, untracked_out, _ = await run_git(
        ["ls-files", "--others", "--exclude-standard"], cwd=repo_path
    )
    has_dirty = dirty_rc != 0 or bool(untracked_out.strip())
    stashed = False
    if has_dirty:
        _, _, stash_rc = await run_git(
            ["stash", "push", "--include-untracked", "-m", "bodhiorchard-setup-pre-checkout"],
            cwd=repo_path,
        )
        stashed = stash_rc == 0
        if not stashed:
            logger.warning(
                "bodhiorchard_setup_stash_failed",
                error="git stash push failed — checkout may still collide with local changes",
            )

    async def _restore_dirty_state() -> None:
        if not stashed:
            return
        _, stderr, rc = await run_git(["stash", "pop"], cwd=repo_path)
        if rc != 0:
            # Conflict applying the stash back — usually because the target
            # branch has a tracked file where we had an untracked one, or
            # already modified the same lines. Keep the stash entry so the
            # user can recover manually (``git stash list``) rather than
            # silently committing a half-applied tree.
            logger.warning(
                "bodhiorchard_setup_stash_pop_conflict",
                error=stderr[:200],
                hint="stash entry kept; resolve via `git stash list` + `git stash apply`",
            )

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
            logger.warning("bodhiorchard_setup_checkout_failed", error=stderr[:200])
            await _restore_dirty_state()
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
            logger.warning("bodhiorchard_setup_branch_failed", error=stderr[:200])
            await _restore_dirty_state()
            return None

    # Now on the setup branch — pop the stash so the files we need to
    # commit (MCP config, hooks, package.json prepare script) are in the
    # working tree again.
    await _restore_dirty_state()

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
            logger.debug("bodhiorchard_setup_nothing_to_commit", repo=repo_path)
            return None

        # Commit
        _, stderr, rc = await run_git(
            [
                "commit",
                "-m",
                "chore(bodhiorchard): add MCP tools, git hooks, and config\n\n"
                "Auto-committed by Bodhiorchard scan pipeline.\n"
                "- .claude/settings.json: Bodhiorchard MCP server config\n"
                "- .githooks/: pre-commit (BUD validation) + post-commit (tracking)\n"
                "- package.json: prepare script sets core.hooksPath on npm install\n"
                "- .gitignore: exclude .bodhiorchard/ worktrees\n"
                "- CLAUDE.md: GitNexus code intelligence integration\n"
                "- .claude/skills/: GitNexus agent skill definitions",
            ],
            cwd=repo_path,
        )
        if rc != 0:
            logger.warning("bodhiorchard_setup_commit_failed", error=stderr[:200])
            return None

        # Push to origin (force-with-lease when updating existing branch)
        push_cmd = ["push", "-u", "origin", _SETUP_BRANCH]
        if branch_exists_remote:
            push_cmd = ["push", "--force-with-lease", "-u", "origin", _SETUP_BRANCH]
        _, stderr, rc = await run_git(push_cmd, cwd=repo_path)
        if rc != 0:
            # No remote or push failed — merge setup into base branch directly
            logger.info("bodhiorchard_setup_no_remote_merging", repo=repo_path)

            # Remove worktrees that may lock the base branch
            for wt_name in ("main", "develop"):
                wt_path = Path(repo_path) / ".bodhiorchard" / wt_name
                if wt_path.exists():
                    await run_git(
                        ["worktree", "remove", str(wt_path), "--force"],
                        cwd=repo_path,
                    )

            await run_git(["checkout", base_branch], cwd=repo_path)
            _, merge_err, merge_rc = await run_git(
                ["merge", _SETUP_BRANCH, "--no-edit"],
                cwd=repo_path,
            )
            if merge_rc == 0:
                await run_git(["branch", "-d", _SETUP_BRANCH], cwd=repo_path)
                logger.info("bodhiorchard_setup_merged_locally", repo=repo_path)
                return _SETUP_BRANCH
            logger.warning(
                "bodhiorchard_setup_merge_failed",
                repo=repo_path,
                error=merge_err[:200],
            )
            return None

        logger.info(
            "bodhiorchard_setup_pushed",
            repo=repo_path,
            branch=_SETUP_BRANCH,
        )
        return _SETUP_BRANCH
    finally:
        # Remove worktrees that may lock the base branch, then switch back
        wt_main = Path(repo_path) / ".bodhiorchard" / "main"
        if wt_main.exists():
            await run_git(
                ["worktree", "remove", str(wt_main), "--force"],
                cwd=repo_path,
            )
        await run_git(["checkout", base_branch], cwd=repo_path)


async def create_setup_pr(repo_path: str, base_branch: str, pushed_branch: str) -> str | None:
    """Create a pull request for the Bodhiorchard setup branch via ``gh`` CLI.

    Falls back gracefully when ``gh`` is not installed or not authenticated.

    Args:
        repo_path: Absolute path to the git repository.
        base_branch: Target branch for the PR (e.g. "main").
        pushed_branch: Source branch that was pushed (e.g. "bodhiorchard/init-setup").

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
                "chore: add Bodhiorchard MCP tools, git hooks, and config",
                "--body",
                "## Summary\n\n"
                "Auto-generated by Bodhiorchard scan pipeline.\n\n"
                "- `.claude/settings.json` — Bodhiorchard MCP server config\n"
                "- `.githooks/` — pre-commit (BUD validation) + "
                "post-commit (tracking)\n"
                "- `package.json` — prepare script sets `core.hooksPath`\n"
                "- `.gitignore` — exclude `.bodhiorchard/` worktrees\n"
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
