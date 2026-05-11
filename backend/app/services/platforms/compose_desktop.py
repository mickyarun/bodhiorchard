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
