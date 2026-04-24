# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Detection tests for cross-platform mobile + web-wrapper desktop platforms.

Bundled into one file because each platform needs the same tiny fixture
shape (``package.json`` + one config file).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.platforms import PlatformKind, detect_platform


def _write_pkg(repo: Path, deps: dict[str, str]) -> None:
    (repo / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": deps}),
    )


# ── React Native ──────────────────────────────────────────────────────────


def test_react_native_requires_both_dep_and_metro_config(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"react-native": "^0.73.0"})
    (tmp_path / "metro.config.js").write_text("module.exports = {}\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "react_native"
    assert platform.kind == PlatformKind.MOBILE_CROSS


def test_react_native_without_metro_config_does_not_match(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"react-native": "^0.73.0"})
    platform = detect_platform(tmp_path)
    assert platform is not None
    # Falls through — could be a lib consumer or deeper project.
    assert platform.slug != "react_native"


# ── Expo ──────────────────────────────────────────────────────────────────


def test_expo_via_package_dep(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"expo": "^50.0.0"})
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "expo"


def test_expo_via_app_json_key(tmp_path: Path) -> None:
    (tmp_path / "app.json").write_text(json.dumps({"expo": {"name": "demo"}}))
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "expo"


def test_expo_via_app_config_ts(tmp_path: Path) -> None:
    (tmp_path / "app.config.ts").write_text("export default { name: 'x' }\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "expo"


# ── Ionic ─────────────────────────────────────────────────────────────────


def test_ionic_config_json(tmp_path: Path) -> None:
    (tmp_path / "ionic.config.json").write_text(json.dumps({"name": "x", "type": "react"}))
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "ionic"


# ── Capacitor ─────────────────────────────────────────────────────────────


def test_capacitor_config_ts(tmp_path: Path) -> None:
    (tmp_path / "capacitor.config.ts").write_text("export default { appId: 'x' }\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "capacitor"


def test_ionic_plus_capacitor_prefers_ionic(tmp_path: Path) -> None:
    (tmp_path / "ionic.config.json").write_text(json.dumps({"name": "x"}))
    (tmp_path / "capacitor.config.ts").write_text("export default {}\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "ionic"  # higher priority


# ── Electron ──────────────────────────────────────────────────────────────


def test_electron(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"electron": "^28.0.0"})
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "electron"
    assert platform.kind == PlatformKind.DESKTOP


# ── Tauri ─────────────────────────────────────────────────────────────────


def test_tauri(tmp_path: Path) -> None:
    (tmp_path / "src-tauri").mkdir()
    (tmp_path / "src-tauri" / "tauri.conf.json").write_text(json.dumps({"productName": "x"}))
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "tauri"
    assert platform.kind == PlatformKind.DESKTOP
