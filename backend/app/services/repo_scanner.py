"""Re-export shim for backwards compatibility.

All symbols that were previously defined here have been split into:
- ``git_operations`` — git CLI wrappers, branch detection, stash/restore
- ``gitnexus_indexer`` — GitNexus analysis and knowledge graph queries
- ``repo_setup`` — MCP init, hooks, gitignore, package.json, commit/push, PR

This module re-exports every public symbol so existing consumers
(``settings.py``, ``scan_pipeline.py``, ``job_handlers.py``) keep working.
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
from app.services.gitnexus_indexer import (  # noqa: F401
    DocEntry,
    FeatureEntry,
    GitNexusNotInstalledError,
    GitNexusResult,
    ProcessEntry,
    extract_repo_docs,
    index_repo_with_gitnexus,
)
from app.services.repo_setup import (  # noqa: F401
    add_bodhigrove_gitignore,
    add_prepare_script,
    commit_and_push_bodhigrove_setup,
    create_setup_pr,
    detect_repo_type,
    ensure_repo_worktrees,
    init_bodhigrove_mcp_in_repo,
    install_hooks,
)
