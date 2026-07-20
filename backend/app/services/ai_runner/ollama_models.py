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

Unlike the CLI providers, Ollama's usable models are a property of the user's
own machine, not of a table we ship — so they are read at runtime.

Everything here degrades to empty/None rather than raising: this is called
while rendering the settings page, and an unreachable Ollama must not 500 it.

Imports nothing from ``capabilities`` on purpose — that module imports
``ollama_probe`` from here, so the dependency has to stay one-directional.
Callers own presentation types; this returns plain strings.
"""

import asyncio
import ipaddress
import time
from collections.abc import Mapping
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
# Ollama's own variable for the server address.
OLLAMA_HOST_ENV = "OLLAMA_HOST"
# Ours, not Ollama's: the per-run channel carrying org-scoped settings down to
# the provider. Providers are handed a config, never the org, and os.environ
# would leak one org's choice into another's run.
OLLAMA_THINK_ENV = "OLLAMA_THINK"  # "1"/"0"
OLLAMA_MODEL_ENV = "OLLAMA_MODEL"

# Short: this runs inside a settings-page request. A slow or absent host must
# degrade quickly, not hold the page open.
_PROBE_TIMEOUT_S = 2.0
_LIST_BUDGET_S = 5.0
_CACHE_TTL_S = 60.0

# Ollama reports per-model capabilities; only models advertising this can drive
# agents. Without it a model answers in prose instead of calling a tool.
_TOOLS_CAPABILITY = "tools"

# Keyed by base_url. Every settings load would otherwise re-probe every model.
_model_cache: dict[str, tuple[float, list[str]]] = {}


# Hostnames that name the local machine across our documented deployments:
# the default, and the bridge Docker Desktop / Linux exposes for host-gateway.
_LOCAL_HOSTNAMES = frozenset({"localhost", "host.docker.internal"})


def _assert_reachable_host(host: str) -> None:
    """Reject an address the backend has no business being pointed at.

    The value reaches an HTTP client server-side, so whoever supplies it is
    choosing a destination on the backend's network — one the browser cannot
    reach itself. Left open, an authenticated member can sweep internal admin
    ports, or read a cloud instance's credentials off its metadata endpoint,
    using the model list as an oracle for what answered.

    Ollama is a local provider by definition ("runs against a server on your own
    machine"), so the honest bound is the machine and its private network. An IP
    literal must be loopback or private; a name must be one we know is local.
    Link-local is refused explicitly rather than by omission — 169.254.169.254
    is the metadata address, and it is the reason this check exists.

    Names are not resolved here: a DNS lookup would block the event loop, and
    resolving at validation time proves nothing about the address used at
    request time anyway. Anyone with a hostname for a LAN server can give its
    address instead, which is what the error says.
    """
    if host in _LOCAL_HOSTNAMES:
        return
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError(
            f"'{host}' is not a recognised local address. Use localhost, "
            "host.docker.internal, or the server's IP address on your network."
        ) from None
    if ip.is_link_local:
        raise ValueError(
            "Link-local addresses are not allowed — that range holds cloud "
            "instance metadata, not an Ollama server."
        )
    if not (ip.is_loopback or ip.is_private):
        raise ValueError(
            f"{host} is a public address. Ollama runs on your own machine or "
            "private network, so only loopback and private addresses are allowed."
        )


def clean_base_url(value: str | None) -> str | None:
    """Normalise a user-supplied server address; ``None`` means "use the default".

    Raises ``ValueError`` for anything that isn't an http/https URL pointing at
    a local or private host. Every caller that accepts this from a request has
    to run it through here — including the ones that only probe and never
    persist, since a probe is still a server-side request to a caller-chosen
    address. See :func:`_assert_reachable_host` for why the host is bounded.
    """
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("base_url must include a host, e.g. http://localhost:11434")
    _assert_reachable_host(parsed.hostname)
    return cleaned


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


def _remember(base_url: str, at: float, models: list[str]) -> list[str]:
    """Cache and return a probe result, successful or not."""
    _model_cache[base_url] = (at, models)
    return list(models)


async def _get_json(client: httpx.AsyncClient, url: str) -> dict[str, object] | None:
    """GET one JSON object, or None on any failure."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.info("ollama_request_failed", url=url, error=str(exc))
        return None
    return body if isinstance(body, dict) else None


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


async def list_tool_models(base_url: str) -> list[str]:
    """Installed models that can actually run agents, newest-listed first.

    Filters to tool-capable models: offering one without that capability would
    let a user pick a model that fails at the first tool call. Returns ``[]``
    on any failure — an unreachable host means "nothing to offer", not an error.
    """
    base_url = base_url.rstrip("/")
    cached = _model_cache.get(base_url)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL_S:
        return list(cached[1])

    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
        tags = await _get_json(client, f"{base_url}/api/tags")
        if tags is None:
            # Cache the failure too. This is probed on every settings load, for
            # every org — including ones on another provider entirely. A host
            # that drops packets rather than refusing costs the full timeout,
            # and without this that is paid on every page view forever.
            return _remember(base_url, now, [])
        raw = tags.get("models")
        names = [
            m["name"]
            for m in (raw if isinstance(raw, list) else [])
            if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"]
        ]
        if not names:
            return _remember(base_url, now, [])
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
            return _remember(base_url, now, [])

    for outcome in checked:
        if isinstance(outcome, BaseException):
            # _model_has_tools catches its own HTTP/OS/parse errors, so anything
            # here is unexpected — a model would vanish from the dropdown with
            # no trace of why.
            logger.warning("ollama_show_unexpected_error", error=str(outcome))
    capable = [r for r in checked if isinstance(r, str)]
    _remember(base_url, now, capable)
    logger.info(
        "ollama_models_listed", base_url=base_url, installed=len(names), tool_capable=len(capable)
    )
    return list(capable)


async def ollama_probe(env: Mapping[str, str] | None) -> str | None:
    """Liveness probe: a version string if the host answers, else None.

    Stands in for the CLI providers' ``version_cmd`` — there is no binary to
    invoke, so reachability is the equivalent signal.
    """
    base_url = base_url_from_env(env)
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
        body = await _get_json(client, f"{base_url}/api/version")
    if body is None:
        return None
    version = body.get("version")
    return f"Ollama {version}" if isinstance(version, str) else "Ollama"


def clear_model_cache() -> None:
    """Drop the TTL cache. For tests, and for a base_url change."""
    _model_cache.clear()
