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

"""Resolve the ``repo_id`` argument of the ``code_*`` MCP tools.

Agents get the id wrong in predictable ways — passing the repo name or its
clone path, or an id from another org. Each of those must come back as an
error that tells the agent what to pass instead (the org's repos with their
ids), not the generic "no cached graph" that reads like an unscanned repo
and sends the agent off to read files by hand.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.tracked_repository import TrackedRepoRepository

# Enough to cover any realistic org without letting the error envelope grow
# unbounded for an org with hundreds of repos.
_MAX_KNOWN_REPOS = 25
# An agent sometimes passes a whole path or blob as repo_id; echo only enough
# of it back for the agent to recognise its mistake.
_MAX_ECHOED_REPO_ID = 100


@dataclass(frozen=True)
class GraphRepo:
    """A resolved repo: its id, display name, and the SHA its graph is keyed on.

    ``head_sha`` is ``None`` when the repo is tracked but has never been
    scanned, which the caller reports as such.
    """

    repo_id: uuid.UUID
    name: str
    head_sha: str | None


@dataclass(frozen=True)
class RepoLookupError:
    """Why ``repo_id`` did not resolve, phrased for the calling agent."""

    message: str


async def resolve_graph_repo(
    db: AsyncSession,
    org: Organization,
    repo_id_raw: Any,
) -> GraphRepo | RepoLookupError:
    """Resolve ``repo_id_raw`` to one of ``org``'s tracked repositories."""
    tracked_repo = TrackedRepoRepository(db, org_id=org.id)
    try:
        repo_id = uuid.UUID(str(repo_id_raw))
    except ValueError:
        known = await _known_repos(tracked_repo)
        return RepoLookupError(
            f"repo_id must be a tracked repository UUID, got "
            f"{str(repo_id_raw)[:_MAX_ECHOED_REPO_ID]!r}. {known}"
        )

    tracked = await tracked_repo.get_by_id(repo_id)
    if tracked is None:
        known = await _known_repos(tracked_repo)
        return RepoLookupError(
            f"repo_id {repo_id} is not a tracked repository in this organization. {known}"
        )

    head_sha = tracked.head_sha
    if not head_sha:
        # ``head_sha`` is cleared by a scan reset; the last indexed SHA in
        # cluster_cache still points at a usable graph.
        head_sha = await ClusterCacheRepository(db, org_id=org.id).latest_head_sha(repo_id=repo_id)
    return GraphRepo(repo_id=repo_id, name=tracked.name, head_sha=head_sha)


def not_scanned_message(repo: GraphRepo) -> str:
    """Error text for a valid repo whose code graph is not available yet."""
    if repo.head_sha is None:
        return f"repo {repo.name!r} ({repo.repo_id}) has not been scanned yet — no code graph"
    return (
        f"no cached code graph for repo {repo.name!r} ({repo.repo_id}) at "
        f"head_sha {repo.head_sha} — it is not indexed at this commit yet (a scan may "
        "still be running); rescan the repo if this persists"
    )


async def _known_repos(tracked_repo: TrackedRepoRepository) -> str:
    """Render the org's active repos as ``name=id`` pairs for an error message."""
    triples = await tracked_repo.get_active_id_path_name()
    if not triples:
        return "This organization has no active tracked repositories."
    pairs = [f"{name}={rid}" for rid, _path, name in triples[:_MAX_KNOWN_REPOS]]
    more = len(triples) - _MAX_KNOWN_REPOS
    suffix = f", … ({more} more)" if more > 0 else ""
    return f"Known repos: {', '.join(pairs)}{suffix}"


__all__ = ["GraphRepo", "RepoLookupError", "not_scanned_message", "resolve_graph_repo"]
