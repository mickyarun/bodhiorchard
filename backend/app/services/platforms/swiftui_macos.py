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
