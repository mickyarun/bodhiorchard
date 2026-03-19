"""FlowDev API application entry point."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    logger.info("flowdev_startup", version="0.1.0")
    yield
    logger.info("flowdev_shutdown")


app = FastAPI(
    title="FlowDev API",
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
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict:
    """Root endpoint returning API identity and version."""
    return {"name": "FlowDev", "version": "0.1.0"}
