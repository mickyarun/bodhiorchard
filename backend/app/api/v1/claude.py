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
