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
