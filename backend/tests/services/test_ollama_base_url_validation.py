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

This suite once asserted a local-only bound: loopback, private ranges, or one
of two known hostnames. That bound was wrong for how the provider is actually
deployed — a shared or hosted Ollama behind a name is the normal case — so it
was lifted deliberately rather than eroded by exceptions. These tests now pin
what remains true, and each is written so that re-narrowing the rule would
fail loudly rather than silently break a working deployment:

* the metadata range stays refused,
* the output is regenerated, never echoed,
* a path prefix survives, because a gateway needs it,
* a credential in the URL is refused rather than quietly dropped.
"""

import pytest

from app.models.organization import AIProvider
from app.services.ai_runner.capabilities import capabilities_for
from app.services.ai_runner.capability_gate import provider_env
from app.services.ai_runner.ollama_models import (
    OLLAMA_API_KEY_ENV,
    OLLAMA_HOST_ENV,
    clean_base_url,
)


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


@pytest.mark.parametrize(
    "url",
    [
        "https://ollama.internal.example.com",
        "https://ollama.internal.example.com:8443",
        "http://ollama-gateway:11434",  # single-label name, e.g. a compose service
        "https://gpu-01.ml.corp.example.com:11434",
    ],
)
def test_hosted_endpoints_are_accepted(url: str) -> None:
    """The point of the widening: a team's shared endpoint is reached by name.

    Refusing these is what made the provider unusable for a deployment that
    cannot run a local model per machine.
    """
    assert clean_base_url(url) == url


def test_the_cloud_metadata_address_is_still_refused() -> None:
    """The one bound kept from the local-only rule: 169.254.169.254 serves
    instance credentials, and no Ollama server lives there — so refusing it
    costs nothing and removes the sharpest reason to bound the host at all."""
    with pytest.raises(ValueError, match="[Ll]ink-local"):
        clean_base_url("http://169.254.169.254")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://127.0.0.1", "not-a-url"])
def test_non_http_schemes_are_refused(url: str) -> None:
    with pytest.raises(ValueError, match="http"):
        clean_base_url(url)


def test_empty_means_use_the_default() -> None:
    assert clean_base_url(None) is None
    assert clean_base_url("   ") is None


def test_a_trailing_slash_is_normalised_away() -> None:
    """Callers join paths onto this, so a trailing slash would double up."""
    assert clean_base_url("http://localhost:11434/") == "http://localhost:11434"


def test_a_path_prefix_is_preserved() -> None:
    """A gateway commonly serves Ollama under a prefix rather than at the root.

    The earlier rule dropped the path, which turned a working gateway URL into
    requests against the gateway's own root — a 404 per call with nothing on
    screen connecting it to the address that was saved.
    """
    assert clean_base_url("https://gw.example.com/ollama") == "https://gw.example.com/ollama"
    assert clean_base_url("https://gw.example.com/a/b/") == "https://gw.example.com/a/b"


@pytest.mark.parametrize(
    "url", ["https://gw.example.com/../admin", "https://gw.example.com/a/./b"]
)
def test_a_traversing_path_is_refused(url: str) -> None:
    """A prefix that walks upward makes the saved address and the requested one
    disagree about where /api/tags lands."""
    with pytest.raises(ValueError, match=r"'\.'"):
        clean_base_url(url)


def test_embedded_credentials_are_refused_not_stripped() -> None:
    """Silently dropping them yields a 401 whose cause is invisible in the
    saved value; the message points at the field that does work."""
    with pytest.raises(ValueError, match="username and password"):
        clean_base_url("http://user:pass@localhost:11434")


def test_a_query_string_is_refused() -> None:
    with pytest.raises(ValueError, match="query string"):
        clean_base_url("http://localhost:11434/v1?x=1")


def test_ipv6_keeps_its_brackets_after_rebuild() -> None:
    """urlparse strips the brackets an IPv6 authority needs to be re-parsed."""
    assert clean_base_url("http://[::1]:11434") == "http://[::1]:11434"


def test_an_invalid_port_is_refused() -> None:
    with pytest.raises(ValueError, match="port"):
        clean_base_url("http://localhost:notaport")


@pytest.mark.parametrize(
    "ambiguous",
    [
        "http://127.000.000.001:11434",  # zero-padded octets
        "http://0x7f000001:11434",  # hex
    ],
)
def test_ambiguous_address_spellings_are_refused(ambiguous: str) -> None:
    """Validating one spelling and sending another is the shape of every
    parser-mismatch bypass: the checker reads 127.0.0.1 where the HTTP client
    reads something else. Neither parses as an address nor matches the hostname
    pattern, so both are refused outright — no spelling survives for the two to
    disagree about."""
    with pytest.raises(ValueError, match="not a valid host name"):
        clean_base_url(ambiguous)


def test_an_ipv6_address_is_rendered_in_canonical_form() -> None:
    assert clean_base_url("http://[0:0:0:0:0:0:0:1]:11434") == "http://[::1]:11434"


def test_an_uppercase_host_and_scheme_are_normalised() -> None:
    """Both come back regenerated rather than echoed."""
    assert clean_base_url("HTTP://LocalHost:11434") == "http://localhost:11434"


def test_provider_env_refuses_a_hostile_address_from_any_caller() -> None:
    """provider_env is the one point every address passes through — the org's
    saved value and the setup wizard's unsaved one, the latter from an
    unauthenticated endpoint that did not validate it. A check living only in
    the settings handler left that path open, which is how it was open.

    Falls back to the default rather than raising: this builds a run's
    environment and cannot report a bad request, and a run against the default
    fails visibly instead of quietly reaching somewhere it should not.
    """
    caps = capabilities_for(AIProvider.ollama)

    hostile = provider_env(caps, base_url="http://169.254.169.254", model="qwen3", thinking=False)
    assert hostile[OLLAMA_HOST_ENV] == caps.default_base_url

    allowed = provider_env(
        caps, base_url="https://ollama.example.com", model="qwen3", thinking=False
    )
    assert allowed[OLLAMA_HOST_ENV] == "https://ollama.example.com"


def test_provider_env_carries_a_token_only_when_there_is_one() -> None:
    """The token rides the per-run mapping, not os.environ — one process serves
    every org, and a shared endpoint can issue each a different credential."""
    caps = capabilities_for(AIProvider.ollama)

    without = provider_env(caps, base_url=None, model="qwen3", thinking=False)
    assert OLLAMA_API_KEY_ENV not in without

    blank = provider_env(caps, base_url=None, model="qwen3", thinking=False, api_key="   ")
    assert OLLAMA_API_KEY_ENV not in blank

    with_token = provider_env(caps, base_url=None, model="qwen3", thinking=False, api_key=" tok ")
    assert with_token[OLLAMA_API_KEY_ENV] == "tok"
