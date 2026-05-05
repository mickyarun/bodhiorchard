# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

r"""Generic API URL extractor for any frontend repo.

Two passes, framework-agnostic:

1. :func:`build_url_constants_map` — walk the whole repo once, capture every
   ``IDENTIFIER = "/some/path"`` and ``IDENTIFIER: \`${base}/some/path\``` it
   can find. The map is keyed by identifier name.

2. :func:`extract_api_paths` — for the files belonging to one feature, pull
   every URL we can recognise: inline string literals passed to HTTP-method
   calls (``axios.get``, ``fetch``, ``$fetch``, ``useFetch``, ``http.post``,
   ``client.put``, etc.) and identifier references (``api.X``,
   ``apiUrls.X``, ``API_ROUTES.X``) which we resolve via the constants map.

All paths normalise to ``:param`` for templated segments so a backend
declaration like ``@Get(":id/status")`` and a frontend literal like
``/foo/$id/status`` collapse to the same shape.

The patterns are tuned for TypeScript/JavaScript today. To add another
language (Dart, Swift, Kotlin, …), extend the call-site regex below — the
constants-map regex is already permissive enough.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from app.services.scan.backend_link.endpoint_maps import iter_endpoint_paths
from app.services.scan.backend_link.nuxt_autoimport import find_store_references

_HTTP_METHODS = "get|post|put|patch|delete|head|options|all"

# Identifier := letters/digits/underscore, starting with a non-digit.
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

# Constants-map detector. Recognises:
#   const NAME = "/path"          (declaration)
#   const NAME = `${anything}/path`
#   NAME: "/path"                 (object-literal key, NOT member assignment)
#   NAME: `${anything}/path`
# The declaration form requires ``const|let|var`` so we don't pick up member
# assignments like ``ref.value = "/x"`` — that would have matched ``value``
# as a global constant and polluted every leaf-identifier lookup. The
# object-key form forbids a preceding ``.`` for the same reason.
_STRING_LITERAL = (
    r"(?:"
    r"`(?P<bt>[^`]*)`"
    r"|'(?P<sq>[^']*)'"
    r'|"(?P<dq>[^"]*)"'
    r")"
)
_URL_DECL_RE = re.compile(
    rf"\b(?:const|let|var)\s+({_IDENT})\s*=\s*{_STRING_LITERAL}",
)
_URL_OBJ_KEY_RE = re.compile(
    rf"(?<![.\w])({_IDENT})\s*:\s*{_STRING_LITERAL}",
)

# JS / Vue / DOM property names that look like identifiers but are universally
# accessed via member expressions. Including them in the constants map causes
# every ``foo.value`` / ``e.target`` reference to resolve to whatever URL was
# last assigned to that property, which is never what we want.
_PROPERTY_NAME_STOPLIST = frozenset(
    {
        # Vue / state primitives
        "value",
        "default",
        "current",
        "state",
        "props",
        "params",
        "query",
        "body",
        "config",
        "options",
        "context",
        # Generic identifiers
        "id",
        "key",
        "name",
        "type",
        "data",
        "target",
        "url",
        "path",
        "method",
        "status",
        "message",
        "error",
        "result",
        "response",
        "request",
        # JS / DOM prototype methods commonly assigned string values in
        # config objects (``{href: "/x"}``, ``{toFixed: "NaN"}``) — these
        # shadow real route constants when the value happens to start with
        # ``/``.
        "length",
        "href",
        "map",
        "filter",
        "reduce",
        "forEach",
        "find",
        "some",
        "every",
        "includes",
        "indexOf",
        "slice",
        "splice",
        "push",
        "pop",
        "concat",
        "join",
        "split",
        "replace",
        "match",
        "trim",
        "toFixed",
        "toString",
        "toLowerCase",
        "toUpperCase",
        "charAt",
        "substr",
        "substring",
        "valueOf",
        "hasOwnProperty",
        # JS keywords / common helpers that frequently appear before
        # string values in ways the constants regex catches when
        # immediately followed by ``=``: ``from "..."``, ``format(...)``,
        # ``parse(...)``. None should ever be a real route constant.
        "from",
        "to",
        "in",
        "of",
        "as",
        "format",
        "parse",
        "compile",
        "render",
        "load",
        "init",
        "open",
        "close",
        "set",
        "get",
        "log",
        "warn",
        "info",
        "debug",
        "trace",
    }
)

# Recognises any HTTP-method call where the receiver looks like an HTTP client.
# We accept anything ending in ``.METHOD(`` because false positives on the
# first-argument extraction are filtered later by the path shape check.
_HTTP_CALL_RE = re.compile(
    rf"\.\s*({_HTTP_METHODS})\s*\(\s*(?P<arg>[^,)\s][^,)]*?)(?=[,)])",
    re.IGNORECASE,
)

# Bare fetch-style calls without a receiver: fetch / $fetch / useFetch.
_BARE_FETCH_RE = re.compile(
    r"\b(?:\$fetch|useFetch|fetch)\s*\(\s*(?P<arg>[^,)\s][^,)]*?)(?=[,)])",
)

# Object-literal request: {url: 'something'} or {url: NAME}.
_REQ_OBJ_URL_RE = re.compile(
    r"\burl\s*:\s*(?P<arg>[^,}\s][^,}]*?)(?=[,}])",
)

# Dotted call where the leaf identifier is what we look up. Matches
# ``api_urls.EMPLOYEE.GET_DETAILS(`` and ``_employeeEndpoints.LOG_OUT(``
# but NOT bare ``foo()``. The leading char rejection avoids re-matching
# inside another dotted chain. The receiver (``axios.get``) lookup is
# already covered by ``_HTTP_CALL_RE`` for HTTP-method names.
_LEAF_CALL_RE = re.compile(rf"(?<![.\w])(?:{_IDENT}\.)+(?P<arg>{_IDENT})\s*\(")

# Leading dotted-identifier prefix (``X``, ``X.Y``, ``X.Y.Z``) at the start of
# an argument expression. Anchored only at the start so trailing method calls
# like ``.replace(...)`` or string concatenations don't prevent the lookup.
_IDENT_REF_RE = re.compile(rf"^({_IDENT})(?:\.({_IDENT}))?(?:\.({_IDENT}))?")

# Import statement — captures the module specifier in group 1. Covers both
# ``import X from "spec"`` and ``import {X} from "spec"`` forms.
_IMPORT_RE = re.compile(r"""(?:^|\n)\s*import\b[^'"\n]*['"]([^'"\n]+)['"]""")

_TEMPLATE_PARAM_RE = re.compile(r"(\$\{" + _IDENT + r"\}|\$" + _IDENT + r"|:" + _IDENT + r")")

# Directories that contain transpiler/build/vendored code. Walking them
# pollutes the constants map with framework internals (``BABEL_RUNTIME``,
# ``runtimeKey``, ``jsx-runtime`` etc.) and slows scans dramatically.
# Hidden directories (``.git``, ``.nuxt``, ``.output``, ``.next``, …) are
# rejected by the leading-dot check below; this list catches the rest.
_SKIP_DIRS = frozenset(
    {
        "node_modules",
        "dist",
        "build",
        "out",
        "coverage",
        "vendor",
        "__pycache__",
    }
)


def _is_source_path(fp: Path, repo_root: Path) -> bool:
    """Whether ``fp`` should contribute to the constants map.

    Skips hidden directories (``.git``, ``.nuxt``, ``.bodhiorchard``, …),
    explicit build/vendor dirs, and anything outside the repo root.
    """
    try:
        rel_parts = fp.relative_to(repo_root).parts
    except ValueError:
        return False
    return not any(part.startswith(".") or part in _SKIP_DIRS for part in rel_parts[:-1])


def build_url_constants_map(repo_root: Path) -> dict[str, str]:
    """Return ``{NAME: normalised_path}`` for the whole repo tree.

    Walks every ``.ts`` / ``.js`` file outside hidden, vendored, and build
    output directories. The matcher picks up both object-literal style
    entries (``NAME: "/path"``) and declaration style (``const NAME =
    "/path"``). Multi-occurrence keys keep the first match.
    """
    out: dict[str, str] = {}
    if not repo_root.is_dir():
        return out
    for fp in repo_root.rglob("*"):
        if not fp.is_file() or fp.suffix not in (".ts", ".js", ".mjs"):
            continue
        if not _is_source_path(fp, repo_root):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for regex in (_URL_DECL_RE, _URL_OBJ_KEY_RE):
            for m in regex.finditer(text):
                name = m.group(1)
                if name in _PROPERTY_NAME_STOPLIST:
                    continue
                raw = m.group("bt") or m.group("sq") or m.group("dq") or ""
                path = _first_path_in_string(raw)
                if path and _looks_like_api_path(path) and name not in out:
                    out[name] = _normalise(path)
        for name, path in iter_endpoint_paths(text):
            if name not in _PROPERTY_NAME_STOPLIST and name not in out:
                out[name] = path
    return out


def extract_api_paths(
    file_paths: list[Path],
    *,
    constants_map: dict[str, str] | None = None,
    repo_root: Path | None = None,
    store_map: dict[str, Path] | None = None,
) -> list[str]:
    """Return a sorted, deduped list of normalised API paths in ``file_paths``.

    Three signal sources, all merged:
    * Inline literal arguments to HTTP-method / fetch-style calls.
    * Inline ``url:`` keys in object-literal requests.
    * Identifier references whose name resolves through ``constants_map``.

    When ``repo_root`` is given the file list is expanded by following
    one level of import statements — a feature whose ``code_locations``
    only lists UI components still picks up the network calls in the
    services/composables/utils modules those components import.

    Files that don't exist on disk are skipped silently — a synth's
    ``code_locations`` may list paths the worktree no longer has.
    """
    seen: set[str] = set()
    cmap = constants_map or {}
    if repo_root:
        expanded: dict[Path, int] = _expand_via_imports(file_paths, repo_root, store_map or {})
    else:
        expanded = {p.resolve(): 0 for p in file_paths if p.is_file()}
    for fp, distance in expanded.items():
        if distance > _FETCH_MAX_DISTANCE or not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for arg_re in (_HTTP_CALL_RE, _BARE_FETCH_RE, _REQ_OBJ_URL_RE):
            for m in arg_re.finditer(text):
                resolved = _resolve_argument(m.group("arg"), cmap)
                if resolved:
                    seen.add(resolved)
        for m in _LEAF_CALL_RE.finditer(text):
            leaf = m.group("arg")
            if leaf in _PROPERTY_NAME_STOPLIST:
                continue
            candidate = cmap.get(leaf)
            if candidate and _looks_like_api_path(candidate):
                seen.add(candidate)
    return sorted(seen)


# Maximum BFS distance from any seed file at which we still attribute a
# fetch call to the feature. Distance 0 = seed itself, 1 = direct import,
# 2 = transitive import. Folder-name heuristics (``services/``, ``stores/``)
# vary too much across codebases to be reliable; raw graph distance is
# the only generic signal.
#
# The default of 1 is intentionally tight — it counts calls in the seed
# files plus the modules they directly import, but rejects calls reached
# only through shared layout / bootstrap code. The synth pipeline that
# produces a feature's ``code_locations`` already includes that feature's
# domain services and stores in the seed, so distance-1 reach covers the
# real surface without depending on directory layout.
_FETCH_MAX_DISTANCE = 1

# How far BFS expands to discover files at all. Always ``>= _FETCH_MAX_DISTANCE``;
# we may keep an extra hop available in future for diagnostics, but for
# now they're equal — there's no point walking deeper if we won't count
# the calls we find.
_IMPORT_DEPTH = _FETCH_MAX_DISTANCE


def _expand_via_imports(
    seed: list[Path],
    repo_root: Path,
    store_map: dict[str, Path],
) -> dict[Path, int]:
    """Return ``{file: shortest_hop_distance_from_any_seed}``.

    Performs a BFS from the seed set following both literal ``import``
    statements and Nuxt-style auto-imported store references
    (``useXxxStore``). Resolves ``@/x`` / ``~/x`` aliases against both
    ``<repo_root>/src/x`` (Vite, Vue CLI) and ``<repo_root>/x`` (Nuxt).
    Walks at most :data:`_IMPORT_DEPTH` hops so transitive shared-layout
    chains can't pull every service into a feature's surface.
    """
    distance: dict[Path, int] = {p.resolve(): 0 for p in seed if p.is_file()}
    alias_roots = (repo_root / "src", repo_root)
    frontier: list[tuple[Path, int]] = [(p, 0) for p in list(distance)]
    while frontier:
        next_frontier: list[tuple[Path, int]] = []
        for fp, d in frontier:
            if d >= _IMPORT_DEPTH:
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            new_distance = d + 1
            for resolved in _iter_imported_targets(fp, text, alias_roots):
                if distance.get(resolved, _IMPORT_DEPTH + 1) > new_distance:
                    distance[resolved] = new_distance
                    next_frontier.append((resolved, new_distance))
            for symbol in find_store_references(text):
                target = store_map.get(symbol)
                if target and distance.get(target, _IMPORT_DEPTH + 1) > new_distance:
                    distance[target] = new_distance
                    next_frontier.append((target, new_distance))
        frontier = next_frontier
    return distance


def _iter_imported_targets(fp: Path, text: str, alias_roots: tuple[Path, ...]) -> Iterator[Path]:
    """Yield resolved file paths for every literal ``import`` in ``text``."""
    for m in _IMPORT_RE.finditer(text):
        spec = m.group(1)
        if spec.startswith(("@/", "~/")):
            bases: list[Path] = [root / spec[2:] for root in alias_roots]
        elif spec.startswith("./") or spec.startswith("../"):
            bases = [(fp.parent / spec).resolve()]
        else:
            continue  # bare package import — skip
        for base in bases:
            resolved = _resolve_import_target(base)
            if resolved:
                yield resolved
                break


def _resolve_import_target(base: Path) -> Path | None:
    """Try common extensions / index files to turn a specifier into a path."""
    for ext in (".ts", ".tsx", ".js", ".mjs", ".vue"):
        candidate = base.with_suffix(ext) if base.suffix == "" else Path(str(base) + ext)
        if candidate.is_file():
            return candidate.resolve()
    if base.is_file():
        return base.resolve()
    if base.is_dir():
        for ext in (".ts", ".tsx", ".js", ".mjs"):
            candidate = base / f"index{ext}"
            if candidate.is_file():
                return candidate.resolve()
    return None


# Filesystem-ish first segments and asset extensions that look like URL paths
# but are not API endpoints. The shebang ``#!/usr/bin/env node`` and config
# strings like ``"http://localhost:80/server/api"`` both surface as
# ``/usr/...`` and ``/localhost:.../`` here — neither is a route to match.
_FILESYSTEM_PREFIXES = (
    "/app/",
    "/usr/",
    "/var/",
    "/etc/",
    "/tmp/",
    "/opt/",
    "/bin/",
    "/sbin/",
    "/home/",
    "/root/",
    "/sys/",
    "/proc/",
    "/dev/",
    "/mnt/",
    "/media/",
    "/Users/",
    "/private/",
)
_NON_API_FIRST_SEGMENT = (
    "localhost",
    "127.0.0.1",
)
_ASSET_EXTENSIONS = (
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".css",
    ".scss",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".html",
    ".pdf",
    ".json",
    ".map",
    ".txt",
    ".xml",
    ".mp4",
    ".webm",
    ".mp3",
    ".wav",
)


# Single-segment first-words that are JS keywords or content-type fragments
# rather than route prefixes — extracted from things like ``"/function"`` or
# ``"application/json"`` slipping past the literal regex.
_GENERIC_FIRST_SEGMENTS = frozenset(
    {
        "function",
        "json",
        "null",
        "undefined",
        "true",
        "false",
        "object",
        "string",
        "number",
        "boolean",
        "void",
        "any",
        "never",
        "this",
        "default",
        "export",
        "import",
        "return",
        "async",
        "await",
    }
)


def _looks_like_api_path(path: str) -> bool:
    """Reject filesystem paths, URL fragments, asset paths, and JS-keyword tokens.

    A real API path has at least one alphanumeric segment that doesn't
    contain a host-like dot (rules out ``/devapi.example.com/api``) and
    isn't a single JS keyword extracted from a comment or content-type.
    """
    if not path or not path.startswith("/"):
        return False
    # Template-literal fragments — ``\`${baseUrl}/${accountAuthId}/...\``` leaks
    # ``/${accountAuthId`` through ``_first_path_in_string``. Real routes don't
    # contain unresolved interpolation tokens.
    if "${" in path or path.startswith("/$"):
        return False
    if path.startswith(_FILESYSTEM_PREFIXES):
        return False
    if path.lower().endswith(_ASSET_EXTENSIONS):
        return False
    parts = [p for p in path.split("/") if p]
    if not parts:
        return False
    first = parts[0]
    if any(token in first.lower() for token in _NON_API_FIRST_SEGMENT):
        return False
    # Domain-like first segment — host fragments leaking from URL strings.
    if "." in first:
        return False
    # Real API segments start with a letter and have ≥3 letters — rules out
    # bare ``/0``, ``/_``, ``/__v_raw``, ``/:paramy``, ``/a``, ``/li``,
    # ``/no-`` while keeping legitimate short roots like ``/api``.
    if not first[0].isalpha() or sum(1 for c in first if c.isalpha()) < 3:
        return False
    # Single-segment paths that are bare JS / content-type keywords.
    return not (len(parts) == 1 and first.lower() in _GENERIC_FIRST_SEGMENTS)


def _resolve_argument(arg: str, constants_map: dict[str, str]) -> str | None:
    """Translate a raw call-site argument into a URL path or ``None``.

    Tries (a) string-literal-with-leading-slash extraction, then (b) member-
    access lookup against ``constants_map`` for the leaf identifier. Drops
    paths that look like filesystem paths or static assets.
    """
    arg = arg.strip()
    direct = _first_path_in_string(arg)
    if direct and _looks_like_api_path(direct):
        return _normalise(direct)
    m = _IDENT_REF_RE.match(arg)
    if not m:
        return None
    leaf = next((g for g in reversed(m.groups()) if g), None)
    if leaf and leaf not in _PROPERTY_NAME_STOPLIST and leaf in constants_map:
        candidate = constants_map[leaf]
        if _looks_like_api_path(candidate):
            return candidate
    return None


def _first_path_in_string(s: str) -> str | None:
    """Pull the first ``/segment...`` substring out of a literal."""
    if not s:
        return None
    m = re.search(r"/[A-Za-z_$:][A-Za-z0-9_/$:{}.\-]*", s)
    return m.group(0) if m else None


def _normalise(path: str) -> str:
    """Drop query/fragment, trim trailing slash, collapse template params."""
    p = path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    p = _TEMPLATE_PARAM_RE.sub(":param", p)
    return p or "/"
