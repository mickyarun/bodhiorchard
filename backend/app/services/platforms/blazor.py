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

"""Blazor platform detection.

Markers:
- A ``.csproj`` referencing ``Microsoft.AspNetCore.Components.*``.
- At least one ``.razor`` file in the repo (Blazor's component file extension).
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._csproj import any_csproj_contains_any
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_BLAZOR_PACKAGE_NEEDLES: tuple[str, ...] = (
    "microsoft.aspnetcore.components",
    "blazor",
)


@register
class BlazorPlatform:
    slug = "blazor"
    kind = PlatformKind.DESKTOP
    priority = 60

    def detect(self, repo: Path) -> bool:
        if not any_csproj_contains_any(repo, _BLAZOR_PACKAGE_NEEDLES):
            return False
        return next(repo.rglob("*.razor"), None) is not None

    @property
    def design_globs(self) -> tuple[str, ...]:
        # ``Shared/**/*.razor`` and ``**/Program.cs`` are not design files.
        # Keep to the wwwroot stylesheets and explicit theme razor files.
        return DEFAULT_COMMON_GLOBS + (
            "wwwroot/css/site.css",
            "wwwroot/css/app.css",
            "wwwroot/css/**/*.css",
            "wwwroot/css/**/*.scss",
            "**/*.razor.css",
            "App.razor",
            "Themes/**/*.razor",
            "Themes/**/*.razor.css",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("bin", "obj", ".vs")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Blazor .NET web/desktop app. Extract design tokens from "
            "`wwwroot/css/**` (site.css / app.css) and any `*.razor.css` "
            "scoped-style files. Preserve Bootstrap or Fluent-UI token "
            "naming when the app uses those libraries."
        )
