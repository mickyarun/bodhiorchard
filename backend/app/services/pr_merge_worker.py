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

"""PR-merge worker: one Redis Streams consumer per ``(org, repo)``.

Why this exists
---------------

Phase 4 used a Postgres-advisory-lock + in-memory job queue +
lock-lifecycle-wrapper stack to coordinate PR-merge deliveries. End-to-
end tests against real GitHub webhooks surfaced a lock-handoff race
between the dispatcher and the narrow-synth follow-up job. Phase 5
replaces that surface with **one Redis stream per (org, repo)
consumed by exactly one asyncio task** — FIFO by construction, no
locks, no defer dance.

Topology
--------

* Stream key: ``pr-merge:{org_id}:{repo_id}``.
* Registry set: ``pr-merge:streams`` (members are
  ``"{org_id}:{repo_id}"``). The webhook entry point SADDs on every
  delivery; the supervisor task reads this set to discover which
  streams need a consumer.
* Consumer group: ``workers``. One consumer per stream
  (``consumername="primary"``).
* Message body: ``{"delivery_id": "<uuid>"}``. The replay payload
  lives in Postgres (``webhook_logs.payload``); the stream carries
  only the routing handle.

State machine (worker is the sole writer of ``webhook_logs.status``)
---------------------------------------------------------------------

::

    pending  ──XREADGROUP──►  running  ──handler ok──►  done
                                  │
                                  └──handler raises──►  failed

``skipped`` rows (install events / untracked repos) are inserted
directly by the webhook entry point and never reach the stream.

Crash recovery
--------------

:func:`recover_orphans_at_startup` lists rows in ``running`` and
``pending`` status at boot. A ``running`` orphan means the previous
backend died mid-handler, so we re-XADD to its stream and let the
fresh worker pick up. A ``pending`` orphan means the webhook entry
point successfully recorded the row but the XADD never landed (or
landed and was lost) — same recovery path. Either way the row gets
exactly one fresh attempt under the new process.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

import structlog
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.database import AsyncSessionLocal
from app.models.webhook_log import WebhookDeliveryStatus, WebhookLog
from app.repositories.webhook_log import WebhookLogRepository
from app.services.redis_client import get_redis

logger = structlog.get_logger(__name__)


# --- Naming -----------------------------------------------------------------

STREAM_KEY_PREFIX = "pr-merge"
"""Stream key format: ``pr-merge:{org_id}:{repo_id}``."""

REGISTRY_KEY = "pr-merge:streams"
"""SET of ``"{org_id}:{repo_id}"`` members — one per stream that has
ever been XADDed to. Membership is the lookup channel the supervisor
uses to spawn consumers.
"""

CONSUMER_GROUP = "workers"
"""Single consumer group name — only one group per stream is needed
because the per-(org, repo) FIFO property depends on a single
consumer reading from the stream."""

CONSUMER_NAME = "primary"
"""Single consumer name within the group. If we ever need parallelism
within a single repo's stream, this is the knob to turn — but Phase 5
is intentionally serial-per-repo."""

XADD_FIELD_DELIVERY_ID = "delivery_id"
"""The only field carried in the stream message body. Replay payload
lives in Postgres, not the message."""


# --- Tunables ---------------------------------------------------------------

# Block on XREADGROUP for this many ms before checking the stop event.
# Shorter = faster shutdown; longer = less Redis traffic at idle. A
# few seconds is the sweet spot — backend shutdown isn't latency-
# critical and Redis idle-traffic at this rate is negligible.
XREAD_BLOCK_MS = 5000

# Supervisor polls the registry at this cadence. New streams (first
# webhook for a never-seen-before (org, repo)) take this long to spawn
# a consumer. 2s is well below the webhook→merge-decision latency
# floor.
SUPERVISOR_POLL_SECONDS = 2.0

# Sleep after an unhandled supervisor error before retrying so a
# misbehaving Redis doesn't spin the loop.
SUPERVISOR_ERROR_BACKOFF_SECONDS = 15.0

# Per-status cap for orphan recovery at boot. Hit on a healthy system
# means something is wrong (handler stuck, Redis offline for an
# extended window) — the cap keeps boot bounded; the WARN log surfaces
# the saturation.
ORPHAN_BATCH_LIMIT = 500


# --- Stream-key helpers -----------------------------------------------------


def stream_key(org_id: uuid.UUID, repo_id: uuid.UUID) -> str:
    """Build the per-(org, repo) stream key."""
    return f"{STREAM_KEY_PREFIX}:{org_id}:{repo_id}"


def _registry_member(org_id: uuid.UUID, repo_id: uuid.UUID) -> str:
    """Build the registry-set member string."""
    return f"{org_id}:{repo_id}"


def _parse_registry_member(member: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Reverse :func:`_registry_member`. Returns ``None`` on malformed input.

    A corrupted registry entry shouldn't tank the supervisor; log + skip.
    """
    try:
        org_part, repo_part = member.split(":", 1)
        return uuid.UUID(org_part), uuid.UUID(repo_part)
    except (ValueError, AttributeError):
        return None


# --- Producer-side helper ---------------------------------------------------


async def publish_pr_merge_delivery(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    delivery_id: str,
) -> bool:
    """XADD a delivery onto the per-(org, repo) stream + register it.

    Returns ``True`` on success, ``False`` when Redis is unreachable
    (the webhook entry point logs + skips; the orphan-recovery path
    will pick the row up on the next boot when Redis is healthy
    again).

    Pipelined so the SADD and XADD are atomic-ish — either both land
    or neither does, which keeps the registry consistent with what's
    actually been written.
    """
    redis = await get_redis()
    if redis is None:
        logger.warning("pr_merge_publish_skipped_no_redis", delivery_id=delivery_id)
        return False
    key = stream_key(org_id, repo_id)
    member = _registry_member(org_id, repo_id)
    async with cast(Any, redis).pipeline(transaction=False) as pipe:
        pipe.sadd(REGISTRY_KEY, member)
        pipe.xadd(key, {XADD_FIELD_DELIVERY_ID: delivery_id})
        await pipe.execute()
    logger.info(
        "pr_merge_publish",
        stream=key,
        delivery_id=delivery_id,
    )
    return True


# --- Worker -----------------------------------------------------------------


# Handler type — handle_pr_merge_delivery(delivery_id) -> None. Lives
# behind a callable param so tests can inject a stub without monkey-
# patching imports.
DeliveryHandler = Callable[[str], Awaitable[None]]


@dataclass
class WorkerPool:
    """Handle to the running worker pool. Returned from
    :func:`start_pr_merge_workers` so the lifespan can stop it on
    shutdown.
    """

    stop_event: asyncio.Event
    supervisor_task: asyncio.Task[None]
    consumers: dict[str, asyncio.Task[None]]

    async def stop(self, timeout: float = 10.0) -> None:
        """Signal shutdown and drain in-flight tasks."""
        self.stop_event.set()
        tasks = [self.supervisor_task, *self.consumers.values()]
        if not tasks:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            for t in tasks:
                if not t.done():
                    t.cancel()
            logger.warning("pr_merge_worker_pool_shutdown_timeout")


async def start_pr_merge_workers(
    *,
    handler: DeliveryHandler,
) -> WorkerPool | None:
    """Start the supervisor + consumer pool. Idempotent on Redis loss.

    Returns ``None`` when Redis is unreachable at startup — the backend
    still boots (PR-merge work is offline until Redis comes back; the
    orphan-recovery path catches up on the next start once it does).

    Steps:
      1. Recover orphans — list ``running`` + ``pending`` rows and
         re-XADD them to their respective streams.
      2. Spawn the supervisor task that polls the registry and spawns
         one consumer per stream.
    """
    redis = await get_redis()
    if redis is None:
        logger.warning("pr_merge_worker_start_skipped_no_redis")
        return None

    stop = asyncio.Event()
    consumers: dict[str, asyncio.Task[None]] = {}

    try:
        recovered = await recover_orphans_at_startup(redis=redis)
        if recovered:
            logger.info("pr_merge_worker_orphans_recovered", count=recovered)
    except Exception:
        logger.exception("pr_merge_worker_orphan_recovery_failed")

    supervisor = asyncio.create_task(
        _supervise(redis=redis, handler=handler, stop=stop, consumers=consumers),
        name="pr-merge-supervisor",
    )
    logger.info("pr_merge_worker_started")
    return WorkerPool(stop_event=stop, supervisor_task=supervisor, consumers=consumers)


async def recover_orphans_at_startup(*, redis: Redis) -> int:
    """Re-publish PR-merge rows stuck in ``running`` or ``pending``.

    Two orphan classes:

    * ``running`` — backend died mid-handler. The Redis-stream XACK
      may or may not have happened. Re-XADDing is safe: even if the
      ACK did land, the new message gets a new ID and the consumer
      will see it as a fresh delivery. Idempotency belongs upstream
      (the WebhookLog row is the canonical state — re-running the
      handler at the same merge SHA is idempotent at the feature-
      reconcile level).
    * ``pending`` — the webhook entry recorded the row but the XADD
      either never executed (Redis was down at write time) or was
      lost (Redis crashed before persisting). Re-publish so the
      consumer picks it up.

    Returns the number of rows republished (for log telemetry).
    """
    async with AsyncSessionLocal() as db:
        repo = WebhookLogRepository(db)
        running_rows = await repo.list_in_status(WebhookDeliveryStatus.RUNNING)
        pending_rows = await repo.list_in_status(WebhookDeliveryStatus.PENDING)

    # ``list_in_status`` caps each set at 500 rows. After a long outage
    # we may have more orphans than the cap; surfacing the saturation
    # at WARN lets operators see "this boot didn't drain everything"
    # without having to count rows by hand. Subsequent boots make
    # progress one batch at a time.
    if len(running_rows) >= ORPHAN_BATCH_LIMIT or len(pending_rows) >= ORPHAN_BATCH_LIMIT:
        logger.warning(
            "pr_merge_orphan_recovery_batch_capped",
            running=len(running_rows),
            pending=len(pending_rows),
            cap=ORPHAN_BATCH_LIMIT,
            hint="more orphans remain — they'll be picked up on the next boot",
        )

    republished = 0
    for row in (*running_rows, *pending_rows):
        if row.repo_id is None or row.payload is None:
            # Unreplayable — no stream to publish to. Flip to FAILED so
            # the row doesn't loop through the recovery path on every
            # boot.
            await _mark_unreplayable_failed(row)
            continue
        ok = await _republish_orphan(redis=redis, row=row)
        if ok:
            republished += 1
    return republished


async def _republish_orphan(*, redis: Redis, row: WebhookLog) -> bool:
    """Re-XADD one orphan row to its stream + ensure registry membership.

    Returns ``True`` on success.
    """
    if row.repo_id is None:
        return False
    key = stream_key(row.org_id, row.repo_id)
    member = _registry_member(row.org_id, row.repo_id)
    try:
        async with cast(Any, redis).pipeline(transaction=False) as pipe:
            pipe.sadd(REGISTRY_KEY, member)
            pipe.xadd(key, {XADD_FIELD_DELIVERY_ID: row.delivery_id})
            await pipe.execute()
    except Exception:
        logger.exception(
            "pr_merge_orphan_republish_failed",
            delivery_id=row.delivery_id,
            stream=key,
        )
        return False
    logger.info(
        "pr_merge_orphan_republished",
        delivery_id=row.delivery_id,
        stream=key,
        prior_status=row.status.value,
    )
    return True


async def _mark_unreplayable_failed(row: WebhookLog) -> None:
    """Flip an orphan with no repo_id/payload to ``failed`` permanently."""
    async with AsyncSessionLocal() as db:
        await WebhookLogRepository(db).update_status(
            delivery_id=row.delivery_id,
            status=WebhookDeliveryStatus.FAILED,
            error="orphan: missing repo_id or payload at recovery",
        )
        await db.commit()


# --- Supervisor + consumer ---------------------------------------------------


async def _supervise(
    *,
    redis: Redis,
    handler: DeliveryHandler,
    stop: asyncio.Event,
    consumers: dict[str, asyncio.Task[None]],
) -> None:
    """Poll the registry; spawn one consumer task per stream.

    Idempotent — only spawns a consumer for a stream that doesn't
    already have a live task. Finished/cancelled tasks are GC'd from
    the dict on the next tick.
    """
    logger.info("pr_merge_supervisor_started", poll_s=SUPERVISOR_POLL_SECONDS)
    while not stop.is_set():
        try:
            members = await cast(Any, redis).smembers(REGISTRY_KEY)
            _reap_finished_consumers(consumers)
            for member in members:
                if member in consumers:
                    continue
                parsed = _parse_registry_member(member)
                if parsed is None:
                    logger.warning("pr_merge_supervisor_bad_registry_member", member=member)
                    continue
                org_id, repo_id = parsed
                consumers[member] = asyncio.create_task(
                    _consume_stream(
                        redis=redis,
                        handler=handler,
                        stop=stop,
                        org_id=org_id,
                        repo_id=repo_id,
                    ),
                    name=f"pr-merge-consumer:{member}",
                )
                logger.info("pr_merge_consumer_spawned", member=member)
        except Exception:
            logger.exception("pr_merge_supervisor_tick_failed")
            await _interruptible_sleep(stop, SUPERVISOR_ERROR_BACKOFF_SECONDS)
            continue
        await _interruptible_sleep(stop, SUPERVISOR_POLL_SECONDS)
    logger.info("pr_merge_supervisor_stopped")


def _reap_finished_consumers(consumers: dict[str, asyncio.Task[None]]) -> None:
    """Drop tasks that have ended so the next supervisor tick can respawn."""
    dead = [k for k, t in consumers.items() if t.done()]
    for k in dead:
        del consumers[k]


async def _consume_stream(
    *,
    redis: Redis,
    handler: DeliveryHandler,
    stop: asyncio.Event,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    """One consumer task per (org, repo) stream.

    Loops XREADGROUP until ``stop`` is set. Each message triggers the
    full lifecycle:

      1. Flip row to ``running`` (sole writer is this worker).
      2. Call ``handler(delivery_id)``.
      3. Flip row to ``done`` (or ``failed`` on exception).
      4. XACK regardless of success — failures are surfaced in
         Postgres, not in Redis. We do NOT re-process a failed message
         (single-attempt policy, matches Phase 4); operators re-queue
         by flipping the row back to ``pending`` and the orphan-
         recovery path catches it on the next boot.
    """
    key = stream_key(org_id, repo_id)
    await _ensure_group(redis=redis, key=key)
    logger.info(
        "pr_merge_consumer_started",
        stream=key,
        consumer=CONSUMER_NAME,
        group=CONSUMER_GROUP,
    )
    while not stop.is_set():
        try:
            entries = await cast(Any, redis).xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={key: ">"},
                count=1,
                block=XREAD_BLOCK_MS,
            )
        except Exception:
            logger.exception("pr_merge_consumer_xread_failed", stream=key)
            await _interruptible_sleep(stop, 5.0)
            continue
        if not entries:
            continue
        for _stream_key, messages in entries:
            for message_id, fields in messages:
                await _process_message(
                    redis=redis,
                    handler=handler,
                    stream=key,
                    message_id=message_id,
                    fields=fields,
                )
    logger.info("pr_merge_consumer_stopped", stream=key)


async def _ensure_group(*, redis: Redis, key: str) -> None:
    """Create the consumer group + stream if missing.

    ``mkstream=True`` creates the stream as a side-effect, so the
    consumer can start polling even before the first XADD lands. Race
    on group creation is benign — Redis returns ``BUSYGROUP`` and we
    swallow it.
    """
    try:
        await cast(Any, redis).xgroup_create(
            name=key, groupname=CONSUMER_GROUP, id="0", mkstream=True
        )
        logger.info("pr_merge_group_created", stream=key, group=CONSUMER_GROUP)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _process_message(
    *,
    redis: Redis,
    handler: DeliveryHandler,
    stream: str,
    message_id: str,
    fields: dict[str, Any],
) -> None:
    """Drive one delivery through the status state machine.

    The handler raises on irrecoverable failures; we catch broadly
    here because suppressing the exception inside the consumer is the
    *correct* behaviour — the WebhookLog row already carries the
    failure, and re-raising would tank the per-(org, repo) consumer
    task and leave subsequent deliveries for the same repo stuck.
    """
    delivery_id = fields.get(XADD_FIELD_DELIVERY_ID)
    if not delivery_id:
        logger.warning(
            "pr_merge_message_missing_delivery_id",
            stream=stream,
            message_id=message_id,
            fields_json=json.dumps(fields, default=str),
        )
        await _ack(redis=redis, stream=stream, message_id=message_id)
        return

    try:
        await _set_status(delivery_id, WebhookDeliveryStatus.RUNNING, bump_attempts=True)
        await handler(delivery_id)
        await _set_status(delivery_id, WebhookDeliveryStatus.DONE)
        logger.info(
            "pr_merge_message_processed",
            stream=stream,
            delivery_id=delivery_id,
            message_id=message_id,
        )
    except Exception as exc:
        logger.exception(
            "pr_merge_message_failed",
            stream=stream,
            delivery_id=delivery_id,
            message_id=message_id,
        )
        try:
            await _set_status(
                delivery_id,
                WebhookDeliveryStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            # DB write itself failed; the orphan-recovery path will
            # re-publish the row next boot. Don't let this kill the
            # consumer.
            logger.exception(
                "pr_merge_message_status_write_failed",
                delivery_id=delivery_id,
            )
    finally:
        await _ack(redis=redis, stream=stream, message_id=message_id)


async def _ack(*, redis: Redis, stream: str, message_id: str) -> None:
    """XACK a single message, swallowing transient Redis errors.

    A failed ACK leaves the message in the consumer's PEL — the orphan-
    recovery path doesn't read the PEL today, so a missed ACK would
    *not* re-deliver. That's fine: the Postgres row carries the result
    and the next webhook for the same repo will move things forward.
    A future enhancement could add XAUTOCLAIM for PEL-based recovery
    if we ever need it.
    """
    try:
        await cast(Any, redis).xack(stream, CONSUMER_GROUP, message_id)
    except Exception:
        logger.exception("pr_merge_xack_failed", stream=stream, message_id=message_id)


async def _set_status(
    delivery_id: str,
    status: WebhookDeliveryStatus,
    *,
    error: str | None = None,
    bump_attempts: bool = False,
) -> None:
    """Single-row status flip in its own short-lived session."""
    async with AsyncSessionLocal() as db:
        await WebhookLogRepository(db).update_status(
            delivery_id=delivery_id,
            status=status,
            error=error,
            bump_attempts=bump_attempts,
        )
        await db.commit()


async def _interruptible_sleep(stop: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds`` or until ``stop`` is set (whichever first)."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        return
