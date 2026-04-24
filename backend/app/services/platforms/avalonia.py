# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
