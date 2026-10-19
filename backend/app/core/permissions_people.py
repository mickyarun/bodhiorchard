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

"""Permission categories for the people workspace: leave, WFH and employee records.

Kept apart from the engineering registry in :mod:`app.core.permissions`,
which appends these categories last.
"""

from app.core.permission_types import CategoryDef, PermissionDef

# Gate for the whole engineering platform (BUDs, bugs, repos, garden, ...).
# People-only roles such as ``sales`` don't hold it.
WORKSPACE_ENGINEERING = "workspace:engineering"

PEOPLE_PERMISSION_CATEGORIES: list[CategoryDef] = [
    CategoryDef(
        key="WORKSPACE",
        name="Workspaces",
        description="Which parts of the platform a role can open",
        permissions=[
            PermissionDef(
                WORKSPACE_ENGINEERING,
                "Access Engineering Workspace",
                "BUDs, bugs, features, repos, agents and the garden",
                backfill_custom_roles=True,
            ),
        ],
    ),
    CategoryDef(
        key="LEAVE",
        name="Leave & WFH",
        description="Approving and configuring leave and work-from-home",
        permissions=[
            PermissionDef(
                "leave:approve",
                "Approve Any Leave Request",
                "Act on any pending request, including the HR queue. Sees leave reasons.",
                sensitive=True,
            ),
            PermissionDef(
                "leave:configure",
                "Configure Leave Policies",
                "Leave types, holidays, WFH rules, balance adjustments and the Slack post",
                sensitive=True,
            ),
        ],
    ),
    CategoryDef(
        key="EMPLOYEES",
        name="Employee Records",
        description="The employee directory and personal records",
        permissions=[
            PermissionDef("employees:view", "View Employee Directory", "Work details only"),
            PermissionDef(
                "employees:manage",
                "Manage Employee Records",
                "Edit profiles and see personal, bank and ID details",
                sensitive=True,
            ),
            PermissionDef(
                "employees:documents",
                "Manage Employee Documents",
                "View, upload and delete any employee's documents",
                sensitive=True,
            ),
        ],
    ),
]
