#!/usr/bin/env python3
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

"""End-to-end dispatcher smoke for the PR-merge narrow synthesis flow.

Validates the wiring from synthetic webhook -> dispatcher
(``pr_merge_update``) -> narrow synthesis job (``pr_narrow_synthesis``)
*creation*, but does NOT wait for Claude to run. The deterministic
shape (Option 1 of the step-10 design fork): one webhook POST, one log
scan, one cleanup. No tokens, no auth, no API polling.

Mechanics:

1. Resolve a tracked repo (``--repo-id`` or the first one found).
2. Generate a synthetic cluster id + base/head SHAs and seed two
   ``cluster_cache`` rows so ``_find_affected_clusters`` returns
   exactly that one cluster as "modified".
3. Capture the backend log's current size so we can scan only the
   tail produced by this run.
4. Fire ``mock_pr_webhook.py`` as a subprocess (with a unique mock
   PR number and the right ``--changed-files``).
5. Wait briefly, then scan the log tail for two marker events:
   ``pr_merge_update_clusters_affected`` (dispatcher ran) and a
   ``job_created job_type=pr_narrow_synthesis`` line (narrow job
   actually enqueued via ``create_job``).
6. Delete the seeded ``cluster_cache`` rows so the live DB is back
   to its pre-run state.

Required backend env (the script can't enforce these because the
backend runs in a separate process):

  * ``BODHI_MOCK_PR_FILES_PATH``  — same path this script writes via
    ``mock_pr_webhook.py`` so the dispatcher's
    ``GitHubClient.list_pr_files`` returns the simulated set instead
    of hitting GitHub.

Usage::

    cd backend && python scripts/smoke_narrow_synth.py \\
        --repo-id <uuid>             # optional; first tracked repo by default
        --wait 10                    # max seconds to poll for log markers
        --log-file logs/bodhi.log    # default
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
import uuid
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import delete, select

# Make ``app`` importable when invoked as ``python scripts/test_narrow_synth.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.cluster_cache import ClusterCache  # noqa: E402
from app.models.tracked_repository import TrackedRepository  # noqa: E402

DEFAULT_LOG_FILE = "logs/bodhi.log"
DEFAULT_WAIT_SECONDS = 10
POLL_INTERVAL_SECONDS = 0.25
DEFAULT_CHANGED_FILE = "src/harness_changed.py"
MARKER_DISPATCH = "pr_merge_update_clusters_affected"
MARKER_NARROW_CREATED = "job_created"  # paired with ``pr_narrow_synthesis``

# ANSI for clearer CLI output without pulling in a dep.
_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def _parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(
        prog="test_narrow_synth",
        description=(
            "Dispatcher-only smoke for the PR-merge narrow synthesis flow. "
            "Fires a signed synthetic webhook, scans the backend log for "
            "evidence the dispatcher routed to the narrow job, and cleans "
            "up the seeded cluster_cache rows."
        ),
    )
    parser.add_argument(
        "--repo-id",
        default=None,
        help="UUID of a tracked repo. Defaults to the first tracked repo.",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=DEFAULT_WAIT_SECONDS,
        help=(
            "Maximum seconds to poll the log tail for the expected markers "
            f"(default: {DEFAULT_WAIT_SECONDS}). Polls every "
            f"{POLL_INTERVAL_SECONDS}s and exits early once both markers "
            "are seen — the cap only matters on a slow/loaded box."
        ),
    )
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"Backend log file to scan (default: {DEFAULT_LOG_FILE}).",
    )
    parser.add_argument(
        "--changed-file",
        default=DEFAULT_CHANGED_FILE,
        help=f"Synthetic changed-file path (default: {DEFAULT_CHANGED_FILE}).",
    )
    return parser.parse_args()


async def _resolve_repo(db, repo_id_arg: str | None) -> TrackedRepository:  # type: ignore[no-untyped-def]
    """Return a tracked repo to target, by UUID or the first one we find."""
    if repo_id_arg:
        repo = await db.get(TrackedRepository, uuid.UUID(repo_id_arg))
        if repo is None:
            sys.exit(f"error: tracked repo {repo_id_arg} not found")
        if not repo.github_repo_full_name:
            sys.exit(f"error: repo {repo_id_arg} has no github_repo_full_name")
        return repo
    result = await db.execute(
        select(TrackedRepository).where(TrackedRepository.github_repo_full_name.is_not(None)).limit(1)
    )
    repo = result.scalars().first()
    if repo is None:
        sys.exit("error: no tracked repos with github_repo_full_name set")
    return repo


async def _seed_clusters(  # type: ignore[no-untyped-def]
    db,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    cluster_id: str,
    base_sha: str,
    head_sha: str,
    files: list[str],
) -> None:
    """Insert matching base/head ``cluster_cache`` rows so the dispatcher
    routes the change through the narrow path.

    Both rows share a signature so ``_find_affected_clusters`` sees the
    cluster as "modified" (signature unchanged across SHAs, but the
    PR's changed paths intersect ``files``).
    """
    signature = f"harness-sig-{cluster_id}"
    for sha in (base_sha, head_sha):
        db.add(
            ClusterCache(
                org_id=org_id,
                repo_id=repo_id,
                head_sha=sha,
                cluster_id=cluster_id,
                label="narrow-synth-harness",
                symbol_count=1,
                files=files,
                symbols=[],
                signature=signature,
            )
        )
    await db.commit()


async def _cleanup(  # type: ignore[no-untyped-def]
    db,
    *,
    repo_id: uuid.UUID,
    cluster_id: str,
) -> None:
    """Drop the seeded ``cluster_cache`` rows so the live DB is unchanged."""
    await db.execute(
        delete(ClusterCache).where(
            ClusterCache.repo_id == repo_id,
            ClusterCache.cluster_id == cluster_id,
        )
    )
    await db.commit()


def _fire_webhook(
    *,
    repo_id: uuid.UUID,
    pr_number: int,
    base_sha: str,
    head_sha: str,
    changed_files: list[str],
) -> int:
    """Run ``mock_pr_webhook.py`` as a subprocess.

    Reuses the existing driver so the HMAC + payload shape stays in
    one place. Returns the subprocess exit code; non-zero indicates a
    failed POST (the harness aborts before scanning logs).
    """
    script_path = Path(__file__).resolve().parent / "mock_pr_webhook.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--repo-id",
        str(repo_id),
        "--pr-number",
        str(pr_number),
        "--base-sha",
        base_sha,
        "--head-sha",
        head_sha,
        "--changed-files",
        ",".join(changed_files),
    ]
    print(f"  $ {' '.join(cmd)}")
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


def _scan_log_tail(*, log_path: str, from_offset: int, markers: Iterable[str]) -> set[str]:
    """Return the subset of ``markers`` found in the file tail after ``from_offset``.

    Reading the tail (not the whole file) keeps the scan O(bytes-added)
    and side-steps log rotation — if the file got smaller in between
    (rotated), we just scan the whole new file.
    """
    path = Path(log_path)
    if not path.exists():
        return set()
    size = path.stat().st_size
    seek_to = from_offset if from_offset <= size else 0
    found: set[str] = set()
    markers_list = list(markers)
    with path.open("rb") as f:
        f.seek(seek_to)
        tail = f.read().decode(errors="replace")
    for marker in markers_list:
        if marker in tail:
            found.add(marker)
    return found


def _log_size(log_path: str) -> int:
    """File size at scan-baseline time; 0 when the log doesn't exist yet."""
    path = Path(log_path)
    return path.stat().st_size if path.exists() else 0


def _poll_for_markers(
    *,
    log_path: str,
    from_offset: int,
    expected: set[str],
    deadline_seconds: int,
) -> set[str]:
    """Re-scan the log tail until ``expected`` is found or the deadline hits.

    Same upper bound as a fixed sleep, but exits early once both
    markers are seen — keeps the smoke fast on a warm box and
    forgiving on a loaded one without inflating the cap.
    """
    deadline = time.monotonic() + deadline_seconds
    found: set[str] = set()
    while True:
        found = _scan_log_tail(
            log_path=log_path,
            from_offset=from_offset,
            markers=expected,
        )
        if expected <= found:
            return found
        if time.monotonic() >= deadline:
            return found
        time.sleep(POLL_INTERVAL_SECONDS)


async def _amain() -> int:
    args = _parse_args()
    async with AsyncSessionLocal() as db:
        repo = await _resolve_repo(db, args.repo_id)
        cluster_id = f"harness-c-{uuid.uuid4().hex[:8]}"
        pr_number = int(time.time()) % 1_000_000  # avoid clashing with real PR numbers
        base_sha = f"base{uuid.uuid4().hex[:32]}"[:40]
        head_sha = f"head{uuid.uuid4().hex[:32]}"[:40]
        print(f"Target repo:   {repo.github_repo_full_name} ({repo.id})")
        print(f"Synthetic PR:  #{pr_number}")
        print(f"Cluster id:    {cluster_id}")
        print(f"base/head SHA: {base_sha[:12]}.. / {head_sha[:12]}..")

        await _seed_clusters(
            db,
            org_id=repo.org_id,
            repo_id=repo.id,
            cluster_id=cluster_id,
            base_sha=base_sha,
            head_sha=head_sha,
            files=[args.changed_file, "src/sibling_unchanged.py"],
        )

        baseline_offset = _log_size(args.log_file)
        try:
            print("→ firing mock webhook…")
            rc = _fire_webhook(
                repo_id=repo.id,
                pr_number=pr_number,
                base_sha=base_sha,
                head_sha=head_sha,
                changed_files=[args.changed_file],
            )
            if rc != 0:
                print(f"{_RED}FAIL: mock_pr_webhook subprocess returned {rc}{_RESET}")
                return 1
            print(
                f"→ polling log tail for markers (up to {args.wait}s, "
                f"every {POLL_INTERVAL_SECONDS}s)…"
            )
            expected = {MARKER_DISPATCH, "pr_narrow_synthesis"}
            found = _poll_for_markers(
                log_path=args.log_file,
                from_offset=baseline_offset,
                expected=expected,
                deadline_seconds=args.wait,
            )
            missing = sorted(expected - found)
            if missing:
                print(f"{_RED}FAIL: log markers missing from tail:{_RESET} {missing}")
                print(f"   (log file: {args.log_file})")
                return 1
            print(f"{_GREEN}PASS:{_RESET} dispatcher logged '{MARKER_DISPATCH}'")
            print(f"{_GREEN}PASS:{_RESET} narrow synth job event seen in log tail")
            return 0
        finally:
            print("→ cleaning up seeded cluster_cache rows…")
            await _cleanup(db, repo_id=repo.id, cluster_id=cluster_id)


def main() -> int:
    """Sync entry point."""
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
