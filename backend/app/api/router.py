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

"""Main API router that aggregates all sub-routers.

Routers are split into two groups:

* **Shared** — reachable by every authenticated member regardless of
  workspace: auth, setup, membership, notifications, and transports that
  authenticate themselves (webhooks, MCP tokens, the Colyseus bridge).
* **Engineering** — everything else, mounted under one parent router that
  requires ``workspace:engineering``. A people-only role such as ``sales``
  gets 403 on all of it.

The split is default-deny: a new router belongs in the engineering group
unless it's deliberately added to the shared list.
``tests/api/test_workspace_gate.py`` walks every route and fails if one
is in neither group.
"""

from fastapi import APIRouter, Depends

from app.api.health import router as health_router
from app.api.v1.agent_skills import router as agent_skills_router
from app.api.v1.ai_settings import router as ai_settings_router
from app.api.v1.auth import router as auth_router
from app.api.v1.backlash import internal_router as backlash_internal_router
from app.api.v1.backlash import router as backlash_router
from app.api.v1.bud import router as bud_router
from app.api.v1.bug_attachments import router as bug_attachments_router
from app.api.v1.bug_comments import router as bug_comments_router
from app.api.v1.bugs import router as bugs_router
from app.api.v1.claude import router as claude_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.design_system import router as design_system_router
from app.api.v1.employee_documents import router as employee_documents_router
from app.api.v1.employee_sensitive import router as employee_sensitive_router
from app.api.v1.employee_updates import router as employee_updates_router
from app.api.v1.employees import router as employees_router
from app.api.v1.features import router as features_router
from app.api.v1.github_webhook import router as github_webhook_router
from app.api.v1.internal_colyseus import router as internal_colyseus_router
from app.api.v1.jira_import import router as jira_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.learnings import router as learnings_router
from app.api.v1.leave import router as leave_router
from app.api.v1.leave_approvals import router as leave_approvals_router
from app.api.v1.leave_balances import router as leave_balances_router
from app.api.v1.leave_calendar import router as leave_calendar_router
from app.api.v1.leave_calendar_sync import router as leave_calendar_sync_router
from app.api.v1.leave_digest import router as leave_digest_router
from app.api.v1.leave_history import router as leave_history_router
from app.api.v1.leave_holidays import router as leave_holidays_router
from app.api.v1.leave_policies import router as leave_policies_router
from app.api.v1.leave_reports import router as leave_reports_router
from app.api.v1.leave_reports_export import router as leave_reports_export_router
from app.api.v1.leave_types import router as leave_types_router
from app.api.v1.me import router as me_router
from app.api.v1.members import router as members_router
from app.api.v1.minigames import router as minigames_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.offices import router as offices_router
from app.api.v1.organizations import router as orgs_router
from app.api.v1.public import router as public_router
from app.api.v1.quiz import router as quiz_router
from app.api.v1.quiz_review import router as quiz_review_router
from app.api.v1.races import internal_router as races_internal_router
from app.api.v1.races import router as races_router
from app.api.v1.roles import router as roles_router
from app.api.v1.scans import router as scans_router
from app.api.v1.settings import router as settings_router
from app.api.v1.settings_claude import router as settings_claude_router
from app.api.v1.settings_github_members import router as settings_gh_members_router
from app.api.v1.settings_mcp_tokens import router as settings_mcp_tokens_router
from app.api.v1.settings_repos import router as settings_repos_router
from app.api.v1.settings_slack import router as settings_slack_router
from app.api.v1.setup import router as setup_router
from app.api.v1.skills import router as skills_router
from app.api.v1.slack import router as slack_router
from app.api.v1.slack_interactions import router as slack_interactions_router
from app.api.v1.standups import router as standups_router
from app.api.v1.teams import router as teams_router
from app.api.v1.triage_sessions import router as triage_router
from app.api.v1.ws import router as ws_router
from app.api.v1.xp import router as xp_router
from app.api.v1.yield_offers import router as yield_offers_router
from app.core.deps import require_permissions
from app.core.http_cache import no_store
from app.core.permissions import WORKSPACE_ENGINEERING
from app.mcp.server import router as mcp_router
from app.mcp.streamable import router as mcp_remote_router

api_router = APIRouter()

# ── Shared ──────────────────────────────────────────────────────────────
api_router.include_router(health_router, prefix="/health")
api_router.include_router(setup_router, prefix="/api/setup")
api_router.include_router(auth_router, prefix="/api/v1/auth")
api_router.include_router(orgs_router, prefix="/api/v1/organizations")
api_router.include_router(roles_router, prefix="/api/v1")
api_router.include_router(members_router, prefix="/api/v1")
api_router.include_router(me_router, prefix="/api/v1")
api_router.include_router(notifications_router, prefix="/api/v1/notifications")
api_router.include_router(ws_router, prefix="/api/v1")
api_router.include_router(public_router, prefix="/api/v1/public")
# People workspace: open to every member; each route checks its own
# employees:* / leave:* permission or "own record". Nothing here may be
# cached: it carries leave reasons, balances and personal details.
PEOPLE_NO_STORE = [Depends(no_store)]
for employee_part in (
    employees_router,
    employee_updates_router,
    employee_sensitive_router,
    employee_documents_router,
):
    api_router.include_router(
        employee_part, prefix="/api/v1/employees", dependencies=PEOPLE_NO_STORE
    )
api_router.include_router(offices_router, prefix="/api/v1/offices", dependencies=PEOPLE_NO_STORE)
for leave_part in (
    leave_router,
    leave_approvals_router,
    leave_calendar_router,
    leave_balances_router,
    leave_policies_router,
    leave_types_router,
    leave_holidays_router,
    leave_digest_router,
    leave_calendar_sync_router,
    leave_reports_router,
    leave_reports_export_router,
    leave_history_router,
):
    api_router.include_router(leave_part, prefix="/api/v1/leave", dependencies=PEOPLE_NO_STORE)
# Org-level settings routes; each is gated by its own org/integration
# permission. The engineering-only settings sub-routers are mounted below.
api_router.include_router(settings_router, prefix="/api/v1/settings")
# Self-authenticating transports: signed webhooks, MCP bearer tokens and the
# Colyseus bridge secret. They don't use the JWT the gate depends on.
api_router.include_router(slack_router, prefix="/api/v1/slack")
# Signed by Slack (no login): approve / reject leave from a DM.
api_router.include_router(slack_interactions_router, prefix="/api/v1/slack")
api_router.include_router(github_webhook_router, prefix="/api/v1/webhooks")
api_router.include_router(mcp_router)
# Remote MCP endpoint for external LLM clients (Claude Desktop / Cursor /
# Continue). Shares /mcp/ prefix and Bearer auth with the existing tool
# endpoint but enforces a hard-coded read-only tool allowlist at the
# transport layer — see app/mcp/streamable.py for the rationale.
api_router.include_router(mcp_remote_router)
api_router.include_router(internal_colyseus_router, prefix="/api/v1")
api_router.include_router(backlash_internal_router, prefix="/api/v1")
api_router.include_router(races_internal_router, prefix="/api/v1")

# ── Engineering workspace ───────────────────────────────────────────────
# Sub-routers must be included into the parent *before* the parent is
# included into ``api_router``: FastAPI copies routes at include time.
engineering_router = APIRouter(
    dependencies=[Depends(require_permissions(WORKSPACE_ENGINEERING))],
)
engineering_router.include_router(claude_router, prefix="/api/v1/claude")
engineering_router.include_router(bud_router, prefix="/api/v1/buds")
engineering_router.include_router(bugs_router, prefix="/api/v1/bugs")
engineering_router.include_router(bug_comments_router, prefix="/api/v1/bugs")
engineering_router.include_router(bug_attachments_router, prefix="/api/v1/bugs")
engineering_router.include_router(dashboard_router, prefix="/api/v1/dashboard")
engineering_router.include_router(design_system_router, prefix="/api/v1/design-systems")
engineering_router.include_router(features_router, prefix="/api/v1/features")
engineering_router.include_router(agent_skills_router, prefix="/api/v1/settings/agent-skills")
engineering_router.include_router(settings_repos_router, prefix="/api/v1/settings")
engineering_router.include_router(settings_slack_router, prefix="/api/v1/settings")
engineering_router.include_router(settings_claude_router, prefix="/api/v1/settings")
engineering_router.include_router(ai_settings_router, prefix="/api/v1/settings")
engineering_router.include_router(settings_gh_members_router, prefix="/api/v1/settings")
engineering_router.include_router(settings_mcp_tokens_router, prefix="/api/v1/settings")
engineering_router.include_router(skills_router, prefix="/api/v1/skills")
engineering_router.include_router(standups_router, prefix="/api/v1/standups")
engineering_router.include_router(teams_router, prefix="/api/v1")
engineering_router.include_router(triage_router, prefix="/api/v1/triage-sessions")
engineering_router.include_router(jira_router, prefix="/api/v1/jira")
engineering_router.include_router(jobs_router, prefix="/api/v1/jobs")
engineering_router.include_router(learnings_router, prefix="/api/v1/learnings")
engineering_router.include_router(xp_router, prefix="/api/v1")
engineering_router.include_router(yield_offers_router, prefix="/api/v1")
engineering_router.include_router(minigames_router, prefix="/api/v1/minigames")
engineering_router.include_router(backlash_router, prefix="/api/v1/minigames/backlash")
engineering_router.include_router(quiz_router, prefix="/api/v1/quiz")
engineering_router.include_router(quiz_review_router, prefix="/api/v1/quiz")
engineering_router.include_router(races_router, prefix="/api/v1/races")
engineering_router.include_router(scans_router, prefix="/api/v1/reposcanv2")

api_router.include_router(engineering_router)
