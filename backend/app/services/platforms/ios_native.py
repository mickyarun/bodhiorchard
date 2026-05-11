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

"""Native iOS platform detection.

Marker: any of ``*.xcodeproj``, ``Podfile``, or ``Package.swift`` at the repo
root (or up to two levels deep — some monorepos nest iOS under ``ios/`` or
``apple/``). Swift Package Manager projects without CocoaPods/Xcode still
qualify if a Swift source imports SwiftUI or UIKit.

This registers at priority 80, same as Flutter and Android, but is only
reached when the higher-priority mobile platforms decline — ordering inside a
priority bucket is registration (import) order, which is alphabetical via
``__init__.py``. Flutter registers a ``flutter:`` check on ``pubspec.yaml``
so a Flutter-with-iOS-shim repo classifies as Flutter.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_XCODE_PATTERNS: tuple[str, ...] = ("*.xcodeproj", "*/*.xcodeproj", "*/*/*.xcodeproj")
_PODFILE_PATTERNS: tuple[str, ...] = ("Podfile", "ios/Podfile", "apple/Podfile")
_SWIFT_PACKAGE_PATTERNS: tuple[str, ...] = (
    "Package.swift",
    "ios/Package.swift",
    "apple/Package.swift",
)

# Cap the Swift-source scan: the per-file read is bounded to this many bytes
# and the directory walk stops after this many files so large Swift-on-Linux
# repos don't turn ``detect`` into an O(N) operation.
_MAX_SWIFT_FILES_TO_SCAN = 50
_MAX_SWIFT_FILE_BYTES = 16_384


def _any_match(repo: Path, patterns: tuple[str, ...]) -> bool:
    return any(next(repo.glob(pat), None) is not None for pat in patterns)


def _swift_sources_import_ui(repo: Path) -> bool:
    """Scan at most ``_MAX_SWIFT_FILES_TO_SCAN`` Swift sources under the repo.

    Bounded to keep ``detect()`` inside the sub-50 ms budget documented in
    ``README.md`` — a raw ``rglob("*.swift")`` can walk arbitrarily large
    trees on monorepos.
    """
    scanned = 0
    for swift_file in repo.rglob("*.swift"):
        if scanned >= _MAX_SWIFT_FILES_TO_SCAN:
            return False
        scanned += 1
        try:
            with swift_file.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(_MAX_SWIFT_FILE_BYTES)
        except OSError:
            continue
        if "import SwiftUI" in head or "import UIKit" in head:
            return True
    return False


@register
class IosNativePlatform:
    slug = "ios_native"
    kind = PlatformKind.MOBILE_NATIVE
    priority = 80

    def detect(self, repo: Path) -> bool:
        if _any_match(repo, _XCODE_PATTERNS):
            return True
        if _any_match(repo, _PODFILE_PATTERNS):
            return True
        if _any_match(repo, _SWIFT_PACKAGE_PATTERNS):
            # Package.swift can also be a pure server-side Swift project.
            return _swift_sources_import_ui(repo)
        return False

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "**/Assets.xcassets/Colors/**/Contents.json",
            "**/Assets.xcassets/**/Contents.json",
            "**/*Theme*.swift",
            "**/*Color*.swift",
            "**/*Style*.swift",
            "**/DesignTokens/**/*.swift",
            "**/Color+*.swift",
            "**/Font+*.swift",
            "Package.swift",
            "Podfile",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("Pods", "DerivedData", ".build", "build", "xcuserdata")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: native iOS application (SwiftUI or UIKit). Extract "
            "design tokens from Asset Catalog colors (Assets.xcassets/Colors/"
            "*/Contents.json), SwiftUI Color / Font / Style definitions, and "
            "any ThemeManager / DesignTokens Swift files. Preserve "
            "light / dark appearance variants. Output colour values as RGB "
            "or sRGB hex, typography as SwiftUI Font declarations."
        )
