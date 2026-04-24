# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""SwiftUI macOS platform detection.

Distinguishes macOS-only SwiftUI apps from iOS by scanning ``.xcodeproj``
pbxproj for a ``macosx`` SDK / ``SDKROOT = macosx`` setting and the absence
of an iOS / iPhoneOS target. iOS remains the default Apple platform at
priority 80; this module only claims repos that explicitly target macOS.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


def _xcodeproj_targets_macos_only(repo: Path) -> bool:
    for pbxproj in repo.rglob("*.xcodeproj/project.pbxproj"):
        try:
            text = pbxproj.read_text(errors="replace")
        except OSError:
            continue
        mentions_macos = "SDKROOT = macosx" in text or "macosx " in text
        mentions_ios = "SDKROOT = iphoneos" in text or "iphonesimulator" in text
        if mentions_macos and not mentions_ios:
            return True
    return False


@register
class SwiftUiMacosPlatform:
    slug = "swiftui_macos"
    kind = PlatformKind.DESKTOP
    # Higher than ios_native (80) — macos-only is more specific than a generic
    # xcodeproj, so this detector must run first.
    priority = 85

    def detect(self, repo: Path) -> bool:
        return _xcodeproj_targets_macos_only(repo)

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "**/Assets.xcassets/Colors/**/Contents.json",
            "**/*Theme*.swift",
            "**/*Color*.swift",
            "**/Sources/**/Theme.swift",
            "**/Sources/**/DesignTokens/**/*.swift",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("DerivedData", ".build", "build", "xcuserdata")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: macOS SwiftUI / AppKit application. Extract design "
            "tokens from Asset Catalog colors and SwiftUI `Color` / "
            "`Font` definitions. Preserve appearance (aqua / dark-aqua) "
            "variants present in the Asset Catalog."
        )
