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

"""Settings read Full Docker's generated secrets when none are set."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AuthConfig, ColyseusConfig, HRCryptoConfig

LEGACY = "change-me-encryption-key"


def _secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (
        ("secret_key", "gen-secret"),
        ("encryption_key", "gen-key"),
        ("colyseus_bridge_secret", "gen-bridge"),
        ("hr_encryption_keys", "k1:gen-hr"),
    ):
        (tmp_path / name).write_text(value + "\n")
    monkeypatch.setenv("INSTANCE_SECRETS_DIR", str(tmp_path))


def test_full_docker_processes_use_the_generated_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _secrets(tmp_path, monkeypatch)
    monkeypatch.setenv("ENCRYPTION_KEY", "")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("COLYSEUS_BRIDGE_SECRET", "")
    auth = AuthConfig()
    assert (auth.secret_key, auth.encryption_key) == ("gen-secret", "gen-key")
    assert auth.encryption_key_previous == LEGACY
    assert ColyseusConfig().bridge_secret == "gen-bridge"


def test_a_set_key_wins_but_the_legacy_key_stays_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _secrets(tmp_path, monkeypatch)
    monkeypatch.setenv("ENCRYPTION_KEY", "my-key")
    monkeypatch.setenv("ENCRYPTION_KEY_PREVIOUS", f"older,{LEGACY}")
    auth = AuthConfig()
    assert auth.encryption_key == "my-key"
    assert auth.encryption_key_previous == f"older,{LEGACY}"


def test_outside_full_docker_nothing_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INSTANCE_SECRETS_DIR", raising=False)
    monkeypatch.setenv("ENCRYPTION_KEY", "")
    monkeypatch.setenv("ENCRYPTION_KEY_PREVIOUS", "")
    auth = AuthConfig()
    assert (auth.encryption_key, auth.encryption_key_previous) == ("", "")


def test_full_docker_processes_use_the_generated_hr_keyring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _secrets(tmp_path, monkeypatch)
    monkeypatch.setenv("HR_ENCRYPTION_KEYS", "")
    assert HRCryptoConfig().hr_encryption_keys.get_secret_value() == "k1:gen-hr"
    monkeypatch.setenv("HR_ENCRYPTION_KEYS", "mine:key")
    assert HRCryptoConfig().hr_encryption_keys.get_secret_value() == "mine:key"
    monkeypatch.delenv("INSTANCE_SECRETS_DIR")
    monkeypatch.setenv("HR_ENCRYPTION_KEYS", "")
    assert HRCryptoConfig().hr_encryption_keys.get_secret_value() == ""
