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

"""Shared pieces for the caller-chosen repository path tests.

The picker, add-by-path and branch lookup tests all mount one settings
router on a bare ASGI app with the session and permission lookups
stubbed, and all build real git checkouts in ``tmp_path``. Those two
helpers live here so each test module stays about its own behaviour.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, FastAPI

from app.core.auth_deps import get_current_user, get_db
from app.core.permission_deps import PermissionSet, get_permission_set

EDITOR = frozenset({"settings:view", "settings:edit"})
SETTINGS_PREFIX = "/api/v1/settings"


def settings_app(
    router: APIRouter,
    db: Callable[[], AsyncIterator[Any]],
    permissions: frozenset[str] = EDITOR,
) -> FastAPI:
    """``router`` at the settings prefix, signed in with ``permissions``."""
    app = FastAPI()
    app.include_router(router, prefix=SETTINGS_PREFIX)
    app.dependency_overrides[get_db] = db
    user = SimpleNamespace(id=uuid.uuid4(), must_change_password=False)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_permission_set] = lambda: PermissionSet(
        ids=permissions, is_owner=False
    )
    return app


def run_git(*args: str, cwd: Path) -> str:
    """Run git with a throwaway identity; return stdout."""
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


def init_repo(path: Path, *branches: str) -> Path:
    """A local-only checkout at ``path`` on ``main`` plus extra ``branches``."""
    path.mkdir(parents=True, exist_ok=True)
    run_git("init", "-q", "-b", "main", cwd=path)
    run_git("commit", "-q", "--allow-empty", "-m", "init", cwd=path)
    for branch in branches:
        run_git("branch", branch, cwd=path)
    return path
