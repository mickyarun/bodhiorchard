"""Permission definitions and default role mappings — the source of truth for FlowDev RBAC.

This module defines every permission category, permission, and the default
system-role-to-permission mapping.  The seeder reads this config to populate the
database on first setup.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionDef:
    """A single permission definition."""

    resource_id: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class CategoryDef:
    """A permission category with its child permissions."""

    key: str
    name: str
    description: str = ""
    permissions: list[PermissionDef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Permission categories and their permissions
# ---------------------------------------------------------------------------

PERMISSION_CATEGORIES: list[CategoryDef] = [
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
        key="PRDS",
        name="PRD Documents",
        description="Permissions related to product requirement documents",
        permissions=[
            PermissionDef("prds:view", "View PRDs"),
            PermissionDef("prds:create", "Create PRDs"),
            PermissionDef("prds:edit", "Edit PRDs"),
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

# Convenience: flat set of every resource_id
ALL_PERMISSION_IDS: set[str] = {
    p.resource_id for cat in PERMISSION_CATEGORIES for p in cat.permissions
}


def _expand(*specs: str) -> list[str]:
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


# ---------------------------------------------------------------------------
# Default system roles and their permission sets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleDef:
    """A system role definition with its description and permission specs."""

    name: str
    description: str
    permission_specs: list[str] = field(default_factory=list)

    @property
    def permission_ids(self) -> list[str]:
        """Expanded list of resource_id strings."""
        return _expand(*self.permission_specs)


DEFAULT_SYSTEM_ROLES: list[RoleDef] = [
    RoleDef(
        name="org_owner",
        description="Organization owner with full access",
        permission_specs=["*"],
    ),
    RoleDef(
        name="admin",
        description="Administrator with nearly full access",
        permission_specs=[
            "backlog:*",
            "agents:*",
            "nodes:*",
            "prds:*",
            "team:*",
            "org:view_settings",
            "integrations:*",
            "knowledge:*",
            "reports:*",
        ],
    ),
    RoleDef(
        name="pm",
        description="Project manager",
        permission_specs=[
            "backlog:*",
            "prds:*",
            "agents:view/trigger",
            "team:view",
            "knowledge:*",
            "reports:*",
            "integrations:view",
        ],
    ),
    RoleDef(
        name="tech_lead",
        description="Technical lead",
        permission_specs=[
            "backlog:view/edit",
            "agents:*",
            "nodes:*",
            "prds:view",
            "team:view",
            "knowledge:*",
            "reports:*",
        ],
    ),
    RoleDef(
        name="developer",
        description="Software developer",
        permission_specs=[
            "backlog:view",
            "prds:view",
            "knowledge:view/contribute",
            "reports:view",
        ],
    ),
    RoleDef(
        name="designer",
        description="Product designer",
        permission_specs=[
            "backlog:view",
            "prds:view",
            "knowledge:view/contribute",
        ],
    ),
    RoleDef(
        name="qa",
        description="Quality assurance engineer",
        permission_specs=[
            "backlog:view/edit",
            "prds:view",
            "knowledge:view/contribute",
            "reports:view",
        ],
    ),
    RoleDef(
        name="support",
        description="Support team member",
        permission_specs=[
            "backlog:view/create",
            "knowledge:view",
        ],
    ),
    RoleDef(
        name="viewer",
        description="Read-only access",
        permission_specs=[
            "backlog:view",
            "prds:view",
            "knowledge:view",
            "reports:view",
        ],
    ),
]
