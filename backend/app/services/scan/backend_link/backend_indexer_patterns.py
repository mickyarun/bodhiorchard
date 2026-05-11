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

"""Regex tables for the cross-language route indexer.

Pulled out of :mod:`backend_indexer` so the iterator/extractor module
stays focused on traversal and joining logic. Adding support for a new
framework is a one-pattern, one-test change in this file plus a
matching regression case in ``tests/scan/backend_link/test_route_indexer.py``.

Convention: each entry in :data:`ROUTE_PATTERNS` exposes two named
capture groups, ``method`` and ``path``. The extractor reads by name,
so a new pattern can put method either before or after path without
breaking downstream — important because some legacy idioms (Spring's
``@RequestMapping(value=…, method=…)``) capture path first.
"""

from __future__ import annotations

import re

_HTTP_METHODS = "get|post|put|patch|delete|head|options|all|route"
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


# --- Route declaration patterns -----------------------------------------------

ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # NestJS / TS-first decorators: ``@Get("/foo")``, ``@Post("/foo")``…
    re.compile(
        rf"@(?P<method>{_HTTP_METHODS})\s*\(\s*['\"](?P<path>[^'\"]*)['\"]",
        re.IGNORECASE,
    ),
    # Router-method calls: ``router.post("/foo", …)`` — Express, Fastify,
    # Koa-router. Negative lookbehind on ``@`` keeps Python decorators
    # (handled by the next pattern) from being double-counted: ``\b``
    # alone treats ``@`` as a word boundary so ``@bp.route(...)`` would
    # match here too without the guard.
    re.compile(
        rf"(?<!@)\b{_IDENT}\s*\.\s*(?P<method>{_HTTP_METHODS})"
        rf"\s*\(\s*['\"](?P<path>[^'\"]+?)['\"]",
        re.IGNORECASE,
    ),
    # Python decorators: ``@app.route("/foo")``, ``@router.get("/foo")``,
    # ``@blueprint.put("/foo")``. Flask / FastAPI / Quart all share this
    # shape and the ``route`` verb is in ``_HTTP_METHODS``.
    re.compile(
        rf"@{_IDENT}\s*\.\s*(?P<method>{_HTTP_METHODS})"
        rf"\s*\(\s*['\"](?P<path>[^'\"]+?)['\"]",
    ),
    # Spring-MVC verb-specific mapping annotations:
    # ``@GetMapping("/foo")`` etc. Captures both bare-string form and
    # ``value="/foo"`` named-arg form. The bare ``@RequestMapping`` is
    # *not* in this alternation because it's dual-purpose (class-level
    # prefix vs. method-level route); it's covered separately below
    # only in its disambiguated method-level form.
    re.compile(
        r"@(?P<method>Get|Post|Put|Patch|Delete)Mapping"
        r"\s*\(\s*(?:value\s*=\s*)?['\"](?P<path>[^'\"]+?)['\"]",
    ),
    # Legacy Spring method-level form:
    # ``@RequestMapping(value="/foo", method=RequestMethod.POST)``.
    # Required to recover routes from older Spring (pre-4.3) and
    # codebases that still use the verbose form. Disambiguated from
    # the class-level prefix by the mandatory ``method=`` argument.
    re.compile(
        r"@RequestMapping\s*\("
        r"\s*(?:value\s*=\s*)?['\"](?P<path>[^'\"]+?)['\"]"
        r"[^)]*?\bmethod\s*=\s*(?:RequestMethod\.)?(?P<method>\w+)"
    ),
    # Spring verb-specific decorators with no path argument:
    # ``@PostMapping``, ``@GetMapping()``, ``@PostMapping(produces="…")``.
    # Conventional for "create" / "list" methods that inherit the path
    # entirely from the class-level ``@RequestMapping("/x")`` prefix —
    # missing this pattern silently dropped those endpoints.
    #
    # The first lookahead ``(?![A-Za-z_])`` keeps ``Mapping`` from
    # matching inside a longer identifier. The second lookahead
    # rejects the *with-path* forms already covered by the previous
    # pattern, so we don't double-count: it asserts that the chars
    # immediately after the decorator are NOT an open paren followed
    # by an optional ``value=`` and then a quote. This leaves four
    # accepted shapes — ``@PostMapping``, ``@PostMapping()``,
    # ``@PostMapping(produces="...")`` and similarly for the other
    # verbs. ``path`` captures the empty string; the indexer's
    # ``_join_route`` collapses ``(prefix, "")`` to just ``prefix``.
    re.compile(
        r"@(?P<method>Get|Post|Put|Patch|Delete)Mapping"
        r"(?![A-Za-z_])"
        r"(?!\s*\(\s*(?:value\s*=\s*)?['\"])"
        r"(?P<path>)"
    ),
)


# --- Class / router prefix patterns ------------------------------------------

# Each pattern captures the prefix string in group 1.
PREFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    # NestJS controller prefix.
    re.compile(r"@Controller\s*\(\s*['\"]([^'\"]*)['\"]"),
    # Express app.use("/prefix", router) — best-effort, also matches Koa.
    re.compile(rf"\b{_IDENT}\s*\.\s*use\s*\(\s*['\"](/[^'\"]+?)['\"]"),
    # Spring class-level ``@RequestMapping("/prefix")`` /
    # ``@RequestMapping(value="/prefix")`` (when the annotation appears
    # on the class declaration above the method-level ones, the first
    # match in file order is the class prefix).
    re.compile(r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?['\"](/[^'\"]+?)['\"]"),
    # FastAPI ``APIRouter(prefix="/api/v1")`` — the router instance
    # carries the prefix that's prepended to every method-level decorator
    # in the file. Uses a non-greedy ``.*?`` with ``re.DOTALL`` so
    # ``APIRouter(dependencies=[Depends(get_db)], prefix="/api/v1")``
    # works even though the inner ``)`` of ``get_db)`` would otherwise
    # terminate a ``[^)]*`` match prematurely. Worst case the
    # non-greedy span crosses into another ``APIRouter(...)`` call in
    # the same file — uncommon and acceptable for a v1 prefix detector.
    re.compile(
        r"APIRouter\s*\(.*?\bprefix\s*=\s*['\"](/[^'\"]+?)['\"]",
        re.DOTALL,
    ),
)


# --- Discovery + skip filters ------------------------------------------------

ROUTE_DIR_RE = re.compile(
    # ``router`` extended to ``routers?`` so FastAPI's conventional
    # ``app/routers/`` directory is recognised alongside Express's
    # ``router/`` and Rails-style ``routes/``.
    r"/(controllers?|routes?|routers?|api|handlers?|endpoints?)/",
    re.IGNORECASE,
)

# Filename-based controller discovery. Each entry is a framework's
# canonical filename convention — both halves (filename match AND a
# matching regex in :data:`ROUTE_PATTERNS`) ship together so a walked
# file is guaranteed to produce real records, not silent zeroes.
#
# * ``*.controller.{ts,js,mjs}`` — NestJS (``otp/otp.controller.ts``).
#   The framework's CLI generates this exact suffix.
# * ``*Controller.java`` — Spring-MVC (``UserController.java``). Class
#   names by convention end in ``Controller``; matched conservatively
#   to a leading uppercase letter.
# * Python ``routes.py`` / ``router.py`` plus the two split-by-domain
#   variants ``user_routes.py`` (prefix form) and ``routes_user.py``
#   (suffix form). Tightened so unrelated camelCase names like
#   ``routerSnapshot.py`` don't get walked.
ROUTE_FILE_RE = re.compile(
    r"(?:^|/)("
    r"[A-Za-z0-9_-]+\.controller\.(?:ts|js|mjs)"
    r"|[A-Z][A-Za-z0-9_]*Controller\.java"
    r"|(?:[A-Za-z0-9]+_)?(?:routes?|router)(?:_[A-Za-z0-9_]+)?\.py"
    r")$",
)

SKIP_RE = re.compile(r"(test|spec|__test__|\.d\.ts$|node_modules|migration|http-clients?)")

# Path parameter shapes across frameworks, normalised to ``:param``:
#   Express / NestJS / Spring : ``:name``        → ``:param``
#   FastAPI / Flask f-strings  : ``{name}``      → ``:param``
#   Spring path-vars           : ``{name}``      → ``:param`` (same)
#   Flask converters           : ``<int:name>``  → ``:param``
#   Flask plain                : ``<name>``      → ``:param``
# The Flask converter form (``<type:name>``) MUST come before the
# bare ``<name>`` and the bare ``:name`` alternations — otherwise the
# inner ``:name`` would normalise first and leave ``<int::param>``.
TEMPLATE_PARAM_RE = re.compile(
    rf"<{_IDENT}:{_IDENT}>"
    rf"|<{_IDENT}>"
    rf"|\{{{_IDENT}\}}"
    rf"|:({_IDENT})"
)


SUPPORTED_SUFFIXES: tuple[str, ...] = (".ts", ".js", ".mjs", ".py", ".java")


__all__ = [
    "PREFIX_PATTERNS",
    "ROUTE_DIR_RE",
    "ROUTE_FILE_RE",
    "ROUTE_PATTERNS",
    "SKIP_RE",
    "SUPPORTED_SUFFIXES",
    "TEMPLATE_PARAM_RE",
]
