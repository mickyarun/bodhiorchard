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

"""WPF platform detection.

Marker: any ``.csproj`` containing ``<UseWPF>true</UseWPF>``.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._csproj import any_csproj_contains
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class WpfPlatform:
    slug = "wpf"
    kind = PlatformKind.DESKTOP
    priority = 60

    def detect(self, repo: Path) -> bool:
        return any_csproj_contains(repo, "<usewpf>true")

    @property
    def design_globs(self) -> tuple[str, ...]:
        # ``**/*Resources*.xaml`` was too broad — it matched any XAML file
        # with "Resources" in the name, including localized string
        # dictionaries. Constrain to ResourceDictionary-named files.
        return DEFAULT_COMMON_GLOBS + (
            "App.xaml",
            "**/App.xaml",
            "**/Themes/**/*.xaml",
            "**/Styles/**/*.xaml",
            "**/Brushes.xaml",
            "**/Colors.xaml",
            "**/Typography.xaml",
            "**/Theme.xaml",
            "**/ResourceDictionary.xaml",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("bin", "obj", ".vs", "packages")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Windows Presentation Foundation desktop app. Extract "
            "design tokens from `App.xaml` and any `Themes/` / `Styles/` "
            "ResourceDictionaries. Output tokens as XAML "
            "`<SolidColorBrush>` / `<Style>` resources with their keys."
        )
