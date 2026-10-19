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

"""Token typing, deactivation, and the production secret guard."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError

from app.config import AuthConfig, settings
from app.core import auth_deps
from app.core.security import create_access_token, create_refresh_token, verify_token

CLAIMS = {"sub": str(uuid.uuid4()), "org_id": str(uuid.uuid4())}


def test_refresh_token_is_not_an_access_token() -> None:
    assert verify_token(create_refresh_token(CLAIMS)) is None


def test_access_token_is_not_a_refresh_token() -> None:
    assert verify_token(create_access_token(CLAIMS), expected_type="refresh") is None


def test_each_token_verifies_as_its_own_type() -> None:
    assert verify_token(create_access_token(CLAIMS)) is not None
    assert verify_token(create_refresh_token(CLAIMS), expected_type="refresh") is not None


def test_legacy_untyped_token_still_counts_as_access() -> None:
    # Tokens minted before the ``type`` claim existed must not log everyone out.
    legacy = jwt.encode(
        {**CLAIMS, "exp": 4_102_444_800},
        settings.auth.secret_key,
        algorithm=settings.auth.algorithm,
    )
    assert verify_token(legacy) is not None
    assert verify_token(legacy, expected_type="refresh") is None


async def test_deactivated_user_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock(get_by_id=AsyncMock(return_value=SimpleNamespace(is_active=False)))
    monkeypatch.setattr(auth_deps, "UserRepository", MagicMock(return_value=repo))
    with pytest.raises(HTTPException) as excinfo:
        await auth_deps.get_current_user(token=create_access_token(CLAIMS), db=AsyncMock())
    assert excinfo.value.status_code == 401


@pytest.mark.parametrize("secret", ["", "change-me-in-production"])
def test_production_rejects_weak_secret_key(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", secret)
    monkeypatch.setenv("ENCRYPTION_KEY", "a-real-encryption-key")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        AuthConfig()


def test_production_accepts_real_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a-real-signing-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "a-real-encryption-key")
    assert AuthConfig().secret_key == "a-real-signing-key"


def test_dev_allows_default_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert AuthConfig(_env_file=None).secret_key  # type: ignore[call-arg]
