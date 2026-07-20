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

"""The server address decides where the backend sends a request.

Whoever supplies it is choosing a destination on the backend's network, not
their own — so an unbounded value lets an authenticated member sweep internal
ports or read a cloud instance's credentials off the metadata endpoint, using
the returned model list as an oracle for what answered. A scheme check alone
does not stop that: ``http://169.254.169.254`` passes it.

Ollama is local by definition, so the bound is the machine and its private
network. Both the saved address and the merely-probed one go through here; a
guard on only the persisted path just moves the request to the probe.
"""

import pytest

from app.services.ai_runner.ollama_models import clean_base_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://[::1]:11434",
        "http://host.docker.internal:11434",  # Docker Desktop / host-gateway
        "http://192.168.1.50:11434",  # Ollama on another LAN machine
        "http://10.0.0.7:11434",
        "https://172.16.4.2:11434",
    ],
)
def test_local_and_private_addresses_are_accepted(url: str) -> None:
    assert clean_base_url(url) == url


def test_the_cloud_metadata_address_is_refused() -> None:
    """The reason this check exists: 169.254.169.254 serves instance
    credentials, and a probe against it would report success as 'no models'."""
    with pytest.raises(ValueError, match="[Ll]ink-local"):
        clean_base_url("http://169.254.169.254")


@pytest.mark.parametrize(
    "url",
    [
        "http://8.8.8.8:11434",
        "https://example.com/api",
    ],
)
def test_public_addresses_are_refused(url: str) -> None:
    with pytest.raises(ValueError, match="public|local"):
        clean_base_url(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://127.0.0.1", "not-a-url"])
def test_non_http_schemes_are_refused(url: str) -> None:
    with pytest.raises(ValueError, match="http"):
        clean_base_url(url)


def test_an_unknown_hostname_is_refused_rather_than_resolved() -> None:
    """Names are not resolved: a lookup would block the loop, and what it
    resolves to at validation time proves nothing about request time."""
    with pytest.raises(ValueError, match="not a recognised local address"):
        clean_base_url("http://internal-admin.corp:8080")


def test_empty_means_use_the_default() -> None:
    assert clean_base_url(None) is None
    assert clean_base_url("   ") is None


def test_a_trailing_slash_is_normalised_away() -> None:
    """Callers join paths onto this, so a trailing slash would double up."""
    assert clean_base_url("http://localhost:11434/") == "http://localhost:11434"
