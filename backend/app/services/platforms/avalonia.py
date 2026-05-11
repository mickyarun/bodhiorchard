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

"""Avalonia platform detection.

Marker: any ``.csproj`` referencing the ``Avalonia`` NuGet package.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._csproj import any_csproj_contains_any
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_AVALONIA_NEEDLES: tuple[str, ...] = (
    'include="avalonia"',
    'packagereference include="avalonia',
    ">avalonia<",
)


@register
class AvaloniaPlatform:
    slug = "avalonia"
    kind = PlatformKind.DESKTOP
    priority = 60

    def detect(self, repo: Path) -> bool:
        return any_csproj_contains_any(repo, _AVALONIA_NEEDLES)

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "App.axaml",
            "**/App.axaml",
            "**/Themes/**/*.axaml",
            "**/Assets/**/*.axaml",
            "**/*Theme*.axaml",
            "**/*Colors*.axaml",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("bin", "obj", ".vs")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Avalonia cross-platform .NET desktop app. Extract "
            "design tokens from `.axaml` theme files (Avalonia's XAML "
            "dialect). Treat `<SolidColorBrush>` / `<Color>` resources as "
            "the canonical token format."
        )
