# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Function-bodied endpoint-map extractor.

Many TS frontends (notably Nuxt apps that wrap a single fetch helper)
declare their entire API surface as object methods that return template
strings, e.g.::

    const _employeeEndpoints = {
      GET_DETAILS(businessId: string, userId: string) {
        return `business/${businessId}/users/user/${userId}`;
      },
      LOG_OUT: (id: string) => `merchant/employee/${id}/logout-web`,
    };

The plain ``KEY: "/path"`` constants regex in :mod:`endpoint_extractor`
misses these entirely. This module recognises three shapes —

* method body: ``KEY(args) { ... return STRING ... }``
* arrow body: ``KEY: (args) => STRING``
* arrow with single param: ``KEY: arg => STRING``

— and yields ``(name, normalised_path)`` pairs. Paths missing a leading
slash are prefixed with one (the HTTP wrapper adds the API base at call
time, so internally we treat ``business/foo`` and ``/business/foo`` as
the same route shape).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

_STRING_LITERAL = (
    r"(?:"
    r"`(?P<bt>[^`]*)`"
    r"|'(?P<sq>[^'\\]*)'"
    r'|"(?P<dq>[^"\\]*)"'
    r")"
)

# Method head: ``KEY(<args>) [: RetType] {`` — locates the start of an
# endpoint-method body. We don't try to brace-match the body in the
# regex (real bodies often contain ``if`` blocks, optional chaining,
# nested helpers); instead, :func:`iter_endpoint_paths` scans the next
# ~2000 chars after each head for the first ``return <string-literal>``.
_METHOD_HEAD_RE = re.compile(
    rf"(?<![.\w])({_IDENT})\s*\(([^)]*)\)\s*(?::\s*[^{{]+?)?\s*\{{",
    re.DOTALL,
)
_RETURN_STRING_RE = re.compile(rf"\breturn\s+{_STRING_LITERAL}", re.DOTALL)
_METHOD_BODY_WINDOW = 2000

# Arrow body: ``KEY: (args) => STRING`` or ``KEY: arg => STRING``.
_ARROW_RE = re.compile(
    rf"(?<![.\w])({_IDENT})"
    r"\s*:\s*"
    rf"(?:\([^)]*\)|{_IDENT})"
    r"\s*=>\s*"
    rf"{_STRING_LITERAL}",
    re.DOTALL,
)

_TEMPLATE_PARAM_RE = re.compile(r"(\$\{" + _IDENT + r"\}|\$" + _IDENT + r"|:" + _IDENT + r")")


def iter_endpoint_paths(text: str) -> Iterator[tuple[str, str]]:
    """Yield ``(name, normalised_path)`` for every method/arrow endpoint.

    Names emitted here are merged into the same constants map used for
    plain ``KEY: "/path"`` lookups, so a downstream call site like
    ``api.get(_employeeEndpoints.GET_DETAILS(...))`` resolves the leaf
    identifier ``GET_DETAILS`` directly.

    Method bodies are scanned (rather than brace-matched in regex) so
    bodies with nested ``if``/``else`` branches still surface their
    return path. The first ``return <string-literal>`` after a method
    head wins — within one method, branches typically return
    structurally identical paths.
    """
    for m in _METHOD_HEAD_RE.finditer(text):
        name = m.group(1)
        body_start = m.end()
        window = text[body_start : body_start + _METHOD_BODY_WINDOW]
        ret = _RETURN_STRING_RE.search(window)
        if ret is None:
            continue
        raw = ret.group("bt") or ret.group("sq") or ret.group("dq")
        if raw is None:
            continue
        path = _normalise_endpoint_string(raw)
        if path:
            yield name, path
    for m in _ARROW_RE.finditer(text):
        name = m.group(1)
        raw = m.group("bt") or m.group("sq") or m.group("dq")
        if raw is None:
            continue
        path = _normalise_endpoint_string(raw)
        if path:
            yield name, path


_SKIP_DIRS = frozenset(
    {"node_modules", "dist", "build", "out", "coverage", "vendor", "__pycache__"}
)


def collect_endpoint_map(repo_root: Path) -> dict[str, str]:
    """Walk the repo and return ``{NAME: path}`` for every endpoint method.

    First match wins so a top-level declaration shadows a later
    re-export — same precedence rule as the plain constants map.
    Skips hidden, vendored, and build directories — see
    :data:`_SKIP_DIRS`.
    """
    out: dict[str, str] = {}
    if not repo_root.is_dir():
        return out
    for fp in repo_root.rglob("*"):
        if not fp.is_file() or fp.suffix not in (".ts", ".js", ".mjs"):
            continue
        try:
            rel_parts = fp.relative_to(repo_root).parts
        except ValueError:
            continue
        if any(part.startswith(".") or part in _SKIP_DIRS for part in rel_parts[:-1]):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, path in iter_endpoint_paths(text):
            if name not in out:
                out[name] = path
    return out


def _normalise_endpoint_string(raw: str) -> str | None:
    """Convert a raw return-string into a normalised API path.

    Rejects external URLs, JS pseudo-protocols (``javascript:void(0)``,
    ``mailto:``, ``tel:``, ``data:``, ``blob:``), and strings without
    any path separator. Prefixes a leading ``/`` when missing so the
    result lines up with backend route declarations.
    """
    s = raw.strip()
    if not s or _is_external_url(s) or _is_pseudo_protocol(s):
        return None
    # A real API path has at least one ``/``. Strings like
    # ``"javascript:void(0)"`` or ``"some-error-message"`` have none and
    # should never be promoted to routes by the leading-slash hack.
    if "/" not in s:
        return None
    if not s.startswith("/"):
        s = "/" + s
    s = s.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    s = _TEMPLATE_PARAM_RE.sub(":param", s)
    if not s or s == "/":
        return None
    return s


def _is_external_url(s: str) -> bool:
    """Rough check for fully-qualified URLs we never want as routes."""
    return s.startswith(("http://", "https://", "//", "ws://", "wss://"))


def _is_pseudo_protocol(s: str) -> bool:
    """Whether ``s`` starts with a non-route ``scheme:`` token.

    A scheme here is letters/digits before a ``:`` that appears before
    any ``/`` — covers ``javascript:``, ``mailto:``, ``tel:``, ``data:``,
    ``blob:``, ``file:``, ``chrome:``. Express-style ``/:param`` paths
    are unaffected because their ``:`` always comes after a ``/``.
    """
    colon = s.find(":")
    if colon <= 0:
        return False
    slash = s.find("/")
    if slash != -1 and slash < colon:
        return False
    return s[:colon].replace("-", "").replace("_", "").isalnum()
