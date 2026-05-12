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

"""Unit tests for ``repo_classify.mode_detection``.

The classifier's behaviour is purely a function of the worktree
contents + repo name, so each test sets up a synthetic worktree under
``tmp_path`` and asserts on the resulting :class:`Classification`.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.repo_layer import RepoLayer
from app.services.scan.repo_classify import (
    classify,
    classify_from_name,
    classify_from_worktree,
)


def _write_pkg(tmp_path: Path, deps: dict[str, str]) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": deps}))


def test_vue_package_detected_as_frontend(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"vue": "3.0", "vuetify": "3.0"})
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.FRONTEND
    assert c.tech_stack == "vue3"


def test_nuxt_dep_detected_as_nuxt_tech(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"@nuxt/kit": "3", "vue": "3"})
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.tech_stack == "nuxt"


def test_nestjs_detected_as_backend(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"@nestjs/core": "10", "@nestjs/common": "10"})
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.tech_stack == "nestjs"


def test_fastapi_python_detected_as_backend(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.poetry.dependencies]\nfastapi = '*'")
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.tech_stack == "fastapi"


def test_alembic_dir_implies_postgres(tmp_path: Path) -> None:
    (tmp_path / "alembic").mkdir()
    (tmp_path / "pyproject.toml").write_text("fastapi = '*'")
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.db_flavor == "postgres"


def test_name_hint_fallback() -> None:
    """When the worktree gives no signal, name patterns drive layer."""
    c = classify_from_name("MyMerchantDashboard")
    assert c is not None
    assert c.layer is RepoLayer.FRONTEND


def test_unknown_falls_back_to_shared(tmp_path: Path) -> None:
    """No worktree, no name match → SHARED."""
    c = classify("UnknownThing", None)
    assert c.layer is RepoLayer.SHARED


def test_batch_name_overrides_worktree(tmp_path: Path) -> None:
    """A repo named ``...Batch...`` always becomes BATCH even if pkg looks like backend."""
    _write_pkg(tmp_path, {"@nestjs/core": "10"})
    c = classify("PaymentsBatchWorker", str(tmp_path))
    assert c.layer is RepoLayer.BATCH
    # Tech stack still reflects the manifest detection.
    assert c.tech_stack == "nestjs"


def test_postgres_node_with_stray_mongo_file_classifies_as_postgres(tmp_path: Path) -> None:
    """A Node service that imports ``pg`` is postgres regardless of stray mongo files.

    Regression: a real comms-service repo uses postgres but the previous heuristic
    globbed ``**/mongo*.js`` anywhere in the tree and mis-flagged it as
    mongo because the repo shipped a sample ``mongo-shell-helper.js``.
    Dependency keys are authoritative; lone files are not.
    """
    _write_pkg(tmp_path, {"@nestjs/core": "10", "pg": "^8.0", "typeorm": "^0.3"})
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "mongo-shell-helper.js").write_text("// unrelated sample\n")
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.db_flavor == "postgres"


def test_node_with_mongoose_dep_classifies_as_mongo(tmp_path: Path) -> None:
    """The mongo classification still fires when ``mongoose`` IS a real dep."""
    _write_pkg(tmp_path, {"@nestjs/core": "10", "mongoose": "^8.0"})
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.db_flavor == "mongo"


def test_python_with_psycopg_classifies_as_postgres(tmp_path: Path) -> None:
    """Python backends sniff their DB driver from the manifest text."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = ['fastapi', 'psycopg[binary]>=3.0']\n"
    )
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.db_flavor == "postgres"


def test_node_with_mysql2_classifies_as_mysql(tmp_path: Path) -> None:
    """A Node service that imports ``mysql2`` is classified as mysql."""
    _write_pkg(tmp_path, {"@nestjs/core": "10", "mysql2": "^3.0", "typeorm": "^0.3"})
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.db_flavor == "mysql"


def test_node_with_mariadb_classifies_as_mysql(tmp_path: Path) -> None:
    """``mariadb`` driver buckets into the same ``mysql`` flavor."""
    _write_pkg(tmp_path, {"@nestjs/core": "10", "mariadb": "^3.0"})
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.db_flavor == "mysql"


def test_python_with_pymysql_classifies_as_mysql(tmp_path: Path) -> None:
    """``pymysql`` in pyproject deps drives the mysql verdict."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = ['fastapi', 'sqlalchemy>=2', 'pymysql>=1.1']\n"
    )
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.db_flavor == "mysql"


def test_flutter_pubspec_detected_as_frontend(tmp_path: Path) -> None:
    """A ``pubspec.yaml`` with a ``flutter:`` section is FRONTEND/flutter.

    Regression: a real Flutter app was falling through to
    ``RepoLayer.SHARED`` because the classifier only inspected
    ``package.json`` / ``pyproject.toml`` / ``requirements.txt``.
    """
    (tmp_path / "pubspec.yaml").write_text(
        "name: consumer_pax\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "flutter:\n"
        "  uses-material-design: true\n"
    )
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.FRONTEND
    assert c.tech_stack == "flutter"


def test_pure_dart_pubspec_returns_none(tmp_path: Path) -> None:
    """A Dart-only ``pubspec.yaml`` (no ``flutter:`` marker) defers to name hints."""
    (tmp_path / "pubspec.yaml").write_text("name: dart_cli_tool\ndependencies:\n  args: ^2.0.0\n")
    c = classify_from_worktree(tmp_path)
    assert c is None


def test_orm_only_without_driver_returns_no_flavor(tmp_path: Path) -> None:
    """A bare ORM (``sqlalchemy``) without a driver hint shouldn't guess.

    The previous heuristic biased ``sqlalchemy`` to postgres, which
    misclassified MySQL shops. We now require a real driver
    (``psycopg``, ``pymysql``, …) before declaring a flavor.
    """
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = ['fastapi', 'sqlalchemy>=2']\n"
    )
    c = classify_from_worktree(tmp_path)
    assert c is not None
    assert c.layer is RepoLayer.BACKEND
    assert c.db_flavor is None
