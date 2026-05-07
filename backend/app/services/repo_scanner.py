# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Re-export shim for backwards compatibility.

Symbols that were previously defined here have been split into:
- ``git_operations`` — git CLI wrappers, branch detection, stash/restore
- ``code_indexer`` — graphify-based code-graph indexing
- ``repo_setup`` — MCP init, hooks, gitignore, package.json, commit/push, PR

Consumers that need code-graph data should import directly from
``app.services.code_indexer``.
"""

from app.services.git_operations import (  # noqa: F401
    _detect_develop_branch,
    _detect_main_branch,
    _run_shell_cmd,
    detect_uncommitted_changes,
    list_remote_branches,
    restore_after_scan,
    run_git,
    stash_and_checkout_main,
)
from app.services.repo_setup import (  # noqa: F401
    add_bodhiorchard_gitignore,
    add_prepare_script,
    commit_and_push_bodhiorchard_setup,
    create_setup_pr,
    ensure_repo_worktrees,
    init_bodhiorchard_mcp_in_repo,
    install_hooks,
)
