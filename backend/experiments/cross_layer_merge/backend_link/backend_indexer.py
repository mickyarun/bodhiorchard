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

"""Generic backend route indexer for any HTTP server repo.

Walks each backend repo's source tree once and extracts route declarations
across common frameworks. Recognised today:

* TypeScript / JavaScript decorators — ``@Get``, ``@Post``, … (NestJS,
  TS-first servers).
* TypeScript / JavaScript router methods — ``router.get(...)``,
  ``app.post(...)``, ``server.put(...)`` (Express, Fastify, Koa-router).
* Mounted controller prefixes — ``@Controller("/x")`` and
  ``app.use("/x", router)``.
* Python decorators — ``@app.route``, ``@router.get`` (Flask, FastAPI).

The output is a :class:`BackendIndex` keyed by normalised path. Each path
is registered both at full length and at every contiguous path-suffix, so
a frontend URL whose framework adds an unseen ``/api`` prefix at runtime
still matches a backend declaration that doesn't include it.

To add another framework, add a regex to ``_ROUTE_PATTERNS`` and a prefix
detector to ``_PREFIX_PATTERNS`` — no other code changes needed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

_HTTP_METHODS = "get|post|put|patch|delete|head|options|all|route"
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

# Each pattern captures the ROUTE STRING in group 1.
_ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Decorator routes: ``@Get("/foo")`` etc.
    re.compile(
        rf"@({_HTTP_METHODS})\s*\(\s*['\"]([^'\"]*)['\"]",
        re.IGNORECASE,
    ),
    # Router-method calls: ``router.post("/foo", …)``.
    re.compile(
        rf"\b{_IDENT}\s*\.\s*({_HTTP_METHODS})\s*\(\s*['\"]([^'\"]+?)['\"]",
        re.IGNORECASE,
    ),
    # Python decorators: ``@app.route("/foo")``, ``@router.get("/foo")``.
    re.compile(
        rf"@{_IDENT}\s*\.\s*({_HTTP_METHODS})\s*\(\s*['\"]([^'\"]+?)['\"]",
    ),
)

# Each pattern captures the PREFIX STRING in group 1.
_PREFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    # NestJS controller prefix.
    re.compile(r"@Controller\s*\(\s*['\"]([^'\"]*)['\"]"),
    # Express app.use("/prefix", router) — best-effort, also matches Koa.
    re.compile(rf"\b{_IDENT}\s*\.\s*use\s*\(\s*['\"](/[^'\"]+?)['\"]"),
)

_ROUTE_DIR_RE = re.compile(
    r"/(controllers?|routes?|router|api|handlers?|endpoints?)/", re.IGNORECASE
)
_SKIP_RE = re.compile(r"(test|spec|__test__|\.d\.ts$|node_modules|migration|http-clients?)")
_TEMPLATE_PARAM_RE = re.compile(rf":({_IDENT})|<{_IDENT}>|\{{{_IDENT}\}}")


@dataclass
class BackendIndex:
    """Lookup structure produced by :func:`build_index`.

    ``paths`` maps a normalised route path to the set of (repo_id, file)
    tuples that declare it. ``suffix_paths`` separately keys by every
    contiguous path-suffix of every declared route, so a frontend URL with
    an extra runtime-mounted prefix still resolves to the backend that
    declares the suffix.
    """

    paths: dict[str, set[tuple[UUID, str]]] = field(default_factory=dict)
    suffix_paths: dict[str, set[tuple[UUID, str]]] = field(default_factory=dict)

    def lookup(self, api_path: str) -> set[tuple[UUID, str]]:
        """Return matching tuples — exact path first, suffixes second."""
        if api_path in self.paths:
            return self.paths[api_path]
        if api_path in self.suffix_paths:
            return self.suffix_paths[api_path]
        # Try dropping leading segments of the frontend path until a suffix
        # of the index is reached. Limits to 3 drops so we don't match
        # something like ``/`` or a single segment.
        parts = [p for p in api_path.split("/") if p]
        for drop in range(1, min(len(parts), 4)):
            tail = "/" + "/".join(parts[drop:])
            if tail in self.suffix_paths:
                return self.suffix_paths[tail]
        return set()


def build_index(repos: Iterable[tuple[UUID, Path]]) -> BackendIndex:
    """Walk ``repos`` and return a populated :class:`BackendIndex`.

    Each repo is ``(repo_id, abs_path_to_repo_root)``. The walker prefers a
    ``src/`` subtree if present, otherwise the whole tree.
    """
    index = BackendIndex()
    for repo_id, repo_path in repos:
        root = repo_path / "src" if (repo_path / "src").is_dir() else repo_path
        if not root.is_dir():
            continue
        for fp in root.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(repo_path).as_posix()
            if not _ROUTE_DIR_RE.search("/" + rel) or _SKIP_RE.search(rel):
                continue
            if fp.suffix not in (".ts", ".js", ".mjs", ".py"):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            prefix = _extract_prefix(text)
            for raw in _extract_routes(text):
                full = _normalise(_join_route(prefix, raw))
                index.paths.setdefault(full, set()).add((repo_id, rel))
                for suffix in _all_suffixes(full):
                    index.suffix_paths.setdefault(suffix, set()).add((repo_id, rel))
    return index


def _extract_prefix(text: str) -> str:
    """Return the first detected controller / app.use prefix or ``""``."""
    for pat in _PREFIX_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return ""


def _extract_routes(text: str) -> list[str]:
    """Pull every route fragment declared in the file (any framework)."""
    routes: list[str] = []
    for pat in _ROUTE_PATTERNS:
        for m in pat.finditer(text):
            # All patterns capture path in the LAST group.
            routes.append(m.group(m.lastindex or 0))
    return routes


def _join_route(prefix: str, path: str) -> str:
    """Join ``prefix`` and ``path``, normalising slashes and empty parts."""
    a = "/" + prefix.strip("/") if prefix else ""
    b = "/" + path.strip("/") if path else "/"
    joined = (a + b).replace("//", "/")
    return joined or "/"


def _all_suffixes(path: str) -> list[str]:
    """All contiguous path-suffixes of ``path`` excluding the empty/root one."""
    parts = [p for p in path.split("/") if p]
    return ["/" + "/".join(parts[i:]) for i in range(len(parts)) if parts[i:]]


def _normalise(path: str) -> str:
    """Match the frontend extractor's normalisation (``:param`` placeholders)."""
    p = path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    p = _TEMPLATE_PARAM_RE.sub(":param", p)
    return p or "/"
