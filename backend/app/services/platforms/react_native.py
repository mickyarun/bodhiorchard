# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""React Native platform detection.

Marker: ``react-native`` npm dep AND ``metro.config.js`` (Metro is the RN-specific
bundler; its presence rules out generic RN-consumer web apps that happen to
import RN primitives). Expo apps declare ``expo`` separately and are picked up
by :mod:`app.services.platforms.expo` at equal priority — but Expo's module
registers alphabetically before ``react_native``, so an Expo app classifies
as Expo rather than RN.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._npm import package_has_any_dep
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_DEPS: frozenset[str] = frozenset({"react-native"})


@register
class ReactNativePlatform:
    slug = "react_native"
    kind = PlatformKind.MOBILE_CROSS
    priority = 70

    def detect(self, repo: Path) -> bool:
        if not package_has_any_dep(repo, _DEPS):
            return False
        return (repo / "metro.config.js").exists() or (repo / "metro.config.ts").exists()

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "package.json",
            "src/theme/**/*.ts",
            "src/theme/**/*.tsx",
            "src/styles/**/*.ts",
            "src/constants/colors.ts",
            "src/constants/theme.ts",
            "**/theme.ts",
            "**/tokens.ts",
            "**/colors.ts",
            "metro.config.js",
            "metro.config.ts",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("ios/Pods", "android/build", "android/.gradle")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: React Native cross-platform mobile app. Extract design "
            "tokens from the app's theme module (typically `src/theme/` or "
            "`src/constants/colors.ts`). Output `StyleSheet`-compatible "
            "tokens with platform-aware values where applicable."
        )
