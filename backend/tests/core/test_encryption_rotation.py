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

"""ENCRYPTION_KEY rotation: old keys stay readable, new values use the new key."""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from app.config import settings
from app.core import encryption
from app.core.encryption import decrypt_secret, encrypt_secret, reencrypt_secret


def _use_keys(monkeypatch: pytest.MonkeyPatch, current: str, previous: str = "") -> None:
    monkeypatch.setattr(settings.auth, "encryption_key", current)
    monkeypatch.setattr(settings.auth, "encryption_key_previous", previous)


def test_old_values_stay_readable_and_move_to_the_new_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_keys(monkeypatch, "old-key")
    stored = encrypt_secret("xoxb-secret")
    _use_keys(monkeypatch, "new-key", "old-key")
    assert decrypt_secret(stored) == "xoxb-secret"
    fresh = reencrypt_secret(stored)
    assert fresh is not None and fresh.startswith("enc:")
    # Under the new key alone, without the old one.
    _use_keys(monkeypatch, "new-key")
    assert decrypt_secret(fresh) == "xoxb-secret"
    assert reencrypt_secret(fresh) is None


def test_plaintext_is_left_alone_and_unreadable_values_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_keys(monkeypatch, "a-key")
    stored = encrypt_secret("token")
    _use_keys(monkeypatch, "another-key")
    assert reencrypt_secret("legacy-plaintext") is None
    with pytest.raises(InvalidToken):
        reencrypt_secret(stored)


def test_keys_are_derived_once(monkeypatch: pytest.MonkeyPatch) -> None:
    encryption._derive.cache_clear()
    _use_keys(monkeypatch, "cached-key")
    for _ in range(3):
        encrypt_secret("x")
    assert encryption._derive.cache_info().misses == 1
