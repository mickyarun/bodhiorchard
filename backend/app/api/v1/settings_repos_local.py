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

"""Local-checkout picker endpoints: browse directories, read a repo's branches.

Both take a caller-chosen filesystem path, so both sit behind a session
*and* ``settings:edit`` (enforced once, on the router), and both confine
the path to :func:`picker_roots`. They serve the setup wizard's
Repositories step — which runs after ``init-org`` has minted a JWT — and
the Settings → Code "Add repositories" dialog. Kept apart from
:mod:`settings_repos` so that file stays focused on tracked-repo state.
"""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import require_permissions
from app.schemas.settings import LocalRepoBranches
from app.schemas.setup import BrowseDirectoriesResponse
from app.services.directory_listing import in_clone_root, list_subdirectories, picker_roots
from app.services.git_operations import list_local_branches, list_remote_branches
from app.services.repo_scanner import _detect_develop_branch, _detect_main_branch

router = APIRouter(
    tags=["settings-repos"],
    dependencies=[Depends(require_permissions("settings:edit"))],
)

_OUTSIDE_ROOTS = "Path is outside the directories the repository picker may browse."


@router.get("/repos/browse-directories", response_model=BrowseDirectoriesResponse)
async def browse_directories(
    path: str = Query(default="", description="Directory path to list. Defaults to home."),
) -> BrowseDirectoriesResponse:
    """List subdirectories at a given path for the folder picker.

    Returns the resolved current path, parent path, and child directories.
    Only directories are listed — no file contents are exposed.
    """
    # Containment check, inline and on the raw string. Two things matter
    # here and both are the result of CodeQL rejecting the tidier forms:
    # it runs before any pathlib call touches the filesystem (it flagged
    # `Path(path).expanduser()` as the sink), and it sits in the same
    # function as the sinks below, because the barrier is not carried
    # across a call — which is why `core.paths.safe_join`, doing exactly
    # this, does not satisfy the query in `file_storage.py` either.
    # `realpath` collapses `..` and resolves symlinks; `commonpath` then
    # confirms the result is still nested under a permitted root.
    candidate = os.path.realpath(os.path.expanduser(path or str(Path.home())))
    within = False
    for root in picker_roots():
        base = os.path.realpath(str(root))
        try:
            within = os.path.commonpath([base, candidate]) == base
        except ValueError:
            within = False  # unrelated roots / different drives
        if within:
            break
    if not within:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUTSIDE_ROOTS)
    # Another org's clones must not be listable either (host installs keep
    # the clone root under home). A separate raise: the plain `if not
    # within` above is what CodeQL recognises as the path barrier.
    if in_clone_root(candidate):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUTSIDE_ROOTS)
    target = Path(candidate)

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path does not exist: {target}",
        )
    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {target}",
        )

    try:
        entries = await asyncio.to_thread(list_subdirectories, target)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {target}",
        ) from exc

    parent = str(target.parent) if target != target.parent else None

    return BrowseDirectoriesResponse(
        current_path=str(target),
        parent_path=parent,
        directories=entries,
    )


@router.get("/repos/local-branches", response_model=LocalRepoBranches)
async def get_local_repo_branches(
    path: str = Query(..., description="Absolute path to a git repository"),
) -> LocalRepoBranches:
    """List branches of a local checkout and guess its main/develop branches.

    Doubles as the "is this a git repo?" check before a path is added, so
    a missing or non-git path is a 400 the caller can show inline.
    """
    # Containment check, inline and on the raw string — see
    # :func:`browse_directories` for why it cannot move into a helper.
    candidate = os.path.realpath(os.path.expanduser(path))
    within = False
    for root in picker_roots():
        base = os.path.realpath(str(root))
        try:
            within = os.path.commonpath([base, candidate]) == base
        except ValueError:
            within = False  # unrelated roots / different drives
        if within:
            break
    if not within:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUTSIDE_ROOTS)
    if in_clone_root(candidate):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUTSIDE_ROOTS)
    repo_path = Path(candidate)
    if not repo_path.exists() or not (repo_path / ".git").exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a git repository: {path}",
        )

    return LocalRepoBranches(
        # A checkout with no remote has no remote branches; offer its local ones.
        branches=(
            await list_remote_branches(str(repo_path)) or await list_local_branches(str(repo_path))
        ),
        detected_main=await _detect_main_branch(str(repo_path)),
        detected_develop=await _detect_develop_branch(str(repo_path)),
    )
