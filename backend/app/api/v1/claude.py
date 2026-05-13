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

"""Claude Code CLI connectivity endpoint.

Production agent flows go through typed service functions
(``job_design``, ``bud_agent_handler``, ``scan/synthesis``), not via
HTTP. The single endpoint here is a read-only smoke test for the CLI
install. The previous ``/run`` endpoint accepted an arbitrary prompt
+ ``max_turns`` from any authenticated caller and had zero in-repo
callers; it was deleted to remove the attack surface (an authenticated
tenant could otherwise spend API credits driving the agent in the
backend's working directory).
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.services.claude_runner import test_claude_connection

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["claude"])


@router.get("/test")
async def test_claude(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Test Claude Code CLI availability and connectivity.

    Runs a simple prompt to verify the CLI is installed and the API key works.
    No user input flows into the subprocess.

    Args:
        current_user: The authenticated user.

    Returns:
        Test results including cli_available, test_passed, output.
    """
    return await test_claude_connection()
