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

"""Classify a tracked repo's layer / tech stack / db flavor.

Two-stage approach. First, look at the worktree on disk and check
high-signal manifest files (``package.json``, ``pyproject.toml``,
``Dockerfile``). Second, if the worktree isn't available or the
signals are ambiguous, fall back to name-based heuristics keyed on the
repo naming convention used in the org.

When a real repo is misclassified, edit the :data:`NAME_HINTS` table or
extend ``classify_from_worktree`` — these are the deliberate tuning
points and the only org-specific data in this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.models.repo_layer import RepoLayer

log = structlog.get_logger(__name__)


# Suffix/substring → (layer, tech_stack). First match wins, evaluated in order.
# Refine this table when scan results show misclassifications.
NAME_HINTS: list[tuple[str, RepoLayer, str | None]] = [
    ("Dashboard", RepoLayer.FRONTEND, "vue3"),
    ("Web", RepoLayer.FRONTEND, "vue3"),
    ("Frontend", RepoLayer.FRONTEND, "vue3"),
    ("Mobile", RepoLayer.FRONTEND, "react-native"),
    # Batch needs to come before "Worker"/"Processor" so a "BatchWorker"
    # repo classifies as batch rather than processor.
    ("Batch", RepoLayer.BATCH, "node"),
    ("Cron", RepoLayer.BATCH, "node"),
    ("Scheduler", RepoLayer.BATCH, "node"),
    ("Processor", RepoLayer.PROCESSOR, "node"),
    ("Worker", RepoLayer.PROCESSOR, "node"),
    ("Core", RepoLayer.BACKEND, "fastapi"),
    ("Service", RepoLayer.BACKEND, "fastapi"),
    ("API", RepoLayer.BACKEND, "fastapi"),
    ("Server", RepoLayer.BACKEND, "fastapi"),
    ("Backend", RepoLayer.BACKEND, "fastapi"),
]


@dataclass
class Classification:
    """The 3 fields the classifier writes back to ``tracked_repositories``."""

    layer: RepoLayer
    tech_stack: str | None
    db_flavor: str | None


def classify_from_name(name: str) -> Classification | None:
    """Match the repo name against :data:`NAME_HINTS` and return the first hit."""
    for needle, layer, tech in NAME_HINTS:
        if needle.lower() in name.lower():
            return Classification(layer=layer, tech_stack=tech, db_flavor=None)
    return None


def classify_from_worktree(path: Path) -> Classification | None:
    """Inspect manifest files to decide layer + tech + db flavor.

    Returns ``None`` if no strong signal — caller should fall back to
    name heuristics.
    """
    if not path.exists() or not path.is_dir():
        return None

    pkg_json = path / "package.json"
    pyproject = path / "pyproject.toml"
    requirements = path / "requirements.txt"

    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        tech = _detect_js_tech(deps)
        if _looks_frontend(deps):
            return Classification(layer=RepoLayer.FRONTEND, tech_stack=tech, db_flavor=None)
        if _looks_backend(deps):
            return Classification(
                layer=RepoLayer.BACKEND, tech_stack=tech, db_flavor=_detect_db_js(deps, path)
            )
        # No positive evidence either way: defer to NAME_HINTS rather than
        # defaulting to PROCESSOR. Returning None lets the caller's
        # name-hint table (curated for this org) make the decision.
        return None

    pubspec = path / "pubspec.yaml"
    if pubspec.exists():
        try:
            text = pubspec.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if "\nflutter:" in f"\n{text}" or "  flutter:" in text:
            return Classification(layer=RepoLayer.FRONTEND, tech_stack="flutter", db_flavor=None)
        return None

    if pyproject.exists() or requirements.exists():
        manifest = pyproject if pyproject.exists() else requirements
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            return None
        if "fastapi" in text or "django" in text or "flask" in text:
            return Classification(
                layer=RepoLayer.BACKEND,
                tech_stack="fastapi" if "fastapi" in text else "django",
                db_flavor=_detect_db_python(text, path),
            )
        return Classification(layer=RepoLayer.PROCESSOR, tech_stack="python", db_flavor=None)

    return None


_FRONTEND_DEP_HINTS = (
    "vue",
    "@vue/",
    "@vueuse",
    "@nuxt",
    "@nuxtjs",
    "vuetify",
    "pinia",
    "react",
    "react-dom",
    "next",
    "@next/",
    "vite",
    "@vitejs",
    "svelte",
    "@sveltejs",
    "astro",
    "remix",
)
_BACKEND_DEP_HINTS = (
    "express",
    "@nestjs/",
    "fastify",
    "koa",
    "hapi",
    "@hapi/",
)


def _has_dep_hint(deps: dict[str, str], hints: tuple[str, ...]) -> bool:
    """True if any package key in ``deps`` starts with one of the hint prefixes."""
    for key in deps:
        kl = key.lower()
        for hint in hints:
            if kl == hint or kl.startswith(hint):
                return True
    return False


def _looks_frontend(deps: dict[str, str]) -> bool:
    return _has_dep_hint(deps, _FRONTEND_DEP_HINTS)


def _looks_backend(deps: dict[str, str]) -> bool:
    return _has_dep_hint(deps, _BACKEND_DEP_HINTS)


def _detect_js_tech(deps: dict[str, str]) -> str | None:
    """Pick a single representative tech label."""
    if _has_dep_hint(deps, ("@nuxt", "@nuxtjs")):
        return "nuxt"
    if _has_dep_hint(deps, ("vue", "@vue/", "@vueuse", "vuetify")):
        return "vue3"
    if _has_dep_hint(deps, ("next", "@next/")):
        return "nextjs"
    if _has_dep_hint(deps, ("react",)):
        return "react"
    if _has_dep_hint(deps, ("@nestjs/",)):
        return "nestjs"
    if _has_dep_hint(deps, ("express",)):
        return "express"
    if _has_dep_hint(deps, ("vite", "@vitejs")):
        return "vite"
    return None


# Driver-package prefixes for the three flavors we recognise. Listed in
# priority order — the first hit wins and the subsequent loop short-
# circuits, so a project with both a postgres driver AND an unrelated
# ``mongodb`` test fixture still classifies as postgres.
#
# Only specific *driver* packages are listed here; multi-dialect ORMs
# (``sqlalchemy``, ``typeorm``, ``sequelize``, ``knex``) are deliberately
# omitted because their presence doesn't tell us which engine the repo
# actually targets. In practice every project that uses one of those ORMs
# also pulls in the underlying driver (``pg``, ``mysql2``, ``psycopg``…),
# which IS in the table — so the classification still resolves.
#
# The previous heuristic globbed for ``**/mongo*.js`` anywhere in the
# tree, which mis-classified Node services that ship a stray
# ``mongo-shell-helper.js`` doc/sample alongside their real driver.
# Dependency keys are authoritative; lone files are not.
_DB_DRIVER_HINTS_JS: tuple[tuple[str, str], ...] = (
    # Postgres drivers
    ("pg", "postgres"),
    ("pg-pool", "postgres"),
    ("postgres", "postgres"),
    ("@databases/pg", "postgres"),
    # MySQL / MariaDB drivers
    ("mysql", "mysql"),
    ("mysql2", "mysql"),
    ("mariadb", "mysql"),
    ("@databases/mysql", "mysql"),
    # Mongo drivers and ODMs
    ("mongoose", "mongo"),
    ("mongodb", "mongo"),
    ("@nestjs/mongoose", "mongo"),
)
_DB_DRIVER_HINTS_PY: tuple[tuple[str, str], ...] = (
    # Postgres drivers
    ("psycopg", "postgres"),
    ("psycopg2", "postgres"),
    ("asyncpg", "postgres"),
    # MySQL / MariaDB drivers
    ("mysqlclient", "mysql"),
    ("pymysql", "mysql"),
    ("aiomysql", "mysql"),
    ("mysql-connector-python", "mysql"),
    # Mongo drivers and ODMs
    ("pymongo", "mongo"),
    ("motor", "mongo"),
    ("mongoengine", "mongo"),
    ("beanie", "mongo"),
)


def _detect_db_js(deps: dict[str, str], path: Path) -> str | None:
    """Pick a DB flavor from ``package.json`` deps, falling back to file hints.

    Dependency keys are the authoritative signal — a service that imports
    ``pg`` uses postgres regardless of unrelated mongo files lying around
    the repo. The Prisma schema fallback stays for projects that hide
    their dialect inside the schema declaration.
    """
    keys_lower = {k.lower() for k in deps}
    for hint, flavor in _DB_DRIVER_HINTS_JS:
        if any(
            k == hint or k.startswith(hint + "-") or k.startswith("@" + hint + "/")
            for k in keys_lower
        ):
            return flavor
    if (path / "alembic").exists() or any(path.glob("**/alembic.ini")):
        return "postgres"
    if any(path.glob("**/prisma/schema.prisma")):
        return "postgres"
    return None


def _detect_db_python(manifest_text: str, path: Path) -> str | None:
    """Pick a DB flavor from a lower-cased pyproject / requirements blob.

    The manifest text is already ``.lower()``-ed by the caller. Alembic
    presence is treated as a postgres signal because that's how every
    real Bodhiorchard backend is laid out — extend the table here if a
    repo legitimately uses alembic on a non-postgres dialect.
    """
    for hint, flavor in _DB_DRIVER_HINTS_PY:
        if hint in manifest_text:
            return flavor
    if (path / "alembic").exists() or any(path.glob("**/alembic.ini")):
        return "postgres"
    return None


_BATCH_NAME_RE = ("batch", "cron", "scheduler")


def classify(name: str, path: str | None) -> Classification:
    """Combined classifier. Worktree first, name-hint second.

    For batch-style names, override the worktree's PROCESSOR/BACKEND verdict
    with BATCH while keeping the worktree-detected ``tech_stack`` and
    ``db_flavor`` — name signals layer better than dependencies for cron /
    queue-driven workers, but the manifest still tells us the language.

    Defaults to :data:`RepoLayer.SHARED` if both stages fail — flagged in logs
    so the operator knows to add a ``NAME_HINTS`` rule.
    """
    if path:
        from_disk = classify_from_worktree(Path(path))
        if from_disk:
            if any(needle in name.lower() for needle in _BATCH_NAME_RE):
                return Classification(
                    layer=RepoLayer.BATCH,
                    tech_stack=from_disk.tech_stack,
                    db_flavor=from_disk.db_flavor,
                )
            return from_disk

    from_name = classify_from_name(name)
    if from_name:
        return from_name

    log.warning(
        "classify.unrecognised",
        name=name,
        path=path,
        hint="add a NAME_HINTS rule in app/services/scan/repo_classify/mode_detection.py",
    )
    return Classification(layer=RepoLayer.SHARED, tech_stack=None, db_flavor=None)
