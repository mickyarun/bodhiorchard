# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Signal + noise regression tests for each platform's ``design_globs``.

The core invariant: design-file discovery must pick up files whose names
clearly mark them as design content, and must skip generic code /
business-logic / localization files. These tests lock the tightened
scope so it can't silently regress.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.design_system_extractor import discover_design_files
from app.services.platforms import detect_platform, get_platform


def _names(repo: Path, platform) -> set[str]:  # type: ignore[no-untyped-def]
    return {p.name for p in discover_design_files(repo, platform)}


# ── Expo ──────────────────────────────────────────────────────────────────


def test_expo_rejects_api_endpoints_and_keys(tmp_path: Path) -> None:
    """Regression mirror of the Flutter bug: ``src/constants/**/*.ts`` used
    to sweep in api_endpoints.ts, route_paths.ts, keys.ts."""
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"expo": "^50.0.0"}}),
    )
    src = tmp_path / "src"
    (src / "constants").mkdir(parents=True)
    (src / "theme").mkdir()

    # Noise
    (src / "constants" / "api_endpoints.ts").write_text("export const BASE = ''")
    (src / "constants" / "route_paths.ts").write_text("export const ROUTES = {}")
    (src / "constants" / "keys.ts").write_text("export const API_KEY = ''")

    # Signal
    (src / "theme" / "colors.ts").write_text("export const colors = {}")
    (src / "theme" / "typography.ts").write_text("export const typography = {}")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "expo"
    names = _names(tmp_path, platform)
    assert "colors.ts" in names
    assert "typography.ts" in names
    assert "api_endpoints.ts" not in names
    assert "route_paths.ts" not in names
    assert "keys.ts" not in names


# ── Electron ──────────────────────────────────────────────────────────────


def test_electron_rejects_component_and_service_ts(tmp_path: Path) -> None:
    """Previously ``src/renderer/**/*.ts`` and ``src/main/**/*.ts`` matched
    every file — components, services, IPC handlers. Now scope to named
    theme modules only."""
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"electron": "^28.0.0"}}),
    )
    renderer = tmp_path / "src" / "renderer"
    (renderer / "components").mkdir(parents=True)
    (renderer / "services").mkdir()
    main_dir = tmp_path / "src" / "main"
    main_dir.mkdir(parents=True)

    # Noise
    (renderer / "components" / "Button.tsx").write_text("export const Button = () => null")
    (renderer / "services" / "ipc_service.ts").write_text("export const send = () => {}")
    (main_dir / "window_manager.ts").write_text("export const createWindow = () => {}")

    # Signal
    (renderer / "theme.ts").write_text("export const theme = {}")
    (tmp_path / "electron" / "theme.ts").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "electron" / "theme.ts").write_text("export const theme = {}")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "electron"
    names = _names(tmp_path, platform)
    assert "theme.ts" in names  # at least one
    assert "Button.tsx" not in names
    assert "ipc_service.ts" not in names
    assert "window_manager.ts" not in names


# ── Tauri ─────────────────────────────────────────────────────────────────


def test_tauri_rejects_random_component_css(tmp_path: Path) -> None:
    """Previously ``src/**/*.css`` matched every stylesheet including
    component-scoped ones; now scope is theme/global/variables/tokens."""
    (tmp_path / "src-tauri").mkdir()
    (tmp_path / "src-tauri" / "tauri.conf.json").write_text(
        json.dumps({"productName": "x"}),
    )
    src = tmp_path / "src"
    (src / "components" / "button").mkdir(parents=True)
    (src / "styles").mkdir()

    # Noise
    (src / "components" / "button" / "button.css").write_text(".btn { }")
    (src / "components" / "button" / "button.module.css").write_text(".btn { }")

    # Signal
    (src / "styles" / "tokens.css").write_text(":root { --primary: #000; }")
    (src / "global.css").write_text(":root { }")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "tauri"
    names = _names(tmp_path, platform)
    assert "tokens.css" in names
    assert "global.css" in names
    assert "button.css" not in names
    assert "button.module.css" not in names


# ── Capacitor ─────────────────────────────────────────────────────────────


def test_capacitor_rejects_component_css(tmp_path: Path) -> None:
    (tmp_path / "capacitor.config.ts").write_text("export default {}\n")
    src = tmp_path / "src"
    (src / "app" / "home").mkdir(parents=True)

    # Noise
    (src / "app" / "home" / "home.page.scss").write_text(".home { }")
    (src / "app" / "home" / "home.component.css").write_text(".x { }")

    # Signal
    (src / "variables.scss").write_text("$primary: #000;")
    (src / "tokens.css").write_text(":root {}")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "capacitor"
    names = _names(tmp_path, platform)
    assert "variables.scss" in names
    assert "tokens.css" in names
    assert "home.page.scss" not in names
    assert "home.component.css" not in names


# ── Qt ────────────────────────────────────────────────────────────────────


def test_qt_rejects_non_theme_qml(tmp_path: Path) -> None:
    """Previously ``**/*.qml`` matched every QML file in the app; now we
    only pick up QML whose name signals theme / palette content."""
    (tmp_path / "app.pro").write_text("QT += core gui\n")
    qml = tmp_path / "qml"
    qml.mkdir()

    # Noise
    (qml / "MainWindow.qml").write_text("import QtQuick\nItem {}")
    (qml / "LoginScreen.qml").write_text("import QtQuick\nItem {}")
    (qml / "SettingsDialog.qml").write_text("import QtQuick\nItem {}")

    # Signal
    (qml / "Theme.qml").write_text("import QtQuick\npragma Singleton\nQtObject {}")
    (qml / "Colors.qml").write_text("import QtQuick\nQtObject {}")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "qt"
    names = _names(tmp_path, platform)
    assert "Theme.qml" in names
    assert "Colors.qml" in names
    assert "MainWindow.qml" not in names
    assert "LoginScreen.qml" not in names
    assert "SettingsDialog.qml" not in names


# ── Blazor ────────────────────────────────────────────────────────────────


def test_blazor_rejects_program_cs_and_shared_components(tmp_path: Path) -> None:
    (tmp_path / "app.csproj").write_text(
        '<Project><ItemGroup>'
        '<PackageReference Include="Microsoft.AspNetCore.Components.Web"/>'
        '</ItemGroup></Project>',
    )
    (tmp_path / "App.razor").write_text("<Router/>")
    shared = tmp_path / "Shared"
    shared.mkdir()
    themes = tmp_path / "Themes"
    themes.mkdir()
    wwwroot = tmp_path / "wwwroot" / "css"
    wwwroot.mkdir(parents=True)

    # Noise
    (tmp_path / "Program.cs").write_text("var builder = ...;")
    (shared / "NavMenu.razor").write_text("<div/>")
    (shared / "LoginDisplay.razor").write_text("<div/>")

    # Signal
    (themes / "DarkTheme.razor").write_text("<div/>")
    (wwwroot / "app.css").write_text("body {}")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "blazor"
    names = _names(tmp_path, platform)
    assert "App.razor" in names
    assert "DarkTheme.razor" in names
    assert "app.css" in names
    assert "Program.cs" not in names
    assert "NavMenu.razor" not in names
    assert "LoginDisplay.razor" not in names


# ── WPF ───────────────────────────────────────────────────────────────────


def test_wpf_rejects_generic_resources_xaml(tmp_path: Path) -> None:
    (tmp_path / "App.csproj").write_text(
        "<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>",
    )
    (tmp_path / "App.xaml").write_text(
        '<Application xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"/>',
    )
    themes = tmp_path / "Themes"
    themes.mkdir()

    # Noise — generic "Resources" match used to sweep in localization dicts.
    (tmp_path / "LocalizationResources.xaml").write_text("<ResourceDictionary/>")
    (tmp_path / "StringResources.en.xaml").write_text("<ResourceDictionary/>")

    # Signal
    (tmp_path / "Colors.xaml").write_text("<ResourceDictionary/>")
    (themes / "DarkTheme.xaml").write_text("<ResourceDictionary/>")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "wpf"
    names = _names(tmp_path, platform)
    assert "App.xaml" in names
    assert "Colors.xaml" in names
    assert "DarkTheme.xaml" in names
    assert "LocalizationResources.xaml" not in names
    assert "StringResources.en.xaml" not in names


# ── Android native ────────────────────────────────────────────────────────


def test_android_excludes_strings_xml(tmp_path: Path) -> None:
    """strings.xml holds user-facing copy, not design tokens — it is
    deliberately excluded from the Android design globs."""
    app_main = tmp_path / "app" / "src" / "main"
    (app_main / "res" / "values").mkdir(parents=True)
    (app_main / "AndroidManifest.xml").write_text('<manifest package="x"/>')
    (tmp_path / "build.gradle.kts").write_text("plugins {}")

    (app_main / "res" / "values" / "colors.xml").write_text("<resources/>")
    (app_main / "res" / "values" / "strings.xml").write_text("<resources/>")
    (app_main / "res" / "values" / "themes.xml").write_text("<resources/>")

    platform = detect_platform(tmp_path)
    assert platform is not None and platform.slug == "android_native"
    names = _names(tmp_path, platform)
    assert "colors.xml" in names
    assert "themes.xml" in names
    assert "strings.xml" not in names


# ── Sanity: get_platform works for all tightened slugs ────────────────────


def test_all_tightened_platforms_still_resolvable() -> None:
    for slug in (
        "expo",
        "electron",
        "tauri",
        "capacitor",
        "qt",
        "blazor",
        "wpf",
        "android_native",
        "flutter",
    ):
        platform = get_platform(slug)
        assert platform.slug == slug
        assert platform.design_globs  # non-empty
