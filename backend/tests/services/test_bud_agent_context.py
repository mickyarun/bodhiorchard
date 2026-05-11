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

"""Unit tests for :func:`format_code_locations_section`.

The renderer is a pure function — it doesn't touch the DB, so these
tests are pure unit tests that stub the ORM objects with minimal
shape. They exist to lock in the contract every BUD-stage prompt
builder depends on (PM, Designer, TechPlanner, Code Reviewer, Tester).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.feature_to_repo import FeatureToRepoRole
from app.services.bud_agent_context import format_code_locations_section


@dataclass
class _StubLink:
    """Minimal stand-in for :class:`FeatureToRepo`."""

    role: FeatureToRepoRole
    code_locations: dict[str, list[str]] | None


@dataclass
class _StubFeature:
    """Minimal stand-in for :class:`Feature`."""

    feature_title: str
    repo_links: list[_StubLink]
    id: uuid.UUID = uuid.uuid4()


def _feature(title: str, locations: dict[str, list[str]] | None) -> _StubFeature:
    return _StubFeature(
        feature_title=title,
        repo_links=[_StubLink(role=FeatureToRepoRole.PRIMARY, code_locations=locations)],
    )


def test_empty_features_returns_empty_text_default() -> None:
    """No features → empty string by default so callers can drop the section."""
    assert format_code_locations_section([]) == ""


def test_empty_features_returns_explicit_empty_text() -> None:
    """``empty_text`` overrides the default ``""`` when callers want a fallback."""
    assert format_code_locations_section([], empty_text="(none)") == "(none)"


def test_renders_heading_features_and_layers() -> None:
    """Happy path: heading + per-feature block with each layer's paths."""
    features = [
        _feature(
            "Login flow",
            {"frontend": ["src/Login.vue"], "backend": ["api/auth.py"]},
        )
    ]
    out = format_code_locations_section(features)
    assert "## Existing code to read before planning" in out
    assert "### Login flow" in out
    assert "- **frontend**: src/Login.vue" in out
    assert "- **backend**: api/auth.py" in out


def test_layer_filter_drops_other_layers() -> None:
    """Only requested layers render — used by the designer (frontend-only)."""
    features = [
        _feature(
            "Login flow",
            {"frontend": ["src/Login.vue"], "backend": ["api/auth.py"]},
        )
    ]
    out = format_code_locations_section(features, layers=["frontend"])
    assert "frontend" in out and "src/Login.vue" in out
    assert "backend" not in out and "api/auth.py" not in out


def test_layer_filter_no_matches_drops_feature_block() -> None:
    """Feature whose layers don't intersect the filter contributes nothing."""
    features = [_feature("Batch job", {"batch": ["jobs/sync.py"]})]
    assert format_code_locations_section(features, layers=["frontend"]) == ""


def test_skips_features_without_primary_link() -> None:
    """Non-PRIMARY rows don't carry ``code_locations`` — skip them."""
    feat = _StubFeature(
        feature_title="Backend stub",
        repo_links=[_StubLink(role=FeatureToRepoRole.BACKEND, code_locations=None)],
    )
    assert format_code_locations_section([feat]) == ""


def test_appends_instruction_line() -> None:
    """An instruction is appended after the feature blocks when supplied."""
    features = [_feature("Login flow", {"frontend": ["src/Login.vue"]})]
    out = format_code_locations_section(features, instruction="Read these first.")
    assert out.rstrip().endswith("Read these first.")


def test_custom_heading_overrides_default() -> None:
    """Heading is a parameter — each builder picks the right one."""
    features = [_feature("Login flow", {"frontend": ["src/Login.vue"]})]
    out = format_code_locations_section(features, heading="## Linked feature surfaces")
    assert "## Linked feature surfaces" in out
    assert "## Existing code to read before planning" not in out
