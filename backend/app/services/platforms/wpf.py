# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
