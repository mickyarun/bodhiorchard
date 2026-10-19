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

"""AI-facing code must never import people data (leave, employee records).

MCP tools and agent runs act on content from repos, Jira and Slack, which
can carry prompt injection. Keeping HR modules out of their import graph
means a manipulated agent has no code path to leave reasons or employee
records, whatever permissions the calling token has.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
AI_PACKAGES = ("mcp", "agents")
FORBIDDEN_PARTS = ("employee", "leave")


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def _touches_people_data(module: str) -> bool:
    if not module.startswith("app."):
        return False
    leaf_parts = module.split(".")[2:]  # skip "app.<layer>"
    return any(part.startswith(FORBIDDEN_PARTS) for part in leaf_parts)


def test_ai_packages_do_not_import_people_modules() -> None:
    offenders = []
    for package in AI_PACKAGES:
        for path in (APP / package).rglob("*.py"):
            offenders.extend(
                f"{path.relative_to(APP)} imports {module}"
                for module in _imported_modules(path)
                if _touches_people_data(module)
            )
    assert offenders == []


def test_detector_flags_people_modules() -> None:
    assert _touches_people_data("app.repositories.leave_request")
    assert _touches_people_data("app.models.employee_profile")
    assert not _touches_people_data("app.repositories.bud")
