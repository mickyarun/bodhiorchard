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

"""`.NET MAUI` platform detection.

Marker: any ``.csproj`` containing ``<UseMaui>true</UseMaui>``.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._csproj import any_csproj_contains
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class DotNetMauiPlatform:
    slug = "dotnet_maui"
    kind = PlatformKind.DESKTOP
    priority = 60

    def detect(self, repo: Path) -> bool:
        return any_csproj_contains(repo, "<usemaui>true")

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "**/Resources/Styles/Colors.xaml",
            "**/Resources/Styles/Styles.xaml",
            "**/Resources/Styles/**/*.xaml",
            "**/Resources/Fonts/**/*.ttf",
            "App.xaml",
            "**/App.xaml",
            "MauiProgram.cs",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("bin", "obj", ".vs")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: .NET MAUI cross-platform app. Extract design tokens "
            "from `Resources/Styles/Colors.xaml` and `Styles.xaml` "
            "(the MAUI convention). Output tokens as XAML "
            "`<Color x:Key=...>` resources."
        )
