"""Health check endpoint for liveness and readiness probes."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """Return application health status including database connectivity.

    Pings the database to verify the connection is alive.
    """
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "database": db_status,
    }
