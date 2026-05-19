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

import re
import uuid

import structlog

from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.webhook_log import WebhookLogRepository
from app.scan.session import with_session
from app.services.git_operations import _detect_main_branch, run_git
from app.services.pr_merge_worker import publish_pr_merge_delivery

logger = structlog.get_logger(__name__)

# Accepts both classic 40-char SHA-1 and 64-char SHA-256 object IDs so
# git transitions on the remote don't silently break us. Anything else
# from ``git ls-remote`` (HTML banners, proxy errors, ``warning:``
# lines, ambiguous branch listings) is rejected before it reaches the
# dispatcher.
_GIT_SHA_RE = re.compile(r"\A[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")

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


class RescanDeliveryIdCollisionError(RuntimeError):
    """A freshly-generated ``rescan-{uuid4}`` delivery_id collided.

    Structurally impossible with uuid4. If it ever fires, something is
    badly wrong (clock-rewind cloning the same PRNG, or a corrupted
    ``webhook_logs`` row pinned at our prefix) — surfacing the failure
    is better than silently masking it as a no-op delivery the operator
    would never see complete.
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
    # Two separate sessions are intentional: ``git ls-remote`` can take
    # several seconds, and holding a Postgres transaction across the
    # network round-trip would needlessly pin a connection. The race
    # window between the two sessions (repo renamed/deleted by another
    # caller) is bounded by the seconds-long ls-remote — acceptable for
    # an operator-triggered rescan; the worst case is an orphan
    # ``webhook_logs`` row that orphan-recovery will replay and the
    # dispatcher will then no-op (``_load_repo_and_org`` returns None).
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
        # ``record_replay_row`` uses ``ON CONFLICT DO NOTHING`` — returning
        # False means the delivery_id already exists. With uuid4 this is
        # structurally impossible, so raise rather than silently masking:
        # if it ever fires, a stray duplicate row would create a no-op
        # delivery the operator would watch forever waiting for "done".
        logger.error("rescan_delivery_id_collision", delivery_id=delivery_id)
        raise RescanDeliveryIdCollisionError(f"webhook_logs already has a row for {delivery_id}")

    # Insert-then-publish ordering is load-bearing: if XADD fails after
    # commit, the durable row stays in ``pending`` status and the
    # boot-time orphan-recovery loop in ``pr_merge_worker.recover_orphans_at_startup``
    # re-publishes pending rows on the next backend start. The reverse
    # order would lose the delivery on a Redis outage between XADD and
    # commit.
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
    """Resolve the remote HEAD SHA for ``branch`` via ``git ls-remote``.

    Validates that the response is a single ``<sha>\\t<ref>`` line whose
    first token is a hex object ID. Refuses ambiguous matches (multiple
    refs come back when the branch name is a glob or matches multiple
    refs); refuses non-SHA tokens (HTML banners, proxy errors, etc.)
    that would otherwise flow into ``payload["head_sha"]`` and surface
    much later as a confusing indexer/git-checkout failure.
    """
    stdout, stderr, rc = await run_git(["ls-remote", "origin", branch], cwd=repo_path)
    if rc != 0 or not stdout.strip():
        raise RescanHeadResolutionError(
            f"git ls-remote origin {branch} failed (rc={rc}): {stderr[:200]}"
        )
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RescanHeadResolutionError(
            f"git ls-remote origin {branch} returned {len(lines)} refs "
            f"(expected exactly one): {stdout[:200]!r}"
        )
    sha = lines[0].split()[0].strip().lower()
    if not _GIT_SHA_RE.fullmatch(sha):
        raise RescanHeadResolutionError(
            f"git ls-remote origin {branch} returned non-SHA token: {sha[:80]!r}"
        )
    return sha
