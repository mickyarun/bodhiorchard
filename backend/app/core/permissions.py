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

"""Permission definitions — the source of truth for Bodhiorchard RBAC.

This module defines every permission category and permission. The default
system-role-to-permission mapping lives in :mod:`app.core.role_defs`. The
seeder reads both to populate the database on startup.
"""

from app.core.permission_types import CategoryDef, PermissionDef
from app.core.permissions_people import PEOPLE_PERMISSION_CATEGORIES, WORKSPACE_ENGINEERING

# ---------------------------------------------------------------------------
# Permission categories and their permissions
# ---------------------------------------------------------------------------

_ENGINEERING_CATEGORIES: list[CategoryDef] = [
    CategoryDef(
        key="BACKLOG",
        name="Backlog Management",
        description="Permissions related to backlog items",
        permissions=[
            PermissionDef("backlog:view", "View Backlog Items"),
            PermissionDef("backlog:create", "Create Backlog Items"),
            PermissionDef("backlog:edit", "Edit Backlog Items"),
            PermissionDef("backlog:delete", "Delete Backlog Items"),
            PermissionDef("backlog:approve", "Approve Backlog Items"),
        ],
    ),
    CategoryDef(
        key="AGENTS",
        name="AI Agents",
        description="Permissions related to AI agent management",
        permissions=[
            PermissionDef("agents:view", "View Agents"),
            PermissionDef("agents:configure", "Configure Agents"),
            PermissionDef("agents:trigger", "Trigger Agent Runs"),
        ],
    ),
    CategoryDef(
        key="NODES",
        name="Execution Nodes",
        description="Permissions related to execution node management",
        permissions=[
            PermissionDef("nodes:view", "View Nodes"),
            PermissionDef("nodes:scan", "Scan for Nodes"),
            PermissionDef("nodes:approve", "Approve Nodes"),
            PermissionDef("nodes:install", "Install Nodes"),
        ],
    ),
    CategoryDef(
        key="BUDS",
        name="BUD Documents",
        description="Permissions related to Business Understanding Documents",
        permissions=[
            PermissionDef("buds:view", "View BUDs"),
            PermissionDef("buds:create", "Create BUDs"),
            PermissionDef("buds:edit", "Edit BUDs"),
            PermissionDef("buds:approve", "Approve BUD Phase Gates"),
            PermissionDef("buds:test", "Record QA Test Results and Evidence"),
        ],
    ),
    CategoryDef(
        key="BUGS",
        name="Bug Tracking",
        description="Permissions for the production bug board (Feature-linked) and bug comments",
        permissions=[
            PermissionDef("bugs:view", "View Bugs"),
            PermissionDef("bugs:report", "Report Bugs"),
            PermissionDef("bugs:edit", "Edit Bugs"),
            PermissionDef("bugs:assign", "Assign Bugs"),
            PermissionDef("bugs:comment", "Comment on Bugs"),
            PermissionDef("bugs:delete", "Delete (Soft-Delete) Bugs"),
        ],
    ),
    CategoryDef(
        key="TEAM",
        name="Team Management",
        description="Permissions related to team and user management",
        permissions=[
            PermissionDef("team:view", "View Team Members"),
            PermissionDef("team:invite", "Invite Team Members"),
            PermissionDef("team:remove", "Remove Team Members"),
            PermissionDef("team:assign_roles", "Assign Roles"),
            PermissionDef("team:manage", "Manage Teams"),
        ],
    ),
    CategoryDef(
        key="ORGANIZATION",
        name="Organization Settings",
        description="Permissions related to organization-level settings",
        permissions=[
            PermissionDef("org:view_settings", "View Organization Settings"),
            PermissionDef("org:edit_settings", "Edit Organization Settings"),
        ],
    ),
    CategoryDef(
        key="SETTINGS",
        name="Project Settings",
        description="Permissions for project-level settings (design systems, agent skills, repos)",
        permissions=[
            PermissionDef("settings:view", "View Project Settings"),
            PermissionDef("settings:edit", "Edit Project Settings"),
        ],
    ),
    CategoryDef(
        key="QUIZ",
        name="Company Quiz",
        description="Permissions for managing the Company Quiz Game",
        permissions=[
            # A standalone permission (NOT bundled into org/admin) so quiz
            # management can be granted to specific people via a custom role —
            # keeping it separate from anyone who plays and competes for SP.
            PermissionDef("quiz:configure", "Manage the Company Quiz (settings + review)"),
        ],
    ),
    CategoryDef(
        key="INTEGRATIONS",
        name="Integrations",
        description="Permissions related to third-party integrations",
        permissions=[
            PermissionDef("integrations:view", "View Integrations"),
            PermissionDef("integrations:configure", "Configure Integrations"),
        ],
    ),
    CategoryDef(
        key="KNOWLEDGE",
        name="Knowledge Base",
        description="Permissions related to the knowledge base",
        permissions=[
            PermissionDef("knowledge:view", "View Knowledge Items"),
            PermissionDef("knowledge:contribute", "Contribute Knowledge"),
            PermissionDef("knowledge:manage", "Manage Knowledge Base"),
        ],
    ),
    CategoryDef(
        key="REPORTS",
        name="Reports & Analytics",
        description="Permissions related to reports and analytics",
        permissions=[
            PermissionDef("reports:view", "View Reports"),
            PermissionDef("reports:export", "Export Reports"),
        ],
    ),
]

# People categories go last: ``display_order`` is only written when a row is
# first inserted, so inserting mid-list would leave existing rows out of order.
PERMISSION_CATEGORIES: list[CategoryDef] = [
    *_ENGINEERING_CATEGORIES,
    *PEOPLE_PERMISSION_CATEGORIES,
]

# Convenience: flat set of every resource_id
ALL_PERMISSION_IDS: set[str] = {
    p.resource_id for cat in PERMISSION_CATEGORIES for p in cat.permissions
}

__all__ = [
    "ALL_PERMISSION_IDS",
    "PERMISSION_CATEGORIES",
    "SENSITIVE_PERMISSION_IDS",
    "WORKSPACE_ENGINEERING",
    "CategoryDef",
    "PermissionDef",
    "expand_permission_specs",
]

SENSITIVE_PERMISSION_IDS: frozenset[str] = frozenset(
    p.resource_id for cat in PERMISSION_CATEGORIES for p in cat.permissions if p.sensitive
)


def expand_permission_specs(*specs: str) -> list[str]:
    """Expand shorthand permission specs into a flat list of resource_ids.

    Supports:
      - Exact ids:  ``"backlog:view"``
      - Wildcards:  ``"backlog:*"``  (all permissions in that resource)
      - Slash lists: ``"agents:view/trigger"``  (multiple actions)
    """
    result: list[str] = []
    for spec in specs:
        if spec == "*":
            result.extend(sorted(ALL_PERMISSION_IDS))
        elif spec.endswith(":*"):
            prefix = spec[:-1]  # e.g. "backlog:"
            result.extend(sorted(rid for rid in ALL_PERMISSION_IDS if rid.startswith(prefix)))
        elif "/" in spec:
            resource, actions = spec.split(":", 1)
            for action in actions.split("/"):
                result.append(f"{resource}:{action}")
        else:
            result.append(spec)
    return result
