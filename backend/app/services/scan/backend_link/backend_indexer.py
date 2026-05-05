# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

_HTTP_METHODS = "get|post|put|patch|delete|head|options|all|route"
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

# Each pattern captures TWO named groups, ``method`` and ``path`` —
# in either order, since some framework idioms put the verb after
# the URL string (e.g. legacy Spring ``@RequestMapping(value=…, method=…)``).
# The extractor reads by name so contributors adding a new pattern
# can't accidentally drift the (1, 2) positional contract.
_ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = (
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
)

# Each pattern captures the PREFIX STRING in group 1.
_PREFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
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

_ROUTE_DIR_RE = re.compile(
    # ``router`` extended to ``routers?`` so FastAPI's conventional
    # ``app/routers/`` directory is recognised alongside Express's
    # ``router/`` and Rails-style ``routes/``.
    r"/(controllers?|routes?|routers?|api|handlers?|endpoints?)/",
    re.IGNORECASE,
)
# Filename-based controller discovery. Each entry is a framework's
# canonical filename convention — both halves (filename match AND
# matching regex in ``_ROUTE_PATTERNS``) ship together so a walked
# file is guaranteed to produce real records, not silent zeroes.
#
# * ``*.controller.{ts,js,mjs}`` — NestJS (``otp/otp.controller.ts``).
#   The framework's CLI generates this exact suffix.
# * ``*Controller.java`` — Spring-MVC (``UserController.java``). Class
#   names by convention end in ``Controller``; matched conservatively
#   to a leading uppercase letter.
# * ``routes.py`` / ``router.py`` (with optional ``_<suffix>``) —
#   Flask / FastAPI canonical names. Tightened from a previous overly
#   broad pattern that would have matched ``routerSnapshot.py``.
_ROUTE_FILE_RE = re.compile(
    r"(?:^|/)("
    r"[A-Za-z0-9_-]+\.controller\.(?:ts|js|mjs)"
    r"|[A-Z][A-Za-z0-9_]*Controller\.java"
    # Python ``routes.py`` / ``router.py`` plus the two split-by-domain
    # variants: ``user_routes.py`` (prefix form) and ``routes_user.py``
    # (suffix form). The optional prefix segment requires a trailing
    # ``_`` separator so unrelated camelCase names like
    # ``routerSnapshot.py`` don't get walked.
    r"|(?:[A-Za-z0-9]+_)?(?:routes?|router)(?:_[A-Za-z0-9_]+)?\.py"
    r")$",
)
_SKIP_RE = re.compile(r"(test|spec|__test__|\.d\.ts$|node_modules|migration|http-clients?)")
# Path parameter shapes across frameworks, normalised to ``:param``:
#   Express / NestJS / Spring : ``:name``        → ``:param``
#   FastAPI / Flask f-strings  : ``{name}``      → ``:param``
#   Spring path-vars           : ``{name}``      → ``:param`` (same)
#   Flask converters           : ``<int:name>``  → ``:param``
#   Flask plain                : ``<name>``      → ``:param``
# The Flask converter form (``<type:name>``) MUST come before the
# bare ``<name>`` and the bare ``:name`` alternations — otherwise the
# inner ``:name`` would normalise first and leave ``<int::param>``.
_TEMPLATE_PARAM_RE = re.compile(
    rf"<{_IDENT}:{_IDENT}>"
    rf"|<{_IDENT}>"
    rf"|\{{{_IDENT}\}}"
    rf"|:({_IDENT})"
)


@dataclass(frozen=True)
class RouteRecord:
    """One declared HTTP route in a backend repo's source.

    The cache table persists one row per record (keyed by repo + sha +
    the three string fields). The in-memory :class:`BackendIndex` is
    assembled from a stream of records, so both consumers share the same
    producer (:func:`iter_route_records`).

    ``file_path`` is repo-root-relative (POSIX separators) so the same
    record is portable across the per-repo writer and the global linker
    that reads it back from the cache.

    ``http_method`` is the regex's first capture group, lower-cased.
    Patterns that don't carry a method (e.g. NestJS ``@Controller``
    prefix) never produce a record on their own.
    """

    normalised_path: str
    http_method: str
    file_path: str


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


def iter_route_records(repo_root: Path) -> Iterator[RouteRecord]:
    """Yield one :class:`RouteRecord` per declared HTTP route in ``repo_root``.

    Walks the same tree :func:`build_index` does (preferring ``src/`` when
    present) and applies the same skip rules. The output is a stream of
    pure data records — both the in-memory index assembler and the cache
    writer (``backend_route_cache``) consume it. Algorithm changes only
    have to touch this function; the two consumers stay aligned.
    """
    if not repo_root.is_dir():
        return
    root = repo_root / "src" if (repo_root / "src").is_dir() else repo_root
    if not root.is_dir():
        return
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(repo_root).as_posix()
        if _SKIP_RE.search(rel):
            continue
        # File qualifies if EITHER (a) it lives under a route-y directory
        # (Express / FastAPI / NestJS-with-controllers-folder layouts) OR
        # (b) its filename matches a per-framework controller convention
        # (NestJS scattered ``*.controller.ts``, Spring ``*Controller.java``).
        in_route_dir = bool(_ROUTE_DIR_RE.search("/" + rel))
        is_controller_file = bool(_ROUTE_FILE_RE.search(rel))
        if not (in_route_dir or is_controller_file):
            continue
        if fp.suffix not in (".ts", ".js", ".mjs", ".py", ".java"):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        prefix = _extract_prefix(text)
        for method, raw_path in _extract_method_path_pairs(text):
            normalised = _normalise(_join_route(prefix, raw_path))
            yield RouteRecord(
                normalised_path=normalised,
                http_method=method.lower(),
                file_path=rel,
            )


def build_index(repos: Iterable[tuple[UUID, Path]]) -> BackendIndex:
    """Walk ``repos`` and return a populated :class:`BackendIndex`.

    Each repo is ``(repo_id, abs_path_to_repo_root)``. Iterates the
    shared :func:`iter_route_records` producer and folds the records
    into the index's exact-path + suffix-path maps.
    """
    index = BackendIndex()
    for repo_id, repo_path in repos:
        for record in iter_route_records(repo_path):
            full = record.normalised_path
            index.paths.setdefault(full, set()).add((repo_id, record.file_path))
            for suffix in all_suffixes(full):
                index.suffix_paths.setdefault(suffix, set()).add((repo_id, record.file_path))
    return index


def all_suffixes(path: str) -> list[str]:
    """All contiguous path-suffixes of ``path`` excluding the empty/root one.

    A frontend URL whose framework adds an unseen ``/api`` prefix at
    runtime still resolves to a backend declaration that doesn't include
    it, so we register every suffix during index assembly and look both
    full path + every suffix up at query time.
    """
    parts = [p for p in path.split("/") if p]
    return ["/" + "/".join(parts[i:]) for i in range(len(parts)) if parts[i:]]


def _extract_prefix(text: str) -> str:
    """Return the first detected controller / app.use prefix or ``""``."""
    for pat in _PREFIX_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return ""


def _extract_method_path_pairs(text: str) -> list[tuple[str, str]]:
    """Pull every (http_method, route_path) pair declared in the file.

    The previous helper discarded the method group; the cache table
    needs it as a column, so we return both. Callers that don't care
    about the method (e.g. an in-memory index keyed only on path) can
    still drop the first element of each pair.
    """
    pairs: list[tuple[str, str]] = []
    for pat in _ROUTE_PATTERNS:
        for m in pat.finditer(text):
            # Patterns use named groups so positional ordering can't
            # drift as new framework idioms are added (e.g. Spring's
            # ``@RequestMapping(value=…, method=…)`` puts path before
            # method, opposite to every other supported pattern).
            pairs.append((m.group("method"), m.group("path")))
    return pairs


def _join_route(prefix: str, path: str) -> str:
    """Join ``prefix`` and ``path``, normalising slashes and empty parts."""
    a = "/" + prefix.strip("/") if prefix else ""
    b = "/" + path.strip("/") if path else "/"
    joined = (a + b).replace("//", "/")
    return joined or "/"


def _normalise(path: str) -> str:
    """Match the frontend extractor's normalisation (``:param`` placeholders)."""
    p = path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    p = _TEMPLATE_PARAM_RE.sub(":param", p)
    return p or "/"
