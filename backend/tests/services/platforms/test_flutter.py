# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Flutter detection tests."""

from __future__ import annotations

from pathlib import Path

from app.services.platforms import PlatformKind, detect_platform


def _write_pubspec(repo: Path, body: str) -> None:
    (repo / "pubspec.yaml").write_text(body)


def test_detects_flutter_project_with_flutter_section(tmp_path: Path) -> None:
    _write_pubspec(
        tmp_path,
        """\
name: demo
description: demo app
environment:
  sdk: ^3.0.0

dependencies:
  flutter:
    sdk: flutter

flutter:
  uses-material-design: true
""",
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "flutter"
    assert platform.kind == PlatformKind.MOBILE_NATIVE


def test_detects_flutter_when_only_dependency_listed(tmp_path: Path) -> None:
    _write_pubspec(
        tmp_path,
        """\
name: demo
dependencies:
  flutter:
    sdk: flutter
""",
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "flutter"


def test_does_not_claim_pure_dart_package(tmp_path: Path) -> None:
    _write_pubspec(
        tmp_path,
        """\
name: demo_cli
dependencies:
  args: ^2.0.0
""",
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


def test_globs_include_theme_and_colors(tmp_path: Path) -> None:
    _write_pubspec(tmp_path, "name: x\ndependencies:\n  flutter:\n    sdk: flutter\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    globs = platform.design_globs
    assert "lib/theme/**/*.dart" in globs
    assert "pubspec.yaml" in globs
    assert any("colors" in g for g in globs)


def test_prompt_hint_mentions_theme_data(tmp_path: Path) -> None:
    _write_pubspec(tmp_path, "flutter:\n  uses-material-design: true\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert "ThemeData" in platform.prompt_hint


def test_globs_reject_non_design_dart_files(tmp_path: Path) -> None:
    """Regression: the first Flutter glob pass swept in `api_endpoints.dart`
    and `keys.dart` via ``lib/config/**/*.dart`` and ``lib/constants/**/*.dart``.
    That bloated the LLM prompt past the 300 s timeout on real apps. These
    non-design files must NOT be discovered."""
    from app.services.design_system_extractor import discover_design_files

    _write_pubspec(
        tmp_path,
        "name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n",
    )
    lib = tmp_path / "lib"
    (lib / "config").mkdir(parents=True)
    (lib / "constants").mkdir()
    (lib / "theme").mkdir()

    # Noise (must NOT be discovered)
    (lib / "config" / "api_endpoints.dart").write_text("// api base urls")
    (lib / "config" / "app_config.dart").write_text("// flags")
    (lib / "config" / "local_app_config.dart").write_text("// local flags")
    (lib / "constants" / "keys.dart").write_text("// secret keys")
    (lib / "constants" / "asset_strings.dart").write_text("// strings")
    (lib / "constants" / "regular_expressions.dart").write_text("// regexes")
    (lib / "constants" / "route_path.dart").write_text("// routes")
    (lib / "atoa_public_key.dart").write_text("// rsa pubkey")

    # Signal (must be discovered)
    (lib / "theme" / "app_theme.dart").write_text("class AppTheme {}")
    (lib / "theme" / "colors.dart").write_text("class AppColors {}")
    (lib / "theme" / "typography.dart").write_text("class AppTypography {}")
    (lib / "theme_color_picker.dart").write_text("class ThemeColorPicker {}")

    platform = detect_platform(tmp_path)
    assert platform is not None
    discovered = {p.name for p in discover_design_files(tmp_path, platform)}

    # Signal
    assert "pubspec.yaml" in discovered
    assert "app_theme.dart" in discovered
    assert "colors.dart" in discovered
    assert "typography.dart" in discovered
    assert "theme_color_picker.dart" in discovered

    # Noise
    assert "api_endpoints.dart" not in discovered
    assert "app_config.dart" not in discovered
    assert "local_app_config.dart" not in discovered
    assert "keys.dart" not in discovered
    assert "asset_strings.dart" not in discovered
    assert "regular_expressions.dart" not in discovered
    assert "route_path.dart" not in discovered
    assert "atoa_public_key.dart" not in discovered
