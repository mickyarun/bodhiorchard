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

"""Refresh ``origin`` in a clone with a freshly-minted installation token.

The clone-path's ``.git/config`` carries whatever ``origin`` URL was
written at clone time. GitHub-App installation tokens expire after 1
hour (no refresh mechanism — every "refresh" is a new mint), so any
``git``/``gh`` operation the agent runs more than an hour after the
original clone can fail with ``Invalid username or token``. This helper
runs the same ``git remote set-url origin`` flip that
``repo_cloner.clone_or_update_repo`` does on the update path, but lifted
to a standalone call so it can be invoked right before each agent
spawn — guaranteeing the agent's git/gh commands see a fresh token.

Best-effort by design: failures are logged and swallowed so they never
block the agent run. If the refresh fails (no App creds, repo not
tracked, git config write error), the agent run still starts — it may
then fail with the auth-rejection path, which the code-review parser
classifier now surfaces as ``git_auth_failed`` with an actionable banner.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.git_operations import run_git
from app.services.github_app_auth import get_installation_token

logger = structlog.get_logger(__name__)


async def refresh_origin_token(
    *,
    working_dir: str,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    """Re-stamp ``origin`` in ``working_dir``'s clone with a fresh token.

    Returns ``True`` when the URL was updated, ``False`` on any
    best-effort failure (no App creds, not a tracked GitHub repo, git
    config write error). Never raises — token freshness is a
    nice-to-have, not a precondition for the spawn.
    """
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    repo = await repo_repo.get_by_path(working_dir)
    if repo is None or not repo.github_repo_full_name:
        # Working dir isn't a tracked GitHub repo (could be the no-repo
        # scratch dir, a local-only repo, or a tracked repo without a
        # GitHub link). Nothing to refresh.
        return False

    org = await db.get(Organization, org_id)
    if org is None:
        logger.warning("origin_refresh_skip_no_org", org_id=str(org_id))
        return False

    token = await get_installation_token(org)
    if not token:
        # No App creds — caller may be on PAT-only or SSH auth. Skip;
        # those paths don't need an installation-token refresh. Logged
        # at debug so a downstream ``git_auth_failed`` banner can be
        # cross-referenced against "did we even attempt a refresh?".
        logger.debug(
            "origin_refresh_skip_no_app_creds",
            org_id=str(org_id),
            repo=repo.github_repo_full_name,
        )
        return False

    # ``x-access-token`` is the documented username for installation-token
    # auth. Kept inline rather than importing the App-clone-URL template
    # to avoid a heavier dependency chain.
    new_url = f"https://x-access-token:{token}@github.com/{repo.github_repo_full_name}.git"

    _, stderr, rc = await run_git(
        ["remote", "set-url", "origin", new_url],
        cwd=working_dir,
    )
    if rc != 0:
        scrubbed = stderr.replace(token, "<redacted>")
        logger.warning(
            "origin_refresh_failed",
            org_id=str(org_id),
            repo_path=working_dir,
            stderr=scrubbed[:300],
        )
        return False

    logger.info(
        "origin_refresh_ok",
        org_id=str(org_id),
        repo=repo.github_repo_full_name,
    )
    return True
