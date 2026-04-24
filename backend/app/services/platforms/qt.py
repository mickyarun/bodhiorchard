# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Qt platform detection.

Markers (any one qualifies):
- A ``*.pro`` file (qmake project).
- A ``CMakeLists.txt`` that references ``Qt5`` / ``Qt6`` / ``find_package(Qt``.
- At least one ``*.qml`` file in the repo.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


def _cmake_mentions_qt(repo: Path) -> bool:
    cmake = repo / "CMakeLists.txt"
    if not cmake.exists():
        return False
    try:
        text = cmake.read_text(errors="replace").lower()
    except OSError:
        return False
    return "find_package(qt" in text or "qt5::" in text or "qt6::" in text


@register
class QtPlatform:
    slug = "qt"
    kind = PlatformKind.DESKTOP
    priority = 55

    def detect(self, repo: Path) -> bool:
        if next(repo.glob("*.pro"), None) is not None:
            return True
        if _cmake_mentions_qt(repo):
            return True
        return next(repo.rglob("*.qml"), None) is not None

    @property
    def design_globs(self) -> tuple[str, ...]:
        # ``**/*.qml`` matched every QML file (every screen, dialog,
        # component) even though only a handful are theme-related.
        # Scope to QML files whose name signals design content.
        return DEFAULT_COMMON_GLOBS + (
            "**/Theme.qml",
            "**/Theme*.qml",
            "**/Colors.qml",
            "**/Colors*.qml",
            "**/Palette.qml",
            "**/Typography.qml",
            "**/qml/**/Theme*.qml",
            "**/qml/**/Colors*.qml",
            "**/qtquickcontrols2.conf",
            "**/*.qss",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("build", "build-release", "build-debug", ".qt-creator")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Qt application (Widgets or QML). Extract design tokens "
            "from any `Theme*.qml` modules, `qtquickcontrols2.conf` style "
            "overrides, and `.qss` Qt Style Sheets. Prefer QML `Theme` "
            "singletons or `qtquickcontrols2.conf` palette keys as the "
            "canonical token format."
        )
