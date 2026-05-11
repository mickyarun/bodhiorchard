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

"""WebJsPlatform detection: matches package.json with known deps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.platforms import PlatformKind, detect_platform, get_platform
from app.services.platforms.web_js import WebJsPlatform

# Dependencies that are listed on WebJsPlatform but are also claimed by a
# more-specific platform at higher priority. Those deps deliberately resolve
# to the specific platform and are tested by the specific platform's file.
_PROMOTED_TO_OTHER_PLATFORM: frozenset[str] = frozenset({"@11ty/eleventy"})
_WEB_JS_ONLY_DEPS: list[str] = sorted(WebJsPlatform.dependencies - _PROMOTED_TO_OTHER_PLATFORM)


def _write_pkg(repo: Path, deps: dict[str, str], *, dev: bool = False) -> None:
    key = "devDependencies" if dev else "dependencies"
    (repo / "package.json").write_text(json.dumps({"name": "x", key: deps}))


@pytest.mark.parametrize("dep", _WEB_JS_ONLY_DEPS)
def test_detects_each_known_dep_in_dependencies(tmp_path: Path, dep: str) -> None:
    _write_pkg(tmp_path, {dep: "^1.0.0"})
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "web_js"
    assert platform.kind == PlatformKind.WEB


@pytest.mark.parametrize("dep", _WEB_JS_ONLY_DEPS)
def test_detects_each_known_dep_in_dev_dependencies(tmp_path: Path, dep: str) -> None:
    _write_pkg(tmp_path, {dep: "^1.0.0"}, dev=True)
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "web_js"


def test_backend_repo_without_package_json(tmp_path: Path) -> None:
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


def test_backend_repo_with_unrelated_package_json(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"express": "^4.0.0", "mongoose": "^7.0.0"})
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


def test_malformed_package_json_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{not valid json")
    platform = detect_platform(tmp_path)
    # Falls through to backend fallback; detection errors are swallowed.
    assert platform is not None
    assert platform.slug == "backend"


def test_web_js_globs_include_tailwind_and_vuetify() -> None:
    platform = get_platform("web_js")
    globs = platform.design_globs
    assert "tailwind.config.*" in globs
    assert "**/vuetify.config.*" in globs
    assert "package.json" in globs
