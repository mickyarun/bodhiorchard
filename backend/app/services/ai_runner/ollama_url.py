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

"""Validates and normalises the address of an Ollama server.

Ollama started as a local-only provider, and this module once enforced that:
loopback, private ranges, or one of two known hostnames. That bound no longer
matches reality — teams run one shared Ollama behind a hostname, and the
deployment that drove this provider in the first place reaches it that way. So
a public host is now allowed, and the module's job narrows to producing a URL
the caller did not write character-for-character.

What survives the widening, and why:

* **Link-local *literals* are still refused.** ``169.254.169.254`` is the
  cloud metadata address; a server-side fetcher pointed at it reads instance
  credentials. No Ollama server lives there, so nothing legitimate is lost.
  Be precise about the limit of this: names are not resolved here, so a
  hostname that resolves into that range — ``metadata.google.internal``, or any
  attacker-controlled record — is **not** caught. Resolving at validation time
  would block the event loop and still prove nothing about the address used at
  request time, so the honest statement is that this refuses one spelling, not
  one destination.
* **The output is rebuilt from parsed parts**, never echoed. An address is
  re-rendered from its numeric form and a name from a matched pattern, so the
  string handed to the HTTP client is one this module produced. This closes
  parser-mismatch bypasses, where the validator and the client disagree about
  what ``0177.0.0.1`` means.
* **Credentials, query and fragment are rejected**, not stripped. Silently
  dropping a password from a pasted URL produces a 401 with no visible cause;
  saying so points at the token field instead.

Be clear-eyed about what this now is: an operator who can reach these settings
can point the backend at any host it can route to. That is inherent to a
configurable server address, and the settings endpoint is admin-gated. This
module bounds the *shape* of the destination, not the operator's intent.
"""

import ipaddress
import re
import socket
from urllib.parse import urlparse

# RFC 1123 host names: dot-separated labels of letters, digits and hyphens,
# each 1-63 characters and neither starting nor ending with a hyphen. Applied
# to the already-lowercased name, and it is a full match — so a name carrying
# anything else (a space, a slash, an encoded byte) never reaches the client.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$"
)

# One path segment of a base URL. Deliberately narrower than RFC 3986 allows:
# a gateway prefix is a plain path, and excluding percent-escapes keeps the
# saved value identical to the one that was checked.
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~-]+$")


def _parses_as_legacy_address(name: str) -> bool:
    """True if a lenient resolver would read this "name" as an IPv4 address.

    ``ipaddress`` is strict: it rejects ``0x7f000001`` and the zero-padded
    ``127.000.000.001``. The C resolver behind the HTTP client is not — both
    reach 127.0.0.1 there. So a value that fails the strict parse can still
    match the hostname pattern and then be resolved as an address, which is
    precisely the checker/client disagreement this module exists to prevent.

    ``inet_aton`` is the lenient parser itself, used here as an oracle. It only
    parses; it performs no lookup, so this cannot touch the network or block.
    """
    try:
        socket.inet_aton(name)
    except OSError:
        return False
    return True


def _safe_host(host: str) -> str:
    """Return this module's own rendering of ``host``, or raise ``ValueError``.

    Two shapes are accepted, and each is regenerated rather than passed
    through: an IP literal is parsed to an integer and rendered back from that
    integer, and a name is lowercased and required to match
    :data:`_HOSTNAME_RE` in full.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        name = host.lower()
        if not _HOSTNAME_RE.match(name) or _parses_as_legacy_address(name):
            raise ValueError(
                f"'{host}' is not a valid host name. Use a name like "
                "ollama.internal.example.com, an IP address, or localhost."
            ) from None
        return name

    if ip.is_link_local:
        raise ValueError(
            "Link-local addresses are not allowed — that range holds cloud "
            "instance metadata, not an Ollama server."
        )
    # Round-trip through the numeric form: the output derives from the parsed
    # number, never from the text that was parsed.
    rebuilt: ipaddress.IPv4Address | ipaddress.IPv6Address = (
        ipaddress.IPv6Address(int(ip)) if ip.version == 6 else ipaddress.IPv4Address(int(ip))
    )
    # An IPv6 authority needs back the brackets urlparse stripped.
    return f"[{rebuilt}]" if rebuilt.version == 6 else str(rebuilt)


def _safe_path(path: str) -> str:
    """Return a normalised path prefix (possibly empty), or raise ``ValueError``.

    Hosted deployments commonly expose Ollama under a prefix rather than at the
    root, so the path is preserved instead of discarded — dropping it would
    turn a working gateway URL into a 404 against the gateway's own root, with
    nothing on screen to explain why.

    ``.`` and ``..`` are refused: a prefix that walks upward would make the
    saved address and the requested one disagree about where ``/api/tags``
    lands, which is the same class of surprise the host check avoids.
    """
    trimmed = path.strip("/")
    if not trimmed:
        return ""
    segments = trimmed.split("/")
    for segment in segments:
        if segment in (".", ".."):
            raise ValueError("base_url path must not contain '.' or '..' segments")
        if not _PATH_SEGMENT_RE.match(segment):
            raise ValueError(f"base_url path segment '{segment}' contains unsupported characters")
    return "/" + "/".join(segments)


def clean_base_url(value: str | None) -> str | None:
    """Normalise a user-supplied server address; ``None`` means "use the default".

    Raises ``ValueError`` with a message written for whoever typed the address —
    it surfaces directly in the settings form.

    Every caller that accepts an address from a request runs it through here,
    including the ones that only probe and never persist: a probe is still a
    request the backend makes to a caller-chosen destination.
    """
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("base_url must include a host, e.g. http://localhost:11434")
    if parsed.username or parsed.password:
        raise ValueError(
            "Remove the username and password from the address. If the server "
            "needs a credential, choose the token auth mode and paste it there."
        )
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not include a query string or fragment")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("base_url has an invalid port") from None

    # Assembled from values this module owns: the scheme is one of two literals
    # chosen by comparison, the host comes back from ``_safe_host`` regenerated,
    # the port is an int, and the path has been matched segment by segment.
    scheme = "https" if parsed.scheme == "https" else "http"
    host = _safe_host(parsed.hostname)
    authority = f"{host}:{port}" if port else host
    return f"{scheme}://{authority}{_safe_path(parsed.path)}"
