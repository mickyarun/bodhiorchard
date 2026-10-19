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

"""Default system roles and their permission sets.

The seeder creates one SYSTEM row per :class:`RoleDef` and keeps its
permission mappings in sync (additions only).
"""

from dataclasses import dataclass, field

from app.core.permissions import WORKSPACE_ENGINEERING, expand_permission_specs


@dataclass(frozen=True)
class RoleDef:
    """A system role definition with its description and permission specs."""

    name: str
    description: str
    permission_specs: list[str] = field(default_factory=list)

    @property
    def permission_ids(self) -> list[str]:
        """Expanded list of resource_id strings."""
        return expand_permission_specs(*self.permission_specs)


DEFAULT_SYSTEM_ROLES: list[RoleDef] = [
    RoleDef(
        name="org_owner",
        description="Organization owner with full access",
        permission_specs=["*"],
    ),
    RoleDef(
        name="quiz_master",
        description="Runs the Company Quiz (configure + approve questions); assign to "
        "a non-competing member so admins can play fairly",
        permission_specs=[WORKSPACE_ENGINEERING, "quiz:configure"],
    ),
    RoleDef(
        name="admin",
        description="Administrator with nearly full access",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:*",
            "agents:*",
            "nodes:*",
            "buds:*",
            "bugs:*",
            "team:*",
            "org:*",
            "settings:*",
            "integrations:*",
            "knowledge:*",
            "reports:*",
            # Not ``leave:approve``: the approval queue shows leave reasons,
            # which stay with HR.
            "leave:configure",
            "employees:view",
        ],
    ),
    RoleDef(
        name="pm",
        description="Project manager",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:*",
            "buds:*",
            "bugs:*",
            "agents:view/trigger",
            "team:view",
            "settings:view",
            "knowledge:*",
            "reports:*",
        ],
    ),
    RoleDef(
        name="tech_lead",
        description="Technical lead",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:view/edit/approve",
            "agents:*",
            "nodes:*",
            "buds:view/approve",
            "bugs:view/edit/comment",
            "team:view",
            "settings:*",
            "knowledge:*",
            "reports:*",
        ],
    ),
    RoleDef(
        name="manager",
        description="Engineering manager",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:view/edit/approve",
            "buds:view/create/edit/approve",
            "bugs:*",
            "team:view/manage/assign_roles",
            "settings:view",
            "knowledge:view",
            "reports:*",
        ],
    ),
    RoleDef(
        name="developer",
        description="Software developer",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:view",
            "buds:view/edit",
            "bugs:view/report/edit/comment",
            "settings:view",
            "knowledge:view/contribute",
            "reports:view",
        ],
    ),
    RoleDef(
        name="designer",
        description="Product designer",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:view",
            "buds:view",
            "bugs:view/comment",
            "settings:view",
            "knowledge:view/contribute",
        ],
    ),
    RoleDef(
        name="qa",
        description="Quality assurance engineer",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:view/edit",
            "buds:view/test",
            # ``bugs:edit`` lets QA transition resolved → closed when
            # they validate the fix, per the methodology's quality-loop
            # description. Filing, commenting and closing are the QA
            # touchpoints on the production bug board.
            "bugs:view/report/edit/comment",
            "settings:view",
            "knowledge:view/contribute",
            "reports:view",
        ],
    ),
    RoleDef(
        name="support",
        description="Support team member",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:view/create",
            "bugs:view/report/comment",
            "knowledge:view",
        ],
    ),
    RoleDef(
        name="viewer",
        description="Read-only access",
        permission_specs=[
            WORKSPACE_ENGINEERING,
            "backlog:view",
            "buds:view",
            "bugs:view",
            "knowledge:view",
            "reports:view",
        ],
    ),
    RoleDef(
        name="hr",
        description="HR: approves leave, manages employee records and documents",
        permission_specs=["leave:*", "employees:*", "team:view", "team:invite"],
    ),
    RoleDef(
        name="sales",
        description="Sales team member: leave, WFH and their own employee details only",
        permission_specs=[],
    ),
]

# A custom role may not reuse a system role's name: the permission bypass
# and several UI checks key off role names, so a custom ``org_owner`` or
# ``hr`` would be confusing at best and an escalation path at worst.
RESERVED_ROLE_NAMES: frozenset[str] = frozenset(r.name for r in DEFAULT_SYSTEM_ROLES)

# Permissions of a member whose membership has no role yet (Slack import,
# GitHub stubs, an invite sent without a role). They are treated as
# developers until an admin picks a role; every resolver (HTTP, MCP,
# websocket, Slack recipients) reads this one definition.
UNASSIGNED_ROLE_NAME = "developer"
UNASSIGNED_MEMBER_PERMISSIONS: frozenset[str] = frozenset(
    next(r.permission_ids for r in DEFAULT_SYSTEM_ROLES if r.name == UNASSIGNED_ROLE_NAME)
)
