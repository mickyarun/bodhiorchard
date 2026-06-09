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

"""Unit tests for Claude subscription (OAuth token) auth mode."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import HTTPException

from app.api.v1.settings_claude import _apply_credential
from app.core.encryption import encrypt_secret
from app.models.organization import Organization
from app.services.claude_env import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_HOST,
    AUTH_MODE_SUBSCRIPTION,
    apply_claude_auth_to_env,
)
from app.services.claude_guard.env_filter import build_claude_env

_API_KEY_VAR = "ANTHROPIC_API_KEY"
_OAUTH_VAR = "CLAUDE_CODE_OAUTH_TOKEN"


@pytest.fixture(autouse=True)
def _isolate_env() -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in (_API_KEY_VAR, _OAUTH_VAR)}
    os.environ.pop(_API_KEY_VAR, None)
    os.environ.pop(_OAUTH_VAR, None)
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _org(mode: str, secret: str | None) -> Organization:
    return Organization(
        claude_auth_mode=mode,
        claude_api_key_encrypted=encrypt_secret(secret) if secret else None,
    )


def test_subscription_injects_oauth_token_and_clears_api_key() -> None:
    os.environ[_API_KEY_VAR] = "sk-ant-leftover"  # a compose/api-key value would shadow the token
    apply_claude_auth_to_env(_org(AUTH_MODE_SUBSCRIPTION, "oat-token-xyz"))
    assert os.environ[_OAUTH_VAR] == "oat-token-xyz"
    assert _API_KEY_VAR not in os.environ


def test_api_key_injects_and_clears_oauth_token() -> None:
    os.environ[_OAUTH_VAR] = "oat-leftover"
    apply_claude_auth_to_env(_org(AUTH_MODE_API_KEY, "sk-ant-123"))
    assert os.environ[_API_KEY_VAR] == "sk-ant-123"
    assert _OAUTH_VAR not in os.environ


def test_host_mode_leaves_process_env_untouched() -> None:
    os.environ[_API_KEY_VAR] = "sk-ant-compose"
    apply_claude_auth_to_env(_org(AUTH_MODE_HOST, None))
    assert os.environ[_API_KEY_VAR] == "sk-ant-compose"
    assert _OAUTH_VAR not in os.environ


def test_apply_credential_stores_supplied_secret() -> None:
    org = _org(AUTH_MODE_SUBSCRIPTION, None)
    _apply_credential(org, supplied="oat-new", field="oauth_token", mode_unchanged=False)
    assert org.claude_api_key_encrypted is not None


def test_apply_credential_requires_secret_when_switching_modes() -> None:
    # Org had an API key; switching to subscription without a token must not
    # silently reinterpret the old API key as an OAuth token.
    org = _org(AUTH_MODE_API_KEY, "sk-ant-old")
    with pytest.raises(HTTPException):
        _apply_credential(org, supplied=None, field="oauth_token", mode_unchanged=False)


def test_apply_credential_keeps_existing_secret_same_mode() -> None:
    org = _org(AUTH_MODE_SUBSCRIPTION, "oat-existing")
    before = org.claude_api_key_encrypted
    _apply_credential(org, supplied=None, field="oauth_token", mode_unchanged=True)
    assert org.claude_api_key_encrypted == before


def test_apply_credential_rejects_blank_secret() -> None:
    org = _org(AUTH_MODE_API_KEY, None)
    with pytest.raises(HTTPException):
        _apply_credential(org, supplied="   ", field="api_key", mode_unchanged=False)


def test_build_claude_env_empty_value_drops_inherited_var() -> None:
    # An empty env_extra value clears an inherited var so a compose-level API
    # key can't shadow a subscription token in the check-claude test path.
    os.environ[_API_KEY_VAR] = "sk-ant-compose"
    env = build_claude_env({_OAUTH_VAR: "oat-token", _API_KEY_VAR: ""})
    assert env[_OAUTH_VAR] == "oat-token"
    assert _API_KEY_VAR not in env
