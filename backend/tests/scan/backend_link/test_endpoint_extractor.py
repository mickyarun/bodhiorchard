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

"""Unit tests for ``backend_link.endpoint_extractor``.

Each test feeds a tiny synthetic worktree at ``tmp_path`` and asserts on
the extracted constants map / API paths. The regexes here have a long
history of subtle false-positives (``value`` from ``ref.value``,
``/refer/home`` from member assignments, ``javascript:void(0)``
slipping through endpoint maps); the cases below codify the fixes.
"""

from __future__ import annotations

from pathlib import Path

from app.services.scan.backend_link.endpoint_extractor import (
    build_url_constants_map,
    extract_api_paths,
)


def _write(p: Path, contents: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contents)


def test_const_decl_captured(tmp_path: Path) -> None:
    """`const FOO = "/path"` populates the constants map."""
    _write(tmp_path / "src" / "api.ts", 'const LOGIN_URL = "/auth/login";\n')
    cmap = build_url_constants_map(tmp_path)
    assert cmap["LOGIN_URL"] == "/auth/login"


def test_member_assignment_does_not_pollute(tmp_path: Path) -> None:
    """``ref.value = "/x"`` must NOT register ``value`` as a constant.

    Prior bug: every Vue ``ref()`` assignment polluted the map; any
    later call site referencing ``something.value`` resolved to the
    last assigned URL.
    """
    _write(
        tmp_path / "store.ts",
        'someRef.value = "/refer/home";\nconst REAL = "/api/users";\n',
    )
    cmap = build_url_constants_map(tmp_path)
    assert "value" not in cmap
    assert cmap["REAL"] == "/api/users"


def test_skips_hidden_and_build_dirs(tmp_path: Path) -> None:
    """Hidden + build dirs (``.nuxt``, ``node_modules``, …) are skipped."""
    _write(tmp_path / "src" / "real.ts", 'const A = "/api/real";\n')
    _write(tmp_path / "node_modules" / "noise.ts", 'const A = "/from/node_modules";\n')
    _write(tmp_path / ".nuxt" / "leak.ts", 'const B = "/from/nuxt";\n')
    cmap = build_url_constants_map(tmp_path)
    assert cmap["A"] == "/api/real"
    assert "B" not in cmap


def test_inline_fetch_call_extracted(tmp_path: Path) -> None:
    """Direct ``axios.get("/path")`` calls surface in the per-feature pass."""
    src = tmp_path / "comp.ts"
    _write(src, 'await axios.get("/api/orders");\n')
    paths = extract_api_paths([src], constants_map={}, repo_root=tmp_path)
    assert paths == ["/api/orders"]


def test_pseudo_protocol_rejected(tmp_path: Path) -> None:
    """``"javascript:void(0)"`` is not a route; must not surface."""
    src = tmp_path / "comp.ts"
    _write(src, 'const HREF = "javascript:void(0)";\n')
    cmap = build_url_constants_map(tmp_path)
    # The constants regex captures it but ``_looks_like_api_path`` /
    # endpoint normalisation reject — ``HREF`` should not map to a real
    # path.
    assert cmap.get("HREF") is None


def test_distance_one_only_includes_direct_imports(tmp_path: Path) -> None:
    """Files reached via depth-2 chains are NOT walked.

    Ensures the BFS gate prevents shared layouts from leaking unrelated
    services into a feature's path set.
    """
    seed = tmp_path / "feature.ts"
    direct = tmp_path / "direct.ts"
    transitive = tmp_path / "transitive.ts"
    _write(seed, 'import "./direct";\n')
    _write(direct, 'import "./transitive";\nawait fetch("/api/direct");\n')
    _write(transitive, 'await fetch("/api/transitive");\n')

    paths = extract_api_paths([seed], constants_map={}, repo_root=tmp_path)
    assert "/api/direct" in paths
    assert "/api/transitive" not in paths


def test_chained_replace_resolves_underlying_constant(tmp_path: Path) -> None:
    """``api_urls.GET_FOO.replace("$id", id)`` resolves to GET_FOO's path.

    Real-world idiom: parameterised URLs are templated via chained
    ``.replace()`` calls. The leaf identifier the call-site regex
    captures is ``replace`` (not in any constants map). The resolver
    must walk the dotted chain right-to-left and pick the first
    identifier whose value IS in the map — which is the URL constant
    sitting between the namespace (``api_urls``) and the chained
    ``replace`` method.

    Regression: this scenario silently returned ``[]`` for every feature
    in a real Nuxt frontend codebase that used ``api_urls.X.replace()``
    + ``this.http.makeRequest({url: ...})`` across many features.
    """
    consts = tmp_path / "src" / "consts.ts"
    _write(
        consts,
        "export const api_urls = {\n"
        '  GET_BOOKING: "/integration/booking/$merchantId/status",\n'
        "};\n",
    )
    seed = tmp_path / "src" / "service.ts"
    _write(
        seed,
        'import { api_urls } from "./consts";\n'
        "this.http.makeRequest({\n"
        '  url: api_urls.GET_BOOKING.replace("$merchantId", id),\n'
        "});\n",
    )
    cmap = build_url_constants_map(tmp_path)
    assert "GET_BOOKING" in cmap, "constants map sanity check"

    paths = extract_api_paths([seed], constants_map=cmap, repo_root=tmp_path)
    assert paths == ["/integration/booking/:param/status"], (
        f"expected GET_BOOKING to resolve through chained .replace(); got {paths}"
    )


def test_double_chained_replace_still_resolves(tmp_path: Path) -> None:
    """``api_urls.X.replace(a, b).replace(c, d)`` still picks X.

    Two chained replace calls is the more common form (one per path
    parameter). The right-to-left walk must skip over both leaf-side
    ``replace`` tokens before landing on the constant.
    """
    consts = tmp_path / "src" / "consts.ts"
    _write(
        consts,
        "export const api_urls = {\n"
        '  GET_APPT: "/integration/dentally/$merchantId/appointment/$id/status",\n'
        "};\n",
    )
    seed = tmp_path / "src" / "service.ts"
    _write(
        seed,
        'import { api_urls } from "./consts";\n'
        "this.http.makeRequest({\n"
        "  url: api_urls.GET_APPT"
        '.replace("$merchantId", mid)'
        '.replace("$id", aid),\n'
        "});\n",
    )
    cmap = build_url_constants_map(tmp_path)
    paths = extract_api_paths([seed], constants_map=cmap, repo_root=tmp_path)
    assert paths == ["/integration/dentally/:param/appointment/:param/status"], paths


# ── Dart / Flutter coverage ─────────────────────────────────────────
#
# Mirrors the JS/TS suite above for the Dart declaration and call-site
# idioms ``_URL_DECL_RE`` accepts: ``const`` and ``final`` with optional
# type, plus ``static const`` class fields. Fixtures use generic
# identifiers so they exercise the regex itself, not any specific app.


def test_dart_typed_const_string_is_indexed(tmp_path: Path) -> None:
    """Dart ``const String NAME = '/path'`` populates the constants map."""
    _write(tmp_path / "lib" / "api.dart", "const String LOGIN_URL = '/auth/login';\n")
    cmap = build_url_constants_map(tmp_path)
    assert cmap["LOGIN_URL"] == "/auth/login"


def test_dart_untyped_const_is_indexed(tmp_path: Path) -> None:
    """Dart ``const NAME = '/path'`` (no type identifier) also indexes."""
    _write(tmp_path / "lib" / "api.dart", "const loginUrl = '/auth/login';\n")
    cmap = build_url_constants_map(tmp_path)
    assert cmap["loginUrl"] == "/auth/login"


def test_dart_final_typed_is_indexed(tmp_path: Path) -> None:
    """Dart ``final String NAME = '/path'`` (immutable variable) indexes."""
    _write(tmp_path / "lib" / "api.dart", "final String loginUrl = '/auth/login';\n")
    cmap = build_url_constants_map(tmp_path)
    assert cmap["loginUrl"] == "/auth/login"


def test_dart_final_untyped_is_indexed(tmp_path: Path) -> None:
    _write(tmp_path / "lib" / "api.dart", "final loginUrl = '/auth/login';\n")
    cmap = build_url_constants_map(tmp_path)
    assert cmap["loginUrl"] == "/auth/login"


def test_dart_static_const_class_field_is_indexed(tmp_path: Path) -> None:
    """Dart ``class X { static const NAME = '/path'; }`` indexes the field.

    Class-static constants are the canonical Flutter idiom for grouping
    API endpoints (``ApiEndpoints.login``). Both typed and untyped forms
    must reach the constants map so dotted call-site references
    (``ApiEndpoints.login``) resolve via the leaf-identifier walk.
    """
    _write(
        tmp_path / "lib" / "api.dart",
        "class ApiEndpoints {\n"
        "  static const String login = '/auth/login';\n"
        "  static const verify = '/auth/verify';\n"
        "}\n",
    )
    cmap = build_url_constants_map(tmp_path)
    assert cmap["login"] == "/auth/login"
    assert cmap["verify"] == "/auth/verify"


def test_dart_member_assignment_does_not_pollute(tmp_path: Path) -> None:
    """Same pollution guard as the JS test, restated for Dart.

    ``notifier.value = '/x'`` must NOT make ``value`` a constants-map
    entry — every later ``something.value`` reference would otherwise
    resolve to the last assigned URL.
    """
    _write(
        tmp_path / "lib" / "store.dart",
        "void f(ValueNotifier notifier) {\n"
        "  notifier.value = '/should-not-leak';\n"
        "}\n"
        "const REAL = '/api/users';\n",
    )
    cmap = build_url_constants_map(tmp_path)
    assert "value" not in cmap
    assert cmap["REAL"] == "/api/users"


def test_dart_http_get_uri_parse_is_extracted(tmp_path: Path) -> None:
    """``await http.get(Uri.parse('/path'))`` surfaces the path.

    The captured call-site arg is ``Uri.parse('/path'`` (open paren
    consumed before the inner close). ``_first_path_in_string`` walks
    the arg and finds the first quoted segment that looks like a path.
    """
    src = tmp_path / "lib" / "feature.dart"
    _write(src, "await http.get(Uri.parse('/api/users'));\n")
    paths = extract_api_paths([src], constants_map={}, repo_root=tmp_path)
    assert paths == ["/api/users"]


def test_dart_dio_post_with_keyword_arg_is_extracted(tmp_path: Path) -> None:
    """``_dio.post('/path', data: payload)`` surfaces the path.

    Dart keyword args (``data: payload``) follow a comma; the call-site
    regex's ``(?=[,)])`` lookahead stops at that comma, leaving the
    string literal as the captured arg.
    """
    src = tmp_path / "lib" / "feature.dart"
    _write(src, "await _dio.post('/api/orders', data: payload);\n")
    paths = extract_api_paths([src], constants_map={}, repo_root=tmp_path)
    assert paths == ["/api/orders"]


def test_dart_dotted_constant_reference_resolves(tmp_path: Path) -> None:
    """``client.post(ApiEndpoints.login)`` resolves through the constants map.

    End-to-end check: declaration regex indexes the class field; call-site
    leaf-identifier walk picks ``login`` from the dotted chain; constants
    map lookup yields the path. Without all three steps, Flutter features
    that route through an ``ApiEndpoints``-style holder stay unlinked.
    """
    _write(
        tmp_path / "lib" / "api.dart",
        "class ApiEndpoints { static const login = '/auth/login'; }\n",
    )
    src = tmp_path / "lib" / "feature.dart"
    _write(src, "await client.post(ApiEndpoints.login);\n")
    cmap = build_url_constants_map(tmp_path)
    paths = extract_api_paths([src], constants_map=cmap, repo_root=tmp_path)
    assert "/auth/login" in paths
