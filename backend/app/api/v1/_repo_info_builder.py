# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Helpers shared by the Settings → Code endpoints.

Every endpoint in :mod:`settings_repos` returns a ``RepoInfo`` row, but
each carries a different mix of optional fields (last-scan summary,
design-system status, link counts, dirty-flag, …). Inlining the
constructor at every call site invited copy-paste drift — fields added
to the schema kept slipping past one or two endpoints.

This module owns:

* :func:`detect_design_system_status` — three-state ds chip
  (``ready`` / ``extracting`` / ``none``), with the ``extracting``
  branch peeking at the job queue.
* :func:`detect_setup_status` — ``merged`` / ``not_setup`` based on
  on-disk markers (``.claude/settings.json`` + ``.githooks/post-commit``).
* :func:`setup_compare_url` — GitHub deep-link the Settings row uses
  when the App-driven PR didn't open automatically.
* :func:`build_repo_info` — single source of truth for the response
  shape; every endpoint hands its ``TrackedRepository`` plus whatever
  per-call extras it knows. Fields the caller doesn't supply fall back
  to their schema defaults rather than being forced to ``None``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models.scan_repo_run import ScanRepoRun
from app.models.tracked_repository import TrackedRepository
from app.schemas.settings import RepoInfo
from app.services.job_queue import JOB_DESIGN_EXTRACT, is_job_active


def detect_design_system_status(repo_id: str, ds_repo_ids: set[str]) -> str:
    """Returns ``ready`` / ``extracting`` / ``none``."""
    if repo_id in ds_repo_ids:
        return "ready"
    if is_job_active(JOB_DESIGN_EXTRACT, {"repo_id": repo_id}):
        return "extracting"
    return "none"


def detect_setup_status(repo_path: str) -> str:
    """Returns ``merged`` if MCP + post-commit hook are on disk, else ``not_setup``."""
    mcp_config = Path(repo_path) / ".claude" / "settings.json"
    hooks_dir = Path(repo_path) / ".githooks" / "post-commit"
    if mcp_config.exists() and hooks_dir.exists():
        return "merged"
    return "not_setup"


def setup_compare_url(github_repo_full_name: str | None, main_branch: str | None) -> str | None:
    """GitHub compare URL for the setup branch, or ``None`` when unavailable.

    Used by the row chip to deep-link to GitHub's "open a PR" page when
    the setup branch was pushed but the GitHub App isn't configured to
    open the PR automatically. Kept server-side so the URL shape lives
    next to ``github_repo_full_name`` ownership.
    """
    if not github_repo_full_name or "/" not in github_repo_full_name:
        return None
    base = main_branch or "main"
    return (
        f"https://github.com/{github_repo_full_name}/compare/"
        f"{base}...bodhiorchard/init-setup?quick_pull=1"
    )


def build_repo_info(
    repo: TrackedRepository,
    *,
    has_dirty: bool = False,
    last_run: ScanRepoRun | None = None,
    ds_repo_ids: set[str] | None = None,
    include_setup_compare: bool = False,
    include_classification: bool = False,
) -> RepoInfo:
    """Single ``RepoInfo`` constructor used by every Settings → Code endpoint.

    Optional kwargs match the per-endpoint context that was previously
    inlined. Anything not passed falls back to the schema's default —
    the list endpoint passes the full set; write-path endpoints pass
    only the basics + whatever they just mutated, and the frontend
    re-fetches the list afterwards to refresh chips it didn't compute.
    """
    fields: dict[str, Any] = {
        "id": str(repo.id),
        "path": repo.path,
        "name": repo.name,
        "status": repo.status.value,
        "lastScanned": repo.last_scanned_at.isoformat() if repo.last_scanned_at else None,
        "sha": repo.head_sha,
        "knowledgeCount": repo.knowledge_count,
        "featureCount": repo.feature_count,
        "mainBranch": repo.main_branch,
        "developBranch": repo.develop_branch,
        "uatBranch": repo.uat_branch,
        "hasUncommittedChanges": has_dirty,
        "githubRepo": repo.github_repo_full_name,
    }

    # The list endpoint signals "I want the full chip set" by passing
    # ``ds_repo_ids``. Wiring it onto a single switch keeps the per-row
    # render in one place; write-path endpoints continue to lean on the
    # schema defaults for the chips they don't compute.
    if ds_repo_ids is not None:
        fields["setupStatus"] = detect_setup_status(repo.path)
        fields["setupBranchPushedAt"] = (
            repo.setup_branch_pushed_at.isoformat()
            if repo.setup_branch_pushed_at is not None
            else None
        )
        fields["setupPrUrl"] = repo.setup_pr_url
        fields["setupPrNumber"] = repo.setup_pr_number
        fields["setupPrState"] = (
            repo.setup_pr_state.value if repo.setup_pr_state is not None else None
        )
        fields["setupCompareUrl"] = setup_compare_url(repo.github_repo_full_name, repo.main_branch)
        # DEBUG: surfaced for the chip tooltip — see ``setup_last_error``
        # column on ``tracked_repositories`` and migration ``zal_…``.
        fields["setupLastError"] = repo.setup_last_error
        fields["designSystemStatus"] = detect_design_system_status(str(repo.id), ds_repo_ids)
    elif include_setup_compare:
        fields["setupCompareUrl"] = setup_compare_url(repo.github_repo_full_name, repo.main_branch)

    if last_run is not None:
        fields["lastScanStatus"] = last_run.status.value
        fields["lastScanFinishedAt"] = (
            last_run.finished_at.isoformat() if last_run.finished_at is not None else None
        )
        fields["lastScanStartedAt"] = (
            last_run.started_at.isoformat() if last_run.started_at is not None else None
        )
        fields["lastScanFeatureCount"] = last_run.feature_count
        fields["lastScanId"] = str(last_run.scan_id)

    if include_classification or ds_repo_ids is not None:
        fields["repoLayer"] = repo.repo_layer.value if repo.repo_layer is not None else None
        fields["techStack"] = repo.tech_stack
        fields["dbFlavor"] = repo.db_flavor

    return RepoInfo(**fields)
