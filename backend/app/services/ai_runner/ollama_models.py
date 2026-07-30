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

"""Discovery against a live Ollama host: which models exist, and can it run?

Unlike the CLI providers, Ollama's usable models are a property of the server
the org points at — their own machine, or a shared/hosted endpoint — not of a
table we ship, so they are read at runtime.

Everything here degrades to empty/None rather than raising: this is called
while rendering the settings page, and an unreachable Ollama must not 500 it.

Imports nothing from ``capabilities`` on purpose — that module imports
``ollama_probe`` from here, so the dependency has to stay one-directional.
Callers own presentation types; this returns plain strings.
"""

import asyncio
import ssl
import time
from collections.abc import Mapping
from functools import lru_cache

import httpx
import structlog

from app.services.ai_runner.capability_types import ProbeResult
from app.services.ai_runner.ollama_url import clean_base_url

__all__ = [
    "OLLAMA_API_KEY_ENV",
    "OLLAMA_DEFAULT_BASE_URL",
    "OLLAMA_HOST_ENV",
    "OLLAMA_MODEL_ENV",
    "OLLAMA_THINK_ENV",
    "api_key_from_env",
    "auth_headers",
    "base_url_from_env",
    "clean_base_url",
    "clear_model_cache",
    "list_tool_models",
    "ollama_probe",
    "verify_context",
]

logger = structlog.get_logger(__name__)

OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
# Ollama's own variable for the server address.
OLLAMA_HOST_ENV = "OLLAMA_HOST"
# Ours, not Ollama's: the per-run channel carrying org-scoped settings down to
# the provider. Providers are handed a config, never the org, and os.environ
# would leak one org's choice into another's run.
OLLAMA_THINK_ENV = "OLLAMA_THINK"  # "1"/"0"
OLLAMA_MODEL_ENV = "OLLAMA_MODEL"
# Bearer token for a hosted endpoint. Empty/absent for a local server, which
# has no auth at all — that is the difference between the two auth modes.
OLLAMA_API_KEY_ENV = "OLLAMA_API_KEY"

# Short: this runs inside a settings-page request. A slow or absent host must
# degrade quickly, not hold the page open. Roomier than a purely local server
# needs, because a hosted endpoint pays a TLS handshake and a network hop
# before answering — at 2s a working remote gateway looked like a dead one.
# The TTL cache keeps a genuinely dead host from costing this on every load.
_PROBE_TIMEOUT_S = 5.0
_LIST_BUDGET_S = 12.0
_CACHE_TTL_S = 60.0

# Ollama reports per-model capabilities; only models advertising this can drive
# agents. Without it a model answers in prose instead of calling a tool.
_TOOLS_CAPABILITY = "tools"

# Every settings load would otherwise re-probe every model. Keyed by address
# *and* token: two orgs can share a hosted endpoint while being entitled to
# different models, and a cache keyed on the address alone would serve the
# first org's answer to the second.
_model_cache: dict[tuple[str, str], tuple[float, list[str]]] = {}


@lru_cache(maxsize=1)
def verify_context() -> ssl.SSLContext:
    """TLS trust for Ollama requests, backed by the operating system's store.

    ``httpx`` verifies against ``certifi`` — a fixed list of *public* CAs. A
    hosted Ollama is commonly reached through an internal gateway whose
    certificate is signed by a company CA: present in the machine's own trust
    store (IT pushes it there), absent from certifi. So httpx rejects it as a
    "self-signed certificate in certificate chain" while every browser and CLI
    on the same box accepts it — which is exactly the report from the field,
    and exactly why the stdlib readiness script (which uses this same context)
    succeeded where the backend did not.

    ``create_default_context`` loads the OS store, so a policy-installed CA is
    trusted without configuration, and it still honours ``SSL_CERT_FILE`` for a
    container that must be pointed at a specific CA bundle. Verification stays
    on: this restores trust the machine already extends, it does not disable it.

    Cached because parsing the whole store on every request would be wasteful;
    a process restart re-reads it.
    """
    return ssl.create_default_context()


def auth_headers(api_key: str | None) -> dict[str, str]:
    """Bearer header for a hosted endpoint, or ``{}`` for a local one.

    A local Ollama has no auth and rejects nothing, so sending an empty bearer
    would be noise at best; hosted gateways in front of Ollama expect the
    standard header.
    """
    key = (api_key or "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def api_key_from_env(env: Mapping[str, str] | None) -> str | None:
    """Read the run's bearer token, or None when the server needs no auth."""
    if not env:
        return None
    return (env.get(OLLAMA_API_KEY_ENV) or "").strip() or None


def base_url_from_env(env: Mapping[str, str] | None) -> str:
    """Resolve the Ollama host from a per-run env mapping.

    Read from the run's own mapping rather than ``os.environ`` so two orgs on
    different hosts cannot clobber each other in a shared process.
    """
    if env:
        value = (env.get(OLLAMA_HOST_ENV) or "").strip()
        if value:
            return value.rstrip("/")
    return OLLAMA_DEFAULT_BASE_URL


def _remember(key: tuple[str, str], at: float, models: list[str]) -> list[str]:
    """Cache and return a probe result, successful or not."""
    _model_cache[key] = (at, models)
    return list(models)


async def _get_json_with_reason(
    client: httpx.AsyncClient, url: str
) -> tuple[dict[str, object] | None, str | None]:
    """GET one JSON object; on failure return why, in the operator's terms.

    The reason exists because every failure here otherwise collapses to "no
    server". A hosted endpoint that answers and rejects the token is a live
    server with a wrong setting, and saying "install Ollama" sends the reader
    to the wrong page.
    """
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        body = resp.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        logger.info("ollama_request_failed", url=url, status=code)
        if code in (401, 403):
            return None, (
                f"The server at {url.rsplit('/api/', 1)[0]} rejected the credential "
                f"(HTTP {code}). Check the token, or choose no authentication for a "
                "server that needs none."
            )
        if code == 404:
            return None, (
                f"HTTP 404 from {url}. If the endpoint serves Ollama under a path "
                "prefix, include it in the server address — and note it must speak "
                "Ollama's own API, not an OpenAI-compatible one."
            )
        return None, f"The server answered HTTP {code}."
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.info("ollama_request_failed", url=url, error=str(exc))
        # A TLS trust failure is otherwise invisible: the list comes back empty
        # and the settings page says "install a model", pointing at the wrong
        # thing entirely. Name it, because the fix is to trust the CA where the
        # backend runs, not to touch the server.
        if "certificate" in str(exc).lower():
            return None, (
                "The server's TLS certificate is not trusted where the backend "
                "runs. If it uses an internal or self-signed certificate, install "
                "that CA on the host (or set SSL_CERT_FILE to its bundle in Docker)."
            )
        return None, None
    return (body if isinstance(body, dict) else None), None


async def _get_json(client: httpx.AsyncClient, url: str) -> dict[str, object] | None:
    """GET one JSON object, or None on any failure.

    ``url`` is built from an address that has been through
    :func:`clean_base_url`, either when it was saved or in
    ``capability_gate.provider_env`` — the point every caller converges on, so
    the guarantee does not rest on each one remembering. That validation
    regenerates the address from its parsed parts, so the string sent is one we
    produced rather than one the caller wrote, and refuses the link-local range
    that holds cloud instance metadata.

    It no longer confines the destination to the local machine: a shared or
    hosted Ollama is the deployment this provider now serves, so the operator
    chooses the host. CodeQL reports ``py/partial-ssrf`` here, and with that
    widening the report is a fair description of the design rather than a false
    positive. What limits it is that choosing the address takes
    ``integrations:configure`` — not that the destination is bounded, and not
    the link-local refusal, which catches that range written as an address but
    not a hostname resolving into it.
    """
    body, _ = await _get_json_with_reason(client, url)
    return body


async def _model_has_tools(client: httpx.AsyncClient, base_url: str, name: str) -> str | None:
    """Return ``name`` if the model advertises tool support, else None."""
    try:
        resp = await client.post(f"{base_url}/api/show", json={"model": name})
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.info("ollama_show_failed", model=name, error=str(exc))
        return None
    if not isinstance(body, dict):
        return None
    capabilities = body.get("capabilities")
    if isinstance(capabilities, list) and _TOOLS_CAPABILITY in capabilities:
        return name
    return None


async def list_tool_models(base_url: str, api_key: str | None = None) -> list[str]:
    """Installed models that can actually run agents, newest-listed first.

    Filters to tool-capable models: offering one without that capability would
    let a user pick a model that fails at the first tool call. Returns ``[]``
    on any failure — an unreachable host means "nothing to offer", not an error.
    A hosted endpoint that rejects the token answers the same way, which is why
    the settings page pairs an empty list with the address, not a bare "none".
    """
    base_url = base_url.rstrip("/")
    key = (base_url, api_key or "")
    cached = _model_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL_S:
        return list(cached[1])

    async with httpx.AsyncClient(
        timeout=_PROBE_TIMEOUT_S, headers=auth_headers(api_key), verify=verify_context()
    ) as client:
        tags = await _get_json(client, f"{base_url}/api/tags")
        if tags is None:
            # Cache the failure too. This is probed on every settings load, for
            # every org — including ones on another provider entirely. A host
            # that drops packets rather than refusing costs the full timeout,
            # and without this that is paid on every page view forever.
            return _remember(key, now, [])
        raw = tags.get("models")
        names = [
            m["name"]
            for m in (raw if isinstance(raw, list) else [])
            if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"]
        ]
        if not names:
            return _remember(key, now, [])
        try:
            checked = await asyncio.wait_for(
                asyncio.gather(
                    *(_model_has_tools(client, base_url, n) for n in names),
                    return_exceptions=True,
                ),
                timeout=_LIST_BUDGET_S,
            )
        except (TimeoutError, asyncio.CancelledError):
            logger.info("ollama_list_models_timeout", base_url=base_url, count=len(names))
            return _remember(key, now, [])

    for outcome in checked:
        if isinstance(outcome, BaseException):
            # _model_has_tools catches its own HTTP/OS/parse errors, so anything
            # here is unexpected — a model would vanish from the dropdown with
            # no trace of why.
            logger.warning("ollama_show_unexpected_error", error=str(outcome))
    capable = [r for r in checked if isinstance(r, str)]
    _remember(key, now, capable)
    logger.info(
        "ollama_models_listed", base_url=base_url, installed=len(names), tool_capable=len(capable)
    )
    return list(capable)


async def ollama_probe(env: Mapping[str, str] | None) -> ProbeResult:
    """Liveness probe: the server's version, or why it could not be read.

    Stands in for the CLI providers' ``version_cmd`` — there is no binary to
    invoke, so reachability is the equivalent signal.
    """
    base_url = base_url_from_env(env)
    async with httpx.AsyncClient(
        timeout=_PROBE_TIMEOUT_S,
        headers=auth_headers(api_key_from_env(env)),
        verify=verify_context(),
    ) as client:
        body, reason = await _get_json_with_reason(client, f"{base_url}/api/version")
    if body is None:
        return ProbeResult(version=None, error=reason)
    version = body.get("version")
    return ProbeResult(f"Ollama {version}" if isinstance(version, str) else "Ollama")


def clear_model_cache() -> None:
    """Drop the TTL cache. For tests, and for a base_url change."""
    _model_cache.clear()
