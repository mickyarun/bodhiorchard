# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Flutter platform detection.

Marker: ``pubspec.yaml`` at the repo root declaring a ``flutter:`` section OR
listing ``flutter`` / a Flutter plugin in its dependencies. The ``flutter:``
key alone distinguishes Flutter projects from generic Dart packages.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class FlutterPlatform:
    slug = "flutter"
    kind = PlatformKind.MOBILE_NATIVE
    priority = 80

    def detect(self, repo: Path) -> bool:
        pubspec = repo / "pubspec.yaml"
        if not pubspec.exists():
            return False
        text = pubspec.read_text(errors="replace")
        # ``flutter:`` as a top-level key, or ``flutter`` listed as a dep.
        return "\nflutter:" in f"\n{text}" or "  flutter:" in text

    @property
    def design_globs(self) -> tuple[str, ...]:
        # Deliberately strict. Early iterations globbed ``lib/config/**/*.dart``
        # and ``lib/constants/**/*.dart`` which swept in ``api_endpoints.dart``,
        # ``keys.dart``, ``regular_expressions.dart`` etc. — noise that inflated
        # the LLM prompt and pushed extraction past the 300 s timeout. Match
        # only files whose names clearly indicate design / theme / colour /
        # typography content.
        return DEFAULT_COMMON_GLOBS + (
            "pubspec.yaml",
            # Theme modules
            "lib/**/theme.dart",
            "lib/**/theme_*.dart",
            "lib/**/*_theme.dart",
            "lib/theme/**/*.dart",
            "lib/themes/**/*.dart",
            "lib/**/app_theme.dart",
            "lib/**/app_theme_*.dart",
            # Colour modules
            "lib/**/colors.dart",
            "lib/**/app_colors.dart",
            "lib/**/color_palette.dart",
            "lib/**/*_colors.dart",
            # Typography
            "lib/**/typography.dart",
            "lib/**/text_styles.dart",
            "lib/**/*_text_styles.dart",
            # Design tokens
            "lib/**/design_tokens.dart",
            "lib/**/design_tokens_*.dart",
            "lib/**/tokens.dart",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return (
            ".dart_tool",
            ".flutter-plugins-dependencies",
            "build",
            "ios",  # native shims — iOS platform handles them if present
            "android",
            "windows",
            "linux",
            "macos",
        )

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Flutter mobile app. Extract design tokens from ThemeData, "
            "ColorScheme, TextTheme, and Material 3 usage. Output color values "
            "in hex, typography as Dart TextStyle, and spacing as EdgeInsets "
            "constants. Use idiomatic Dart naming in the extracted tokens."
        )
