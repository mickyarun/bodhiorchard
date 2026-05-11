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

"""Main API router that aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1.agent_skills import router as agent_skills_router
from app.api.v1.auth import router as auth_router
from app.api.v1.bud import router as bud_router
from app.api.v1.bugs import router as bugs_router
from app.api.v1.claude import router as claude_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.design_system import router as design_system_router
from app.api.v1.features import router as features_router
from app.api.v1.github_webhook import router as github_webhook_router
from app.api.v1.internal_colyseus import router as internal_colyseus_router
from app.api.v1.jira_import import router as jira_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.me import router as me_router
from app.api.v1.members import router as members_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.organizations import router as orgs_router
from app.api.v1.public import router as public_router
from app.api.v1.races import internal_router as races_internal_router
from app.api.v1.races import router as races_router
from app.api.v1.roles import router as roles_router
from app.api.v1.scans import router as scans_router
from app.api.v1.settings import router as settings_router
from app.api.v1.setup import router as setup_router
from app.api.v1.skills import router as skills_router
from app.api.v1.slack import router as slack_router
from app.api.v1.standups import router as standups_router
from app.api.v1.triage_sessions import router as triage_router
from app.api.v1.ws import router as ws_router
from app.api.v1.xp import router as xp_router
from app.mcp.server import router as mcp_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health")
api_router.include_router(setup_router, prefix="/api/setup")
api_router.include_router(auth_router, prefix="/api/v1/auth")
api_router.include_router(claude_router, prefix="/api/v1/claude")
api_router.include_router(orgs_router, prefix="/api/v1/organizations")
api_router.include_router(bud_router, prefix="/api/v1/buds")
api_router.include_router(bugs_router, prefix="/api/v1/bugs")
api_router.include_router(dashboard_router, prefix="/api/v1/dashboard")
api_router.include_router(design_system_router, prefix="/api/v1/design-systems")
api_router.include_router(features_router, prefix="/api/v1/features")
api_router.include_router(roles_router, prefix="/api/v1")
api_router.include_router(agent_skills_router, prefix="/api/v1/settings/agent-skills")
api_router.include_router(settings_router, prefix="/api/v1/settings")
api_router.include_router(skills_router, prefix="/api/v1/skills")
api_router.include_router(members_router, prefix="/api/v1")
api_router.include_router(notifications_router, prefix="/api/v1/notifications")
api_router.include_router(slack_router, prefix="/api/v1/slack")
api_router.include_router(standups_router, prefix="/api/v1/standups")
api_router.include_router(github_webhook_router, prefix="/api/v1/webhooks")
api_router.include_router(triage_router, prefix="/api/v1/triage-sessions")
api_router.include_router(jira_router, prefix="/api/v1/jira")
api_router.include_router(jobs_router, prefix="/api/v1/jobs")
api_router.include_router(me_router, prefix="/api/v1")
api_router.include_router(ws_router, prefix="/api/v1")
api_router.include_router(public_router, prefix="/api/v1/public")
api_router.include_router(xp_router, prefix="/api/v1")
api_router.include_router(mcp_router)
api_router.include_router(internal_colyseus_router, prefix="/api/v1")
api_router.include_router(races_router, prefix="/api/v1/races")
api_router.include_router(races_internal_router, prefix="/api/v1")
api_router.include_router(scans_router, prefix="/api/v1/reposcanv2")
