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

"""MCP handlers for team context, Slack posting, and design systems.

Covers: get_team_context, post_slack_message, list_design_systems,
get_design_system.
"""

from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.models.organization import Organization
from app.repositories.skill_profile import SkillProfileRepository

logger = structlog.get_logger(__name__)


async def handle_get_team_context(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Read team capacity and skill profiles."""
    sp_repo = SkillProfileRepository(db, org_id=org.id)
    rows = await sp_repo.list_with_users()

    # Group by user
    team: dict[str, dict[str, Any]] = {}
    for profile, user in rows:
        key = str(profile.user_id) if profile.user_id else "unknown"
        if key not in team:
            team[key] = {
                "user_name": user.name if user else "Unknown",
                "email": user.email if user else "",
                "role": getattr(user, "role", "").value if getattr(user, "role", None) else "",
                "modules": [],
            }
        team[key]["modules"].append(
            {
                "name": profile.module,
                "score": float(profile.skill_score),
                "languages": profile.languages or [],
                "touch_count": profile.touch_count,
            }
        )

    logger.info("mcp_get_team_context", org_id=str(org.id), members=len(team))
    return {"team": list(team.values())}


async def handle_post_slack_message(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Post message to Slack via stored bot token."""
    channel = params.get("channel", "")
    message = params.get("message", "")
    thread_ts = params.get("thread_ts")

    bot_token = decrypt_secret(org.slack_bot_token or "")
    if not bot_token:
        return {"success": False, "error": "Slack bot token not configured for this organization"}

    payload: dict[str, str] = {
        "channel": channel,
        "text": message,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                json=payload,
                headers={"Authorization": f"Bearer {bot_token}"},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("slack_post_failed", error=data.get("error"))
                return {"success": False, "error": data.get("error", "Slack API error")}
    except Exception:
        logger.exception("slack_post_exception", channel=channel)
        return {"success": False, "error": "Failed to connect to Slack API"}

    logger.info("mcp_post_slack", org_id=str(org.id), channel=channel)
    return {"success": True, "channel": channel}


async def handle_list_design_systems(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """List all extracted design systems (metadata only, no content)."""
    from app.repositories.design_system import DesignSystemRefRepository

    ds_repo = DesignSystemRefRepository(db, org_id=org.id)
    rows = await ds_repo.list_with_repo_names()

    logger.info("mcp_list_design_systems", org_id=str(org.id), count=len(rows))
    return {
        "design_systems": [
            {
                "repo_id": str(row["repo_id"]),
                "repo_name": row["repo_name"] or "Unknown",
                "is_default": row["is_default"],
                "extracted_at": row["extracted_at"].isoformat() if row["extracted_at"] else None,
                "content_length": len(row["content"] or ""),
            }
            for row in rows
        ],
        "count": len(rows),
    }


async def handle_get_design_system(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve the full design system for a repo or the org default."""
    import uuid as _uuid

    from app.repositories.design_system import DesignSystemRefRepository

    ds_repo = DesignSystemRefRepository(db, org_id=org.id)
    repo_id_str = params.get("repo_id")

    rid = _uuid.UUID(repo_id_str) if repo_id_str else None
    ds = await ds_repo.get_effective(repo_id=rid)

    if not ds:
        return {
            "found": False,
            "content": "",
            "message": "No design system extracted for this repository or organization.",
        }

    logger.info(
        "mcp_get_design_system",
        org_id=str(org.id),
        repo_id=repo_id_str,
        content_length=len(ds.content or ""),
    )
    return {
        "found": True,
        "repo_id": str(ds.repo_id) if ds.repo_id else None,
        "is_default": ds.is_default,
        "content": ds.content or "",
    }
