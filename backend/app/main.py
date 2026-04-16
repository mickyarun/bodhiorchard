"""Bodhigrove API application entry point."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.router import api_router
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware

# Configure structured JSON logging before anything else
setup_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    json_output=os.environ.get("LOG_FORMAT", "json") == "json",
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown events."""
    logger.info("bodhigrove_startup", version="0.1.0")

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

    # 6. Recover stuck agent tasks from prior crash/restart
    from app.repositories.bud_agent_task import recover_stuck_agent_tasks

    try:
        async with AsyncSessionLocal() as session:
            recovered = await recover_stuck_agent_tasks(session)
            await session.commit()
        if recovered:
            logger.info("recovered_stuck_agent_tasks", count=recovered)
    except Exception:
        logger.warning("agent_task_recovery_failed", exc_info=True)

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

    yield

    cleanup_task.cancel()
    presence_task.cancel()
    await stop_workers()

    from app.services.redis_client import close_redis

    await close_redis()
    logger.info("bodhigrove_shutdown")


app = FastAPI(
    title="Bodhigrove API",
    version="0.1.0",
    description="AI-powered software development platform",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(RequestLoggingMiddleware)
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
async def root() -> dict:
    """Root endpoint returning API identity and version."""
    return {"name": "Bodhigrove", "version": "0.1.0"}
