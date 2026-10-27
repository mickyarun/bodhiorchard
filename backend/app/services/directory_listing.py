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

"""The local repository picker's allowed roots and its one-level directory walk."""

import contextlib
import os
from pathlib import Path

from app.config import settings
from app.schemas.setup import DirectoryEntry


def picker_roots() -> tuple[Path, ...]:
    """Directories a caller-chosen repository path may sit under.

    The home directory, which is where development checkouts live in
    practice. Kept as a function rather than a constant so tests can
    point it somewhere hermetic, and so adding a root later is one edit.
    Shared by the picker endpoints, add-by-path and the setup wizard's
    finalize, so all three accept the same paths.
    """
    return (Path.home(),)


def in_clone_root(candidate: str) -> bool:
    """Whether an already-resolved path sits inside the shared clone root.

    The clone root holds every org's clones side by side, so a path inside
    it is never accepted from a caller: clones are registered by
    ``POST /repos/clone``, not by path. On a host install it lives in the
    checkout, under home, which is why the picker roots alone don't keep
    it out.

    Compared case-folded: ``realpath`` keeps the caller's spelling, and on
    a case-insensitive volume (macOS default) ``.data/REPOS/...`` still
    opens the clone root. This side only ever refuses, so folding can
    over-refuse but never widens access.
    """
    base = os.path.realpath(str(settings.storage.repos_dir)).casefold()
    try:
        return os.path.commonpath([base, candidate.casefold()]) == base
    except ValueError:
        return False  # unrelated roots / different drives


def list_subdirectories(target: Path) -> list[DirectoryEntry]:
    """Walk ``target`` one level deep, flagging git repos and monorepos.

    Runs synchronously — callers from async endpoints must wrap this in
    ``asyncio.to_thread`` so the event loop doesn't block on the stat
    calls (users with deep home dirs can have hundreds of entries).

    The caller is responsible for confining ``target`` to a permitted
    root before calling this; nothing here checks where it points.
    """
    entries: list[DirectoryEntry] = []
    for child in sorted(target.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        is_git = (child / ".git").exists()
        # For a git repo, peek one level down to flag monorepos — short-
        # circuits at the first nested `.git`, so the cost is one
        # iterdir call plus at most a handful of stats per repo.
        has_sub_repos = False
        if is_git:
            with contextlib.suppress(PermissionError, OSError):
                has_sub_repos = any(
                    (gc / ".git").exists()
                    for gc in child.iterdir()
                    if gc.is_dir() and not gc.name.startswith(".")
                )
        entries.append(
            DirectoryEntry(
                name=child.name,
                path=str(child),
                is_git_repo=is_git,
                has_sub_repos=has_sub_repos,
            )
        )
    return entries
