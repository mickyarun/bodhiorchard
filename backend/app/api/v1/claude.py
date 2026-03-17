"""Claude Code CLI endpoints for testing and running tasks."""

import structlog
from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    run_claude_code,
    test_claude_connection,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["claude"])


@router.get("/test")
async def test_claude(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Test Claude Code CLI availability and connectivity.

    Runs a simple prompt to verify the CLI is installed and the API key works.

    Args:
        current_user: The authenticated user.

    Returns:
        Test results including cli_available, test_passed, output.
    """
    return await test_claude_connection()


@router.post("/run")
async def run_claude_task(
    prompt: str,
    working_dir: str | None = None,
    max_turns: int = 20,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Trigger a Claude Code CLI task directly (for testing/development).

    Args:
        prompt: The prompt to send to Claude Code.
        working_dir: Optional working directory for codebase context.
        max_turns: Maximum number of agent turns.
        current_user: The authenticated user.

    Returns:
        The Claude Code execution result.
    """
    config = ClaudeRunnerConfig(max_turns=max_turns)
    result = await run_claude_code(
        prompt=prompt,
        working_dir=working_dir,
        config=config,
    )
    return {
        "success": result.success,
        "output": result.output,
        "cost_usd": result.cost_usd,
        "turns_used": result.turns_used,
        "error": result.error,
    }
