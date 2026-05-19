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

"""Bodhiorchard API application entry point."""
# (reload trigger — FT-5 fix verification)

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.router import api_router
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware
from app.services.pr_merge_worker import WorkerPool, start_pr_merge_workers
from app.services.scan.pr_merge_update import handle_pr_merge_delivery

# Configure structured JSON logging before anything else
setup_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    json_output=os.environ.get("LOG_FORMAT", "json") == "json",
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown events."""
    logger.info("bodhiorchard_startup", version="0.1.0")

    # 0. Static contract check: every MCP tool's schema ↔ handler must agree.
    # Catches the class of bug that once let `write_bud` silently clobber
    # BUDs because the schema said `content` and the handler read `content`
    # but Claude sent `requirements_md`. Hard-fails the boot with the exact
    # mismatch rather than shipping a silent data-loss regression.
    from app.mcp.contract_check import check_mcp_contracts

    check_mcp_contracts()

    # 0b. Register external event-bus transports. Every publish to a topic
    # like "agent_activity:<org_id>" fans out to the in-process queue
    # subscribers (dashboard WebSocket) AND to each registered transport.
    # Colyseus forwarding lives here so the multiplayer server sees every
    # agent event regardless of which handler raised it.
    from app.services.colyseus_forwarder import forward_agent_activity_to_colyseus
    from app.services.event_bus import register_transport

    register_transport(forward_agent_activity_to_colyseus)

    from app.services.job_handlers import setup_job_handlers
    from app.services.job_queue import cleanup_completed_jobs, start_workers, stop_workers

    # 1. Register all job types (handlers + worker counts)
    setup_job_handlers()

    # 2. Spawn workers for registered types
    await start_workers()

    # 3. Periodic cleanup of expired jobs
    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            removed = cleanup_completed_jobs()
            if removed:
                logger.debug("job_cleanup", removed=removed)

    cleanup_task = asyncio.create_task(_cleanup_loop())

    # 4. Sync system roles & permissions (idempotent — seeds new roles added to code)
    from app.database import AsyncSessionLocal
    from app.services.permission_seeder import seed_permissions

    try:
        async with AsyncSessionLocal() as session:
            await seed_permissions(session)
            await session.commit()
        logger.info("permission_seed_synced")
    except Exception:
        logger.warning("permission_seed_failed_at_startup")

    # 4b. Reconcile orphan scans. Any scan still in a non-terminal
    # status with no running task (i.e. updated_at older than 60s at
    # fresh-process boot) gets marked ``failed`` with a restart-hint
    # error so the frontend exits its polling loop and surfaces a
    # Resume button instead of waiting indefinitely for a coroutine
    # that was torn down mid-run.
    from app.services.scan_progress import reconcile_orphan_scans

    try:
        orphaned = await reconcile_orphan_scans()
        if orphaned:
            logger.info("scan_orphans_reconciled_at_startup", count=orphaned)
    except Exception:
        logger.warning("scan_orphan_reconcile_failed_at_startup", exc_info=True)

    # 5. Seed agent skills + BUD stage mappings for all orgs (idempotent)
    from app.models.organization import Organization
    from app.services.bud_stage_seeder import seed_stage_mappings_for_org
    from app.services.skill_loader import seed_skills_for_org

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Organization))
            for org in result.scalars().all():
                await seed_skills_for_org(org.id, session)
                await seed_stage_mappings_for_org(org.id, session)
            await session.commit()
        logger.info("agent_skills_seeded")
    except Exception:
        logger.warning("agent_skills_seed_failed_at_startup", exc_info=True)

    # 5b. Apply the configured org's Claude API key to os.environ so every
    # subsequent `claude` subprocess inherits it. No-op when auth_mode=host.
    from sqlalchemy.exc import SQLAlchemyError

    from app.services.claude_env import load_claude_env_at_startup

    try:
        async with AsyncSessionLocal() as session:
            await load_claude_env_at_startup(session)
    except (SQLAlchemyError, OSError):
        # Specific failure modes: the DB isn't reachable yet, or the
        # Fernet decrypt blew up. Broader exceptions should propagate.
        logger.warning("claude_env_load_failed_at_startup", exc_info=True)

    # 6. Recover stuck agent tasks from prior crash/restart
    from app.repositories.bud import recover_stuck_designs
    from app.repositories.bud_agent_task import recover_stuck_agent_tasks
    from app.repositories.bud_section_session import recover_stuck_chats

    try:
        async with AsyncSessionLocal() as session:
            recovered = await recover_stuck_agent_tasks(session)
            # Sister recovery: agent-task flip alone leaves ``bud_designs``
            # rows stuck at ``generating`` with dead ``job_id`` values from
            # the prior process. The frontend tracker polls those job ids,
            # gets 404, fires onError → loadDesigns → re-tracker → loop.
            # Flip the orphan design rows here so the next page load sees
            # them as ``failed`` and the user can retry cleanly.
            recovered_designs = await recover_stuck_designs(session)
            # Same shape for the AI Editor chat: any ``bud_section_sessions``
            # row whose ``active_job_id`` survived the restart points at a
            # dead job. Sweep persists an "interrupted" AI marker into
            # ``bud_chat_messages`` so the thread reads cleanly on the
            # next mount, then clears the pointer so the next POST /chat
            # can claim the section without hitting 409.
            recovered_chats = await recover_stuck_chats(session)
            await session.commit()
        if recovered:
            logger.info("recovered_stuck_agent_tasks", count=recovered)
        if recovered_designs:
            logger.info("recovered_stuck_designs", count=recovered_designs)
        if recovered_chats:
            logger.info("recovered_stuck_chats", count=recovered_chats)
    except Exception:
        logger.warning("agent_task_recovery_failed", exc_info=True)

    # 6a. Recover orphan phase workers (assignment / todo / estimation).
    # Sister to step 6: synthetic skills don't have BUDAgentTask rows, so
    # this scans AgentActivityLog for skill_invoked entries with no
    # matching terminal event and emits skill_failed for each — clears the
    # progress banner on any open session and stops re-attachment on
    # fresh mounts via active_phase_worker.
    from app.services.agent_activity_logger import reconcile_orphan_phase_workers

    try:
        async with AsyncSessionLocal() as session:
            recovered_phases = await reconcile_orphan_phase_workers(session)
        # Always log — without this you can't tell from the startup
        # output whether recovery actually ran or silently skipped. The
        # ``count`` lets you confirm the orphan-cancellation pipeline
        # against a live scenario.
        logger.info("phase_worker_recovery_complete", count=recovered_phases)
    except Exception:
        logger.warning("phase_worker_recovery_failed", exc_info=True)

    # 6b. Recover stuck Jira import sessions from prior crash/restart
    from app.repositories.jira_import import recover_stuck_import_sessions

    try:
        async with AsyncSessionLocal() as session:
            recovered = await recover_stuck_import_sessions(session)
            await session.commit()
        if recovered:
            logger.info("recovered_stuck_import_sessions", count=recovered)
    except Exception:
        logger.warning("import_session_recovery_failed", exc_info=True)

    # 7. Periodic Slack presence polling
    from app.services.presence_cache import refresh_all_presence

    async def _presence_poll_loop() -> None:
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    await refresh_all_presence(session)
            except Exception:
                logger.warning("presence_poll_failed")
            await asyncio.sleep(180)  # 3 minutes

    presence_task = asyncio.create_task(_presence_poll_loop())

    # 8. Warm the fastembed ONNX model in the background. The first real
    # embed call otherwise pays a ~10s import + model-load cost which, on
    # uvicorn --reload dev loops, stalls every concurrent API request at
    # the start of each worker lifetime. Fire-and-forget: the task finishes
    # within ~10s and subsequent embed_batch calls find the model ready.
    from app.services.embedding_service import embedding_service

    async def _warm_embedding_model() -> None:
        try:
            await embedding_service.warm()
            logger.info("embedding_model_warmed")
        except Exception:
            logger.warning("embedding_model_warmup_failed", exc_info=True)

    embedding_warmup_task = asyncio.create_task(_warm_embedding_model())

    # 8a. Daily retention sweep for the MCP audit log. Single-instance:
    # if Bodhiorchard grows multi-pod we'll move this behind a Redis lock
    # so duplicate deletes don't race across pods.
    from app.services.mcp_audit_cleanup import run_forever as run_audit_cleanup

    mcp_audit_cleanup_task = asyncio.create_task(run_audit_cleanup())

    # 9. PR-merge Redis-stream worker pool. One consumer per
    # (org, repo) stream; supervisor task spawns consumers lazily as
    # streams appear in the registry. Orphan recovery re-publishes
    # ``running`` (mid-handler crash) and ``pending`` (XADD lost) rows
    # before the supervisor starts so the new process picks them up
    # cleanly. Returns ``None`` and skips silently when Redis is
    # unreachable — the backend still boots and the next start, once
    # Redis is healthy, recovers everything via the orphan path.
    pr_merge_pool: WorkerPool | None = None
    try:
        pr_merge_pool = await start_pr_merge_workers(handler=handle_pr_merge_delivery)
    except Exception:
        logger.warning("pr_merge_worker_start_failed", exc_info=True)

    yield

    cleanup_task.cancel()
    presence_task.cancel()
    embedding_warmup_task.cancel()
    mcp_audit_cleanup_task.cancel()
    if pr_merge_pool is not None:
        await pr_merge_pool.stop()
    await stop_workers()

    from app.services.redis_client import close_redis

    await close_redis()
    logger.info("bodhiorchard_shutdown")


app = FastAPI(
    title="Bodhiorchard API",
    version="0.1.0",
    description="AI-powered software development platform",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(RequestLoggingMiddleware)


# Defence-in-depth: strip every CORS header from /mcp/* responses, and
# fast-fail browser preflight (OPTIONS) for those paths. MCP clients are
# desktop apps (Claude Desktop, Cursor, Continue) — they never send a
# preflight and never need Access-Control-Allow-* headers. Removing them
# means even if someone later widens the wildcard CORSMiddleware, no
# browser can ever talk credentialed CORS to /mcp/. Added BEFORE the
# CORSMiddleware so its post-processing runs AFTER (Starlette wraps
# in reverse-add order).
@app.middleware("http")
async def block_cors_on_mcp(request: Any, call_next: Any) -> Any:
    is_mcp_path = request.url.path.startswith("/mcp/") or request.url.path == "/mcp"
    if is_mcp_path and request.method == "OPTIONS":
        from fastapi import Response

        # Pretend the route doesn't accept browser preflight. No CORS
        # headers, no body. Browsers will refuse the actual request.
        return Response(status_code=403, content=b"")
    response = await call_next(request)
    if is_mcp_path:
        for header in (
            "access-control-allow-origin",
            "access-control-allow-credentials",
            "access-control-allow-methods",
            "access-control-allow-headers",
            "access-control-expose-headers",
            "access-control-max-age",
        ):
            response.headers.pop(header, None)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Design-Job-Id"],
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint returning API identity and version."""
    return {"name": "Bodhiorchard", "version": "0.1.0"}
