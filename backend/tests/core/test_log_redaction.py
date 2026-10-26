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

"""Outbound request logs keep their URLs but never the credentials in them."""

import logging

import pytest

from app.core.logging import _RedactQuerySecrets


def _log(message: str, *args: object) -> logging.LogRecord:
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, message, args, None)
    _RedactQuerySecrets().filter(record)
    return record


def test_giphy_api_key_is_redacted_and_the_rest_kept() -> None:
    record = _log(
        'HTTP Request: GET %s "HTTP/1.1 200 OK"',
        "https://api.giphy.com/v1/gifs/random?api_key=SECRET&tag=party&rating=g",
    )
    message = record.getMessage()
    assert "SECRET" not in message
    assert "api_key=***" in message
    assert "tag=party" in message and "rating=g" in message


@pytest.mark.parametrize("param", ["token", "access_token", "key", "secret", "sig"])
def test_other_credential_params_are_redacted(param: str) -> None:
    assert "hunter2" not in _log(f"GET https://x.example/a?{param}=hunter2").getMessage()


def test_messages_without_secrets_are_untouched() -> None:
    record = _log("GET %s", "https://slack.com/api/chat.postMessage")
    assert record.getMessage() == "GET https://slack.com/api/chat.postMessage"
    assert record.args == ("https://slack.com/api/chat.postMessage",)
