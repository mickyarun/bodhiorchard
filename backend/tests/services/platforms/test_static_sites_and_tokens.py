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

"""Detection tests for static sites + design-tokens-only repositories."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.platforms import PlatformKind, detect_platform

# ── Shopify Liquid ────────────────────────────────────────────────────────


def test_shopify_liquid_requires_both_schema_and_template(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings_schema.json").write_text("[]")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "index.liquid").write_text("{{ product }}")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "shopify_liquid"
    assert platform.kind == PlatformKind.STATIC_SITE


def test_shopify_schema_without_templates_does_not_match(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings_schema.json").write_text("[]")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


# ── Jekyll ────────────────────────────────────────────────────────────────


def test_jekyll_via_sass_directory(tmp_path: Path) -> None:
    (tmp_path / "_config.yml").write_text("title: Demo\n")
    (tmp_path / "_sass").mkdir()
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "jekyll"


def test_jekyll_via_layouts_directory(tmp_path: Path) -> None:
    (tmp_path / "_config.yml").write_text("title: Demo\n")
    (tmp_path / "_layouts").mkdir()
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "jekyll"


# ── Hugo ──────────────────────────────────────────────────────────────────


def test_hugo_via_hugo_toml(tmp_path: Path) -> None:
    (tmp_path / "hugo.toml").write_text('baseURL = "/"\n')
    (tmp_path / "content").mkdir()
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "hugo"


def test_hugo_config_without_content_dir_rejects(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text('baseURL = "/"\n')
    platform = detect_platform(tmp_path)
    assert platform is not None
    # Generic config.toml without content/ — fall through.
    assert platform.slug == "backend"


# ── Eleventy ──────────────────────────────────────────────────────────────


def test_eleventy_via_config_file(tmp_path: Path) -> None:
    (tmp_path / ".eleventy.js").write_text("module.exports = () => ({})\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "eleventy"


# ── Design Tokens ─────────────────────────────────────────────────────────


def test_design_tokens_via_tokens_json(tmp_path: Path) -> None:
    (tmp_path / "tokens.json").write_text(
        json.dumps({"color": {"primary": {"$value": "#0070f3"}}}),
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "design_tokens"
    assert platform.kind == PlatformKind.TOKENS_ONLY


def test_design_tokens_via_style_dictionary_config(tmp_path: Path) -> None:
    (tmp_path / "style-dictionary.config.js").write_text("module.exports = {}\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "design_tokens"


def test_design_tokens_via_tokens_directory(tmp_path: Path) -> None:
    (tmp_path / "tokens").mkdir()
    (tmp_path / "tokens" / "colors.json").write_text("{}")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "design_tokens"


def test_bare_config_json_is_not_claimed_as_design_tokens(tmp_path: Path) -> None:
    # Regression: ``config.json`` at the root is too generic a filename to
    # classify as Style Dictionary — would false-positive on Electron,
    # Storybook, and countless backend repos.
    (tmp_path / "config.json").write_text(json.dumps({"port": 3000}))
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"
