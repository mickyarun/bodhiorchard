# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Jetpack Compose Multiplatform / Desktop detection.

Marker: a Kotlin-DSL Gradle build script (``build.gradle.kts`` or
``settings.gradle.kts``) referencing ``org.jetbrains.compose``. Ordering is
set low (priority 55) so an Android repo with Compose still classifies as
``android_native`` (it ships a manifest; this platform does not).
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_GRADLE_SCRIPT_PATTERNS: tuple[str, ...] = (
    "build.gradle.kts",
    "settings.gradle.kts",
    "*/build.gradle.kts",
)


def _any_script_mentions_compose(repo: Path) -> bool:
    for pattern in _GRADLE_SCRIPT_PATTERNS:
        for script in repo.glob(pattern):
            try:
                text = script.read_text(errors="replace")
            except OSError:
                continue
            if "org.jetbrains.compose" in text:
                return True
    return False


@register
class ComposeDesktopPlatform:
    slug = "compose_desktop"
    kind = PlatformKind.DESKTOP
    priority = 55

    def detect(self, repo: Path) -> bool:
        return _any_script_mentions_compose(repo)

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "src/main/kotlin/**/theme/*.kt",
            "src/main/kotlin/**/Theme.kt",
            "src/main/kotlin/**/Color*.kt",
            "src/main/kotlin/**/Type.kt",
            "src/jvmMain/kotlin/**/theme/*.kt",
            "src/commonMain/kotlin/**/theme/*.kt",
            "build.gradle.kts",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("build", ".gradle", ".idea")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Jetpack Compose Multiplatform / Desktop app. Extract "
            "design tokens from Compose theme files (`Color.kt`, `Theme.kt`, "
            "`Type.kt`). Output tokens as Compose `Color`, `Typography`, "
            "`Shapes` declarations."
        )
