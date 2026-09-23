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

"""Tests for the per-org bug-attachment limits and their resolver."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.settings import MAX_CONFIGURABLE_ATTACHMENT_MB, BugAttachmentSettings
from app.services.org_settings import get_bug_attachment_settings


def test_defaults_match_the_shipped_limits() -> None:
    """A fresh org gets 10 MB per file and 10 files per bug."""
    cfg = BugAttachmentSettings()
    assert cfg.max_file_mb == 10
    assert cfg.max_files_per_bug == 10


def test_camel_case_aliases_round_trip() -> None:
    """The frontend's camelCase payload populates the snake_case fields."""
    cfg = BugAttachmentSettings(maxFileMb=5, maxFilesPerBug=3)
    assert (cfg.max_file_mb, cfg.max_files_per_bug) == (5, 3)
    assert cfg.model_dump() == {"max_file_mb": 5, "max_files_per_bug": 3}


def test_size_cannot_exceed_the_proxy_ceiling() -> None:
    """An org cannot save a limit its own edge proxy would reject.

    ``client_max_body_size`` in ``frontend/nginx.conf.template`` is a
    deployment-wide static; a per-org limit above it would fail at the
    proxy with an HTML 413 the UI cannot render.
    """
    with pytest.raises(ValidationError):
        BugAttachmentSettings(max_file_mb=MAX_CONFIGURABLE_ATTACHMENT_MB + 1)


@pytest.mark.parametrize("payload", [{"max_file_mb": 0}, {"max_files_per_bug": 0}])
def test_limits_must_be_positive(payload: dict[str, int]) -> None:
    """Zero would disable attachments by accident rather than by intent."""
    with pytest.raises(ValidationError):
        BugAttachmentSettings(**payload)


# ── Resolver ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("config", [None, {}, {"bug_attachments": None}, {"bug_attachments": {}}])
def test_resolver_fills_defaults_for_missing_sections(config: dict | None) -> None:
    """An org that never opened the settings page behaves like the defaults."""
    cfg = get_bug_attachment_settings(config)
    assert (cfg.max_file_mb, cfg.max_files_per_bug) == (10, 10)


def test_resolver_reads_saved_values() -> None:
    """Saved limits are what callers get back."""
    cfg = get_bug_attachment_settings({"bug_attachments": {"max_file_mb": 5}})
    assert cfg.max_file_mb == 5
    # Partial sections still fill the untouched field from the default.
    assert cfg.max_files_per_bug == 10


def test_resolver_falls_back_on_corrupt_config() -> None:
    """A bad JSONB section returns defaults instead of 500ing an upload."""
    cfg = get_bug_attachment_settings({"bug_attachments": {"max_file_mb": 9_999}})
    assert (cfg.max_file_mb, cfg.max_files_per_bug) == (10, 10)
