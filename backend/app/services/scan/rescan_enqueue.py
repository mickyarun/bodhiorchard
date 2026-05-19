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

"""Operator-triggered rescan → synthetic Redis-stream delivery.

When an operator clicks "Rescan" on a repo that has already been scanned
at least once, we reuse the PR-merge engine instead of running the full
scan pipeline:

1. Resolve the remote head SHA via ``git ls-remote origin <main_branch>``
   — querying the remote rather than the local worktree keeps the
   payload honest even when the cached worktree is stale (the consumer's
   ``ensure_scan_test_worktree`` fetches+resets before indexing).
2. Insert a ``webhook_logs`` row with ``event_type='repo_scan'`` and
   the minimum replay payload the PR-merge dispatcher reads
   (``pr_number=0``, ``base_sha``, ``head_sha``, ``full_name``).
3. XADD onto the per-(org, repo) Redis stream
   (``pr-merge:{org}:{repo}``) so the PR-merge consumer picks it up
   FIFO with any in-flight webhook deliveries.

The dispatcher treats ``event_type='repo_scan'`` rows identically to
``pull_request`` rows — both branch on cluster-diff size into either
narrow synthesis (≤ ``NARROW_CAP`` affected clusters) or a full scan
trigger.
"""

from __future__ import annotations

import uuid

import structlog

from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.webhook_log import WebhookLogRepository
from app.scan.session import with_session
from app.services.git_operations import _detect_main_branch, run_git
from app.services.pr_merge_worker import publish_pr_merge_delivery

logger = structlog.get_logger(__name__)

EVENT_TYPE_REPO_SCAN = "repo_scan"
"""``webhook_logs.event_type`` value for synthetic rescan deliveries.

Distinct from ``pull_request`` so operator dashboards can filter
operator-triggered rescans from webhook-triggered merges; the consumer
dispatcher reads neither — it branches on payload fields alone.
"""


class RescanRepoNotFoundError(LookupError):
    """The repo can't be resolved for an enqueue request.

    Raised when ``repo_id`` doesn't exist for the org, or when the repo
    has no local ``path`` (so we can't run ``git ls-remote`` to resolve
    the head SHA). The API layer maps this to HTTP 404.
    """


class RescanHeadResolutionError(RuntimeError):
    """Remote head SHA resolution failed for the rescan target.

    ``git ls-remote origin <branch>`` returned non-zero or an empty
    result. Surfacing the failure to the caller is correct — without a
    head SHA the consumer's cluster diff has no anchor and would
    immediately fall back to full scan, defeating the rescan purpose.
    """


async def enqueue_rescan_delivery(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    trigger: str = "operator_button",
) -> str:
    """Build + publish a synthetic rescan delivery. Returns ``delivery_id``.

    The delivery_id uses a ``rescan-`` prefix so log greps can
    distinguish operator-triggered work from GitHub-delivered webhooks
    at a glance. The actual prefix has no semantic meaning to the
    consumer.
    """
    async with with_session(org_id) as db:
        repo = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
        if repo is None:
            raise RescanRepoNotFoundError(f"tracked repo {repo_id} not found for org {org_id}")
        if not repo.path:
            raise RescanRepoNotFoundError(
                f"tracked repo {repo_id} has no local path — cannot resolve head_sha"
            )
        base_sha = repo.head_sha or ""
        repo_path = repo.path
        configured_main_branch = repo.main_branch
        full_name = repo.name or ""

    main_branch = configured_main_branch or await _detect_main_branch(repo_path) or "main"
    head_sha = await _resolve_remote_head_sha(repo_path=repo_path, branch=main_branch)

    delivery_id = f"rescan-{uuid.uuid4()}"
    payload = {
        "pr_number": 0,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "full_name": full_name,
        "trigger": trigger,
    }
    payload_summary = {
        "trigger": trigger,
        "main_branch": main_branch,
        "base_sha": base_sha[:12] if base_sha else None,
        "head_sha": head_sha[:12],
    }

    async with with_session(org_id) as db:
        inserted = await WebhookLogRepository(db).record_replay_row(
            delivery_id=delivery_id,
            event_type=EVENT_TYPE_REPO_SCAN,
            org_id=org_id,
            repo_id=repo_id,
            payload=payload,
            payload_summary=payload_summary,
        )
        await db.commit()

    if not inserted:
        # uuid4 collision is structurally impossible; the only way this
        # branch fires is a clock-skew clone of an existing row. Log
        # and continue — publish_pr_merge_delivery is idempotent enough
        # that a stray duplicate XADD is harmless.
        logger.warning("rescan_delivery_id_collision", delivery_id=delivery_id)

    await publish_pr_merge_delivery(org_id=org_id, repo_id=repo_id, delivery_id=delivery_id)
    logger.info(
        "rescan_enqueued",
        org_id=str(org_id),
        repo_id=str(repo_id),
        delivery_id=delivery_id,
        base_sha=base_sha[:8] if base_sha else None,
        head_sha=head_sha[:8],
        trigger=trigger,
    )
    return delivery_id


async def _resolve_remote_head_sha(*, repo_path: str, branch: str) -> str:
    """Resolve the remote HEAD SHA for ``branch`` via ``git ls-remote``."""
    stdout, stderr, rc = await run_git(["ls-remote", "origin", branch], cwd=repo_path)
    if rc != 0 or not stdout.strip():
        raise RescanHeadResolutionError(
            f"git ls-remote origin {branch} failed (rc={rc}): {stderr[:200]}"
        )
    sha = stdout.split()[0].strip()
    if not sha:
        raise RescanHeadResolutionError(f"git ls-remote origin {branch} returned empty SHA")
    return sha
