# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Integration tests: platform-aware file discovery in the extractor.

These tests exercise only the synchronous discovery / hashing paths — they
do NOT invoke the LLM or touch the database.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.design_system_extractor import (
    compute_hash,
    discover_design_files,
    read_discovered_files,
)
from app.services.platforms import detect_platform, get_platform


def test_web_js_repo_discovers_tailwind_and_theme(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"vue": "^3", "vuetify": "^3"}}),
    )
    (tmp_path / "tailwind.config.js").write_text("module.exports = {}\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "theme.ts").write_text("export const theme = {}\n")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "web_js"

    discovered = discover_design_files(tmp_path, platform)
    names = {p.name for p in discovered}
    assert "tailwind.config.js" in names
    assert "theme.ts" in names
    assert "package.json" in names


def test_flutter_repo_discovers_theme_dart(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: demo\nflutter:\n  uses-material-design: true\n",
    )
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "theme").mkdir()
    (tmp_path / "lib" / "theme" / "app_theme.dart").write_text("class AppTheme {}\n")
    (tmp_path / "lib" / "colors.dart").write_text("class Colors {}\n")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "flutter"

    discovered = discover_design_files(tmp_path, platform)
    names = {p.name for p in discovered}
    assert "app_theme.dart" in names
    assert "colors.dart" in names
    assert "pubspec.yaml" in names


def test_android_repo_discovers_colors_xml(tmp_path: Path) -> None:
    (tmp_path / "app" / "src" / "main").mkdir(parents=True)
    (tmp_path / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
        '<manifest package="com.example.app"/>',
    )
    (tmp_path / "build.gradle.kts").write_text("plugins {}\n")
    (tmp_path / "app" / "src" / "main" / "res" / "values").mkdir(parents=True)
    (tmp_path / "app" / "src" / "main" / "res" / "values" / "colors.xml").write_text(
        '<resources><color name="primary">#6200EE</color></resources>',
    )

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "android_native"

    discovered = discover_design_files(tmp_path, platform)
    assert any(p.name == "colors.xml" for p in discovered)


def test_backend_platform_discovers_nothing(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hi')\n")
    platform = get_platform("backend")
    discovered = discover_design_files(tmp_path, platform)
    assert discovered == []


def test_platform_skip_dirs_are_respected(tmp_path: Path) -> None:
    # web_js skip_dirs include node_modules (via DEFAULT_SKIP_DIRS).
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"vue": "^3"}}),
    )
    (tmp_path / "node_modules" / "junk").mkdir(parents=True)
    (tmp_path / "node_modules" / "junk" / "theme.ts").write_text("export {}\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "theme.ts").write_text("export const theme = {}\n")

    platform = detect_platform(tmp_path)
    assert platform is not None
    discovered = discover_design_files(tmp_path, platform)
    paths = [str(p) for p in discovered]
    assert not any("node_modules" in p for p in paths)


def test_hash_is_stable_across_runs(tmp_path: Path) -> None:
    (tmp_path / "tokens.json").write_text(
        json.dumps({"color": {"primary": "#000"}}, sort_keys=True),
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    discovered_a = discover_design_files(tmp_path, platform)
    discovered_b = discover_design_files(tmp_path, platform)
    assert compute_hash(read_discovered_files(discovered_a)) == compute_hash(
        read_discovered_files(discovered_b),
    )
