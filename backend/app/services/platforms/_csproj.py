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

"""Shared ``.csproj`` inspection helpers for the .NET family of platforms.

We do a case-insensitive substring scan rather than XML parsing because:
- csproj files are small and the interesting tokens (``<UseWPF>``,
  ``<UseMaui>``, NuGet package names) are unambiguous as literal strings.
- Different project styles (SDK-style vs legacy ``<Project>``) vary in
  structure; substring matching handles both.

Private to the platforms package — not part of the public API.
"""

from __future__ import annotations

from pathlib import Path


def iter_csproj_files(repo: Path) -> list[Path]:
    """Return every ``*.csproj`` under the repo (up to 4 levels deep)."""
    found: list[Path] = []
    for depth_glob in ("*.csproj", "*/*.csproj", "*/*/*.csproj", "*/*/*/*.csproj"):
        found.extend(repo.glob(depth_glob))
    return found


def any_csproj_contains(repo: Path, *needles: str) -> bool:
    """True if any csproj in the repo contains all of ``needles`` (case-insensitive)."""
    lowered_needles = tuple(n.lower() for n in needles)
    for csproj in iter_csproj_files(repo):
        try:
            text = csproj.read_text(errors="replace").lower()
        except OSError:
            continue
        if all(n in text for n in lowered_needles):
            return True
    return False


def any_csproj_contains_any(repo: Path, needles: tuple[str, ...]) -> bool:
    """True if any csproj contains at least one of the needles (case-insensitive)."""
    lowered = tuple(n.lower() for n in needles)
    for csproj in iter_csproj_files(repo):
        try:
            text = csproj.read_text(errors="replace").lower()
        except OSError:
            continue
        if any(n in text for n in lowered):
            return True
    return False
