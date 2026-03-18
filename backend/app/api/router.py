"""Main API router that aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.claude import router as claude_router
from app.api.v1.organizations import router as orgs_router
from app.api.v1.prd import router as prd_router
from app.api.v1.roles import router as roles_router
from app.api.v1.setup import router as setup_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health")
api_router.include_router(setup_router, prefix="/api/setup")
api_router.include_router(auth_router, prefix="/api/v1/auth")
api_router.include_router(claude_router, prefix="/api/v1/claude")
api_router.include_router(orgs_router, prefix="/api/v1/organizations")
api_router.include_router(prd_router, prefix="/api/v1/prds")
api_router.include_router(roles_router, prefix="/api/v1")
