# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Native Android platform detection.

Requires BOTH markers to distinguish from generic Kotlin/JVM/Gradle projects:
- ``AndroidManifest.xml`` (anywhere in the tree — standard location is
  ``app/src/main/AndroidManifest.xml``).
- A Gradle script (``build.gradle`` or ``build.gradle.kts``).
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_MANIFEST_CANDIDATES: tuple[str, ...] = (
    "app/src/main/AndroidManifest.xml",
    "src/main/AndroidManifest.xml",
    "AndroidManifest.xml",
)

_GRADLE_CANDIDATES: tuple[str, ...] = (
    "build.gradle",
    "build.gradle.kts",
    "app/build.gradle",
    "app/build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
)


@register
class AndroidNativePlatform:
    slug = "android_native"
    kind = PlatformKind.MOBILE_NATIVE
    priority = 80

    def detect(self, repo: Path) -> bool:
        has_manifest = any((repo / m).exists() for m in _MANIFEST_CANDIDATES)
        if not has_manifest:
            return False
        return any((repo / g).exists() for g in _GRADLE_CANDIDATES)

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            # Classic XML resources (both app/ and top-level layouts)
            "**/res/values/colors.xml",
            "**/res/values/styles.xml",
            "**/res/values/themes*.xml",
            "**/res/values-night/colors.xml",
            "**/res/values-night/themes*.xml",
            "**/res/values/attrs.xml",
            "**/res/values/dimens.xml",
            # NOTE: ``strings.xml`` is deliberately excluded — it holds
            # user-facing copy, not design tokens.
            # Jetpack Compose theme
            "**/ui/theme/Color.kt",
            "**/ui/theme/Theme.kt",
            "**/ui/theme/Type.kt",
            "**/ui/theme/Shape.kt",
            # Build files often carry brand colours or Material Theme flags
            "app/build.gradle",
            "app/build.gradle.kts",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return (".gradle", "build", ".idea", "captures", "local.properties")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: native Android application. Extract design tokens from "
            "XML resources (colors.xml, themes.xml, styles.xml) AND Jetpack "
            "Compose theme files (Color.kt, Theme.kt, Type.kt). Preserve "
            "light/dark-mode variants when present (values-night). Output "
            "colour values in hex, typography as Compose TextStyle or XML "
            "style attributes, and note which Material palette "
            "(M2/M3/Material You) the app uses."
        )
