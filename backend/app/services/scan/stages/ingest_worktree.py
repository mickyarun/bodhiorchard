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

"""Worktree helpers for the ``ingest`` stage.

Mirrors ``app/services/repo_setup.py::ensure_repo_worktrees`` semantics
so ingest behaves the same way the live scan does, just under a
distinct parent dir so the two pipelines don't share state.

The sandbox worktree lives at
``<data_dir>/scan-worktrees/<repo-slug>/<branch>`` — **outside** the
tracked repo. Earlier iterations parked it at
``<repo>/.bodhiorchard/scan-test/<branch>`` for "everything-in-one-tree"
ergonomics, but graphify's file collector filters out any path with a
component starting with ``.`` (its dotfile rule), so the leading
``.bodhiorchard`` made every file under that worktree invisible to the
indexer → empty file list → ``"no source files found in repo"``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.config import settings
from app.services.git_operations import run_git
from app.services.scan.stages._origin_auth import (
    build_app_https_url_for_origin,
    refresh_origin_auth,
)

if TYPE_CHECKING:
    from app.models.organization import Organization

logger = structlog.get_logger(__name__)

# Slug helper for the repo-disambiguating dir name. Strips anything that
# isn't a safe filesystem character; collisions between repos with the
# same basename are vanishingly rare for typical orgs and tolerable for
# a sandbox worktree (worst case: one extra ``git worktree add`` fails
# because the branch is already checked out, then the caller resets).
_SLUG_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _scan_worktree_parent(repo_path: str) -> Path:
    """Return the dot-free parent dir for this repo's sandbox worktrees.

    ``<data_dir>/scan-worktrees/<basename>``. The data_dir is resolved
    at call time so tests overriding ``BODHIORCHARD_DATA_DIR`` take
    effect without a module reload.
    """
    repo_slug = _SLUG_UNSAFE_RE.sub("-", Path(repo_path).name) or "repo"
    return Path(settings.storage.data_dir) / "scan-worktrees" / repo_slug


async def _has_origin_remote(repo_path: str) -> bool:
    """Return True iff the repo has an ``origin`` remote configured."""
    _, _, rc = await run_git(["remote", "get-url", "origin"], cwd=repo_path)
    return rc == 0


async def ensure_scan_test_worktree(
    repo_path: str,
    main_branch: str,
    *,
    skip_fetch: bool,
    org: Organization | None = None,
) -> str:
    """Create or refresh the sandbox worktree.

    Resolution order:

    * If the repo is already on ``main_branch`` at its root, use
      ``repo_path`` directly. Git refuses to ``worktree add`` a branch
      that's already checked out elsewhere, so materialising a separate
      worktree would fail.
    * Otherwise, materialise (or adopt)
      ``<data_dir>/scan-worktrees/<repo-slug>/<branch>``, then fetch +
      hard-reset it to ``origin/<main_branch>`` (or the local branch ref
      if there's no ``origin`` remote — e.g. local-path imports). The
      worktree path lives outside the repo and outside any dot-prefixed
      directory so graphify's dotfile filter doesn't skip every file.
    * If a stale registration points to a missing dir, prune and recreate.

    Returns the absolute path of the worktree to operate on.
    """
    current_branch_out, _, _ = await run_git(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path,
    )
    current_branch = current_branch_out.strip()
    has_origin = await _has_origin_remote(repo_path)

    if current_branch == main_branch:
        if not skip_fetch:
            await fetch_and_reset(repo_path, main_branch, has_origin=has_origin, org=org)
        return repo_path

    parent = _scan_worktree_parent(repo_path)
    parent.mkdir(parents=True, exist_ok=True)
    wt_path = parent / main_branch.replace("/", "-")
    wt_str = str(wt_path)

    await run_git(["worktree", "prune"], cwd=repo_path)
    # If a worktree on ``main_branch`` is still registered at a path
    # that isn't ours (e.g. a stale ``<repo>/.bodhiorchard/scan-test/main``
    # from before the dot-prefix-bug fix moved worktrees to ``<data_dir>``),
    # remove it so the subsequent ``worktree add`` doesn't trip on
    # "branch already used elsewhere".
    await _remove_conflicting_worktree(repo_path, main_branch, keep=wt_str)

    if not wt_path.exists():
        _, stderr, rc = await run_git(
            ["worktree", "add", wt_str, main_branch],
            cwd=repo_path,
        )
        if rc != 0:
            # Branch may not have a local ref yet — try creating from origin
            # (only meaningful when ``origin`` exists).
            if not has_origin:
                raise RuntimeError(f"git worktree add failed (no origin): {stderr[:200]}")
            _, stderr2, rc2 = await run_git(
                ["worktree", "add", "-B", main_branch, wt_str, f"origin/{main_branch}"],
                cwd=repo_path,
            )
            if rc2 != 0:
                raise RuntimeError(f"git worktree add failed: {stderr[:200]} / {stderr2[:200]}")

    if skip_fetch:
        return wt_str

    await fetch_and_reset(
        repo_path,
        main_branch,
        worktree=wt_str,
        has_origin=has_origin,
        org=org,
    )
    return wt_str


async def fetch_and_reset(
    repo_path: str,
    main_branch: str,
    *,
    worktree: str | None = None,
    has_origin: bool | None = None,
    org: Organization | None = None,
) -> None:
    """Fetch origin (if present) and hard-reset the target tree.

    With an ``origin`` remote, refreshes the origin auth (fresh GitHub
    App installation token, or ``GIT_SSH_COMMAND`` for SSH deploy keys —
    see :mod:`._origin_auth`), fetches, and resets to
    ``origin/<main_branch>``. Without an origin (e.g. local-path imports),
    skips the fetch and resets to the local ``<main_branch>`` ref instead.

    ``worktree`` is the path to reset; defaults to ``repo_path`` itself.
    ``org`` carries the GitHub App credentials when present; pass ``None``
    for sandbox / test runs without org context.
    """
    target = worktree or repo_path
    if has_origin is None:
        has_origin = await _has_origin_remote(repo_path)

    if has_origin:
        env = await refresh_origin_auth(repo_path, org)
        _, stderr, rc = await run_git(
            ["fetch", "origin", "--prune"],
            cwd=repo_path,
            env=env,
        )
        if rc != 0:
            logger.warning("scan_ingest_fetch_failed", error=stderr[:200])
            # SSH fetch can fail when the per-repo deploy key isn't
            # registered. The org's GitHub App token covers every
            # selected repo over HTTPS, so retry once with a one-shot
            # ``-c remote.origin.url=...`` override. The persistent
            # SSH remote stays in ``.git/config`` so the user's
            # ``git push`` workflow is unaffected.
            override_url = await build_app_https_url_for_origin(repo_path, org)
            if override_url is not None:
                _, stderr2, rc2 = await run_git(
                    [
                        "-c",
                        f"remote.origin.url={override_url}",
                        "fetch",
                        "origin",
                        "--prune",
                    ],
                    cwd=repo_path,
                )
                if rc2 == 0:
                    logger.info("scan_ingest_fetch_succeeded_via_app_fallback")
                else:
                    logger.warning(
                        "scan_ingest_fetch_failed_after_app_fallback",
                        error=stderr2[:200],
                    )
        reset_ref = f"origin/{main_branch}"
    else:
        reset_ref = main_branch

    _, stderr, rc = await run_git(["reset", "--hard", reset_ref], cwd=target)
    if rc == 0:
        return

    # Propagate the failure to the caller for BOTH live-repo and worktree
    # targets. Previously, worktree failures triggered a silent
    # ``shutil.rmtree(wt_path)`` rebuild — that masked worktree
    # corruption and, more importantly, could wipe the filesystem out
    # from under a concurrent reader (scan stage / narrow-synth
    # consumer reading the same path). Now the consumer's webhook_logs
    # row flips to FAILED, orphan recovery re-publishes on the next
    # boot, and the operator sees the actual git error instead of a
    # "no source files found" downstream symptom.
    target_label = "worktree" if worktree is not None else "repo"
    raise RuntimeError(f"failed to reset {target_label} {target} to {reset_ref}: {stderr[:200]}")


async def _remove_conflicting_worktree(repo_path: str, main_branch: str, *, keep: str) -> None:
    """Drop any worktree on ``main_branch`` whose path isn't ``keep``.

    Git refuses ``worktree add`` for a branch that's already checked out
    elsewhere. This commonly happens after the dot-prefix fix: the old
    ``<repo>/.bodhiorchard/scan-test/main`` worktree still registers
    ``main`` even though we're trying to materialise the new
    ``<data_dir>/scan-worktrees/<slug>/main``. Without this cleanup the
    new ``worktree add`` fails on every webhook until the operator
    removes the stale registration by hand.
    """
    stdout, _, rc = await run_git(
        ["worktree", "list", "--porcelain"],
        cwd=repo_path,
    )
    if rc != 0:
        return
    # ``--porcelain`` yields blocks separated by blank lines:
    #   worktree /abs/path
    #   HEAD <sha>
    #   branch refs/heads/<name>
    keep_norm = str(Path(keep))
    branch_ref = f"refs/heads/{main_branch}"
    for block in stdout.split("\n\n"):
        path_line: str | None = None
        branch_line: str | None = None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path_line = line[len("worktree ") :].strip()
            elif line.startswith("branch "):
                branch_line = line[len("branch ") :].strip()
        if not path_line or branch_line != branch_ref:
            continue
        if str(Path(path_line)) == keep_norm:
            continue
        logger.info(
            "scan_ingest_removing_stale_worktree",
            stale_path=path_line,
            branch=main_branch,
        )
        await run_git(
            ["worktree", "remove", path_line, "--force"],
            cwd=repo_path,
        )
    await run_git(["worktree", "prune"], cwd=repo_path)
