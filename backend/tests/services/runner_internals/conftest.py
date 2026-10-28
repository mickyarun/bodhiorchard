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

"""The no-database fakes, plus a clean slate for the credential env vars."""

from __future__ import annotations

import pytest

from tests.fakes.fixtures import event_recorder, external_guard, fake_claude, fake_embeddings
from tests.services.runner_internals.log_tap import LogTap, reset_cred_env

__all__ = ["clean_cred_env", "event_recorder", "external_guard", "fake_claude", "fake_embeddings"]


@pytest.fixture
def clean_cred_env(monkeypatch: pytest.MonkeyPatch) -> LogTap:
    """Unset the credential vars (restored after the test) and tap the credential loggers."""
    reset_cred_env(monkeypatch)
    tap = LogTap()
    tap.install(monkeypatch)
    return tap
