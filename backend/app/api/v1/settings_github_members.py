# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""GitHub-organisation member listing endpoint.

Lives in its own router file because the surface — talking to GitHub's
members API and zipping in profile data — has nothing to do with the
local repository CRUD that fills :mod:`settings_repos`. Splitting the
two keeps each file under the ~200-line guideline and lets the GitHub
PAT / installation-token error handling stay focused.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.github_app_auth import get_installation_token

router = APIRouter(tags=["settings-github-members"])


@router.get("/github/org-members")
async def list_github_org_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List members of the configured GitHub organisation.

    Returns dicts with ``login``, ``name``, ``avatar_url``, ``email``,
    and ``already_added`` (true when the GitHub login matches an existing
    Bodhiorchard user). The "already added" flag is what powers the
    invite-flow's "skip these accounts" filter.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    token = await get_installation_token(org)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub App is not configured. Set up a GitHub App in Settings.",
        )

    config = org.config or {}
    github_cfg = config.get("integrations", {}).get("github", {})
    github_org = github_cfg.get("org", "")
    if not github_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub organization name is not configured in Settings.",
        )

    gh_headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/orgs/{github_org}/members",
            params={"per_page": 100},
            headers=gh_headers,
            timeout=15,
        )
        _raise_for_github_error(resp, github_org)
        members = resp.json()

    async with httpx.AsyncClient() as profile_client:
        profiles = await asyncio.gather(
            *[_fetch_profile(profile_client, gh_headers, m.get("login", "")) for m in members]
        )

    user_repo = UserRepository(db, org_id=org.id)
    existing_users = await user_repo.list_by_org(org.id)
    existing_github = {u.github_username.lower() for u in existing_users if u.github_username}

    results: list[dict[str, Any]] = []
    for m, profile in zip(members, profiles, strict=True):
        login = m.get("login", "")
        results.append(
            {
                "login": login,
                "name": profile["name"],
                "avatar_url": m.get("avatar_url", ""),
                "email": profile["email"],
                "already_added": login.lower() in existing_github,
            }
        )
    return results


async def _fetch_profile(
    client: httpx.AsyncClient, headers: dict[str, str], login: str
) -> dict[str, str | None]:
    """Best-effort GitHub profile fetch — falls back to ``login`` on any error.

    Used to enrich the org-members list with display name + public
    email. We swallow individual failures because one bad profile
    shouldn't blank the whole roster.
    """
    try:
        r = await client.get(f"https://api.github.com/users/{login}", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return {"name": data.get("name") or login, "email": data.get("email")}
    except Exception:
        pass
    return {"name": login, "email": None}


def _raise_for_github_error(resp: httpx.Response, github_org: str) -> None:
    """Translate the most common GitHub API failures into actionable HTTPExceptions."""
    if resp.status_code == 200:
        return
    if resp.status_code == 401:
        gh_msg = resp.json().get("message", "") if resp.text else ""
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                f"GitHub PAT is unauthorized: {gh_msg}. "
                "Ensure the token has 'Members: Read' under "
                "Organization permissions."
            ),
        )
    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "GitHub PAT lacks required permissions. Go to GitHub → Settings → "
                "Developer settings → Fine-grained tokens → edit your token and "
                "add 'Members: Read' under Organization permissions."
            ),
        )
    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GitHub organization '{github_org}' not found. "
            "Check the org name in Settings.",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"GitHub API error ({resp.status_code}): {resp.text[:200]}",
    )
