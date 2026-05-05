# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for ``backend_link.backend_indexer.iter_route_records``.

The route indexer's job is to walk a backend repo's source and yield
one :class:`RouteRecord` per declared HTTP route. Regression coverage
for the discovery-by-filename rules added when three live backends
(NestJS, all of them) were silently producing zero cached routes
because their controllers lived under domain folders, not under
``controllers/``.
"""

from __future__ import annotations

from pathlib import Path

from app.services.scan.backend_link.backend_indexer import iter_route_records


def _write(p: Path, contents: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contents)


def test_nestjs_controller_in_domain_folder_discovered(tmp_path: Path) -> None:
    """``src/otp/otp.controller.ts`` is recognised by filename, not directory.

    Regression: NestJS scatters controllers across domain folders
    (``otp/``, ``customer-io/``, …) instead of a top-level ``controllers/``.
    The pre-fix indexer's ``_ROUTE_DIR_RE`` only matched files under
    ``controllers?/``, ``routes?/``, ``api/`` etc., so every NestJS repo
    using domain layout produced zero records.
    """
    _write(
        tmp_path / "src" / "otp" / "otp.controller.ts",
        '@Controller("/otp")\n'
        "export class OtpController {\n"
        '  @Post("/verify")\n'
        "  verify() {}\n"
        "}\n",
    )
    records = list(iter_route_records(tmp_path))
    assert len(records) == 1, records
    assert records[0].normalised_path == "/otp/verify"
    assert records[0].http_method == "post"


def test_nestjs_app_controller_at_root(tmp_path: Path) -> None:
    """``src/app.controller.ts`` is the conventional health-check controller."""
    _write(
        tmp_path / "src" / "app.controller.ts",
        'export class AppController {\n  @Get("/health")\n  health() {}\n}\n',
    )
    records = list(iter_route_records(tmp_path))
    assert any(r.normalised_path == "/health" for r in records), records


def test_traditional_controllers_folder_still_works(tmp_path: Path) -> None:
    """The pre-existing ``src/controllers/foo.ts`` discovery is untouched.

    Files under a route-y directory still qualify regardless of whether
    they match the new filename pattern — the change is purely additive.
    """
    _write(
        tmp_path / "src" / "controllers" / "users.ts",
        'router.get("/users", listUsers);\nrouter.post("/users", createUser);\n',
    )
    records = list(iter_route_records(tmp_path))
    paths = sorted({r.normalised_path for r in records})
    assert paths == ["/users"], records


def test_skips_test_and_spec_controller_files(tmp_path: Path) -> None:
    """``app.controller.spec.ts`` is a test, not a real route declaration."""
    _write(
        tmp_path / "src" / "app.controller.spec.ts",
        'describe("AppController", () => {\n'
        '  it("does", () => router.get("/fake", () => {}));\n'
        "});\n",
    )
    records = list(iter_route_records(tmp_path))
    assert records == [], records


def test_unrelated_dotted_filename_not_picked_up(tmp_path: Path) -> None:
    """``foo.service.ts`` lives next to controllers but is not one.

    The filename match is anchored on ``.controller.{ts,js,mjs}`` (or
    Spring's ``*Controller.java``), so service / module / dto files in
    the same domain folder don't get walked.
    """
    _write(
        tmp_path / "src" / "otp" / "otp.service.ts",
        # Even if a service file contains an HTTP-call shape, the indexer
        # should not consider it a route declaration.
        'router.post("/should-not-be-picked-up", x);\n',
    )
    records = list(iter_route_records(tmp_path))
    assert records == [], records


def test_spring_controller_with_class_prefix(tmp_path: Path) -> None:
    """Spring ``@RequestMapping("/users")`` class prefix joins with method routes.

    ``@RequestMapping`` is the dual-purpose annotation: at class level
    it's a prefix; at method level it could also be a route. We treat
    the FIRST occurrence in the file as the class prefix (Java
    convention puts it on the class declaration above any methods)
    and use only the verb-specific annotations (``@GetMapping``, etc.)
    as method-level routes. This keeps the class annotation from being
    double-counted as both prefix and route.
    """
    _write(
        tmp_path / "src" / "main" / "java" / "com" / "x" / "UserController.java",
        "@RestController\n"
        '@RequestMapping("/users")\n'
        "public class UserController {\n"
        '  @GetMapping("/{id}")\n'
        "  public User get(@PathVariable Long id) { return null; }\n"
        "  @PostMapping\n"
        "  public User create() { return null; }\n"
        '  @DeleteMapping("/{id}")\n'
        "  public void delete(@PathVariable Long id) {}\n"
        "}\n",
    )
    records = list(iter_route_records(tmp_path))
    paths = sorted(r.normalised_path for r in records)
    # ``@PostMapping`` without a path argument doesn't match — Spring
    # treats it as the bare class prefix, but our regex requires a
    # string literal. That's an accepted limitation of the v1 pattern.
    assert "/users/:param" in paths, f"GetMapping path: {paths}"
    assert "/users/:param" in paths, f"DeleteMapping path: {paths}"
    methods = {r.http_method for r in records}
    assert "get" in methods and "delete" in methods, methods


def test_spring_value_named_arg(tmp_path: Path) -> None:
    """``@GetMapping(value="/foo")`` named-arg form resolves identically."""
    _write(
        tmp_path / "src" / "ApiController.java",
        "public class ApiController {\n"
        '  @GetMapping(value="/items")\n'
        "  public List<Item> list() { return null; }\n"
        "}\n",
    )
    records = list(iter_route_records(tmp_path))
    assert any(r.normalised_path == "/items" for r in records), records


def test_flask_route_decorator_in_routes_py(tmp_path: Path) -> None:
    """Flask ``@app.route("/users")`` in a top-level ``routes.py``.

    The filename match catches the canonical Flask ``routes.py`` /
    ``router.py`` even when the file isn't under a ``routes/``
    directory — relevant for flat-layout Flask apps.
    """
    _write(
        tmp_path / "src" / "routes.py",
        "from flask import Blueprint\n"
        'bp = Blueprint("api", __name__)\n'
        "\n"
        '@bp.route("/users", methods=["GET"])\n'
        "def list_users(): pass\n"
        "\n"
        '@bp.route("/users/<int:id>", methods=["GET"])\n'
        "def get_user(id): pass\n",
    )
    records = list(iter_route_records(tmp_path))
    paths = sorted(r.normalised_path for r in records)
    # ``<int:id>`` is the Flask path-converter syntax which the
    # template-param normaliser collapses to ``:param``.
    assert paths == ["/users", "/users/:param"], records


def test_fastapi_router_prefix_prepended(tmp_path: Path) -> None:
    """FastAPI ``APIRouter(prefix="/api/v1/users")`` joins with ``@router.get``.

    The prefix detector recognises the construction-time named arg and
    prepends it to every method-level decorator in the same file.
    Flat-layout FastAPI apps (single ``routers/users.py``) need this
    to produce paths that match what the frontend actually calls.
    """
    _write(
        tmp_path / "app" / "routers" / "users.py",
        "from fastapi import APIRouter\n"
        'router = APIRouter(prefix="/api/v1/users")\n'
        "\n"
        '@router.get("/")\n'
        "def list(): pass\n"
        "\n"
        '@router.post("/")\n'
        "def create(): pass\n"
        "\n"
        '@router.get("/{user_id}")\n'
        "def get(user_id: int): pass\n",
    )
    records = list(iter_route_records(tmp_path))
    paths = sorted(r.normalised_path for r in records)
    assert paths == [
        "/api/v1/users",
        "/api/v1/users",
        "/api/v1/users/:param",
    ], records


def test_python_routes_filename_with_underscore_suffix(tmp_path: Path) -> None:
    """``user_routes.py`` naming convention (split-by-domain) is recognised.

    The filename pattern accepts ``routes.py`` / ``router.py`` plus an
    optional ``_<suffix>`` for projects that split routes by feature
    rather than directory.
    """
    _write(
        tmp_path / "user_routes.py",
        '@app.get("/users")\ndef list(): pass\n',
    )
    records = list(iter_route_records(tmp_path))
    assert any(r.normalised_path == "/users" for r in records), records


def test_spring_legacy_request_mapping_method_named_arg(tmp_path: Path) -> None:
    """``@RequestMapping(value="/foo", method=RequestMethod.POST)`` still resolves.

    Legacy Spring (pre-4.3) and codebases that haven't migrated to the
    verb-specific annotations use this verbose form. Disambiguated
    from the class-level prefix by the presence of ``method=``.
    """
    _write(
        tmp_path / "src" / "OrderController.java",
        "@RestController\n"
        '@RequestMapping("/orders")\n'
        "public class OrderController {\n"
        '  @RequestMapping(value="/", method=RequestMethod.POST)\n'
        "  public Order create() { return null; }\n"
        '  @RequestMapping(value="/{id}", method=RequestMethod.PUT)\n'
        "  public Order update(@PathVariable Long id) { return null; }\n"
        "}\n",
    )
    records = list(iter_route_records(tmp_path))
    paths = sorted(r.normalised_path for r in records)
    assert "/orders/:param" in paths, records
    methods = {r.http_method for r in records}
    # Method names appear lower-cased; ``RequestMethod.POST`` → ``post``.
    assert "post" in methods, methods
    assert "put" in methods, methods


def test_fastapi_router_prefix_after_depends_arg(tmp_path: Path) -> None:
    """``APIRouter(dependencies=[Depends(...)], prefix="/x")`` finds the prefix.

    Real FastAPI apps configure auth / DB dependencies before the
    prefix kwarg. The prefix detector must not stop at the inner
    ``)`` of ``Depends(get_db)`` — it has to scan past nested
    parentheses to land on ``prefix=``.
    """
    _write(
        tmp_path / "app" / "routers" / "users.py",
        "from fastapi import APIRouter, Depends\n"
        "from .auth import get_current_user, get_db\n"
        "router = APIRouter(\n"
        "    dependencies=[Depends(get_db), Depends(get_current_user)],\n"
        '    prefix="/api/v1/users",\n'
        '    tags=["users"],\n'
        ")\n"
        "\n"
        '@router.get("/{id}")\n'
        "def get(id: int): pass\n",
    )
    records = list(iter_route_records(tmp_path))
    assert any(r.normalised_path == "/api/v1/users/:param" for r in records), records


def test_python_router_with_unrelated_prefix_filename_not_walked(tmp_path: Path) -> None:
    """``routerSnapshot.py`` should NOT be walked.

    The previous broad regex would have matched any file starting with
    ``router``; the tightened pattern requires the basename to be
    exactly ``router.py`` or ``router_<suffix>.py``.
    """
    _write(
        tmp_path / "scripts" / "routerSnapshot.py",
        '@app.get("/should-not-be-picked-up")\ndef _(): pass\n',
    )
    records = list(iter_route_records(tmp_path))
    assert records == [], records
