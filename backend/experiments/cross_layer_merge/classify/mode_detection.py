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

"""Classify each ``XLMTrackedRepo`` row as frontend/backend/processor/db.

Two-stage approach. First, look at the worktree on disk and check
high-signal manifest files (``package.json``, ``pyproject.toml``,
``Dockerfile``). Second, if the worktree isn't available or the
signals are ambiguous, fall back to name-based heuristics keyed on the
naming conventions in this org's repos.

Sandbox iteration target: when the rules below misclassify a real
repo, edit the ``NAME_HINTS`` table or the ``classify_from_worktree``
signals — this is the User Contribution Point #1 in the plan.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.schema import XLMRepoLayer, XLMTrackedRepo

log = structlog.get_logger(__name__)


# Suffix/substring → (layer, tech_stack). First match wins, evaluated in order.
# Refine this table when sandbox results show misclassifications.
NAME_HINTS: list[tuple[str, XLMRepoLayer, str | None]] = [
    ("Dashboard", XLMRepoLayer.FRONTEND, "vue3"),
    ("Web", XLMRepoLayer.FRONTEND, "vue3"),
    ("Frontend", XLMRepoLayer.FRONTEND, "vue3"),
    ("Mobile", XLMRepoLayer.FRONTEND, "react-native"),
    # Batch needs to come before "Worker"/"Processor" so a "BatchWorker"
    # repo classifies as batch rather than processor.
    ("Batch", XLMRepoLayer.BATCH, "node"),
    ("Cron", XLMRepoLayer.BATCH, "node"),
    ("Scheduler", XLMRepoLayer.BATCH, "node"),
    ("Processor", XLMRepoLayer.PROCESSOR, "node"),
    ("Worker", XLMRepoLayer.PROCESSOR, "node"),
    ("Core", XLMRepoLayer.BACKEND, "fastapi"),
    ("Service", XLMRepoLayer.BACKEND, "fastapi"),
    ("API", XLMRepoLayer.BACKEND, "fastapi"),
    ("Server", XLMRepoLayer.BACKEND, "fastapi"),
    ("Backend", XLMRepoLayer.BACKEND, "fastapi"),
]


@dataclass
class Classification:
    """The 3 fields the classifier writes back to ``XLMTrackedRepo``."""

    layer: XLMRepoLayer
    tech_stack: str | None
    db_flavor: str | None


def classify_from_name(name: str) -> Classification | None:
    """Match the repo name against ``NAME_HINTS`` and return the first hit."""
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
            return Classification(layer=XLMRepoLayer.FRONTEND, tech_stack=tech, db_flavor=None)
        if _looks_backend(deps):
            return Classification(
                layer=XLMRepoLayer.BACKEND, tech_stack=tech, db_flavor=_detect_db(path)
            )
        # No positive evidence either way: defer to NAME_HINTS rather than
        # defaulting to PROCESSOR. Returning None lets the caller's
        # name-hint table (curated for this org) make the decision.
        return None

    if pyproject.exists() or requirements.exists():
        manifest = pyproject if pyproject.exists() else requirements
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            return None
        if "fastapi" in text or "django" in text or "flask" in text:
            return Classification(
                layer=XLMRepoLayer.BACKEND,
                tech_stack="fastapi" if "fastapi" in text else "django",
                db_flavor=_detect_db(path),
            )
        return Classification(layer=XLMRepoLayer.PROCESSOR, tech_stack="python", db_flavor=None)

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


def _detect_db(path: Path) -> str | None:
    """Cheap DB-flavor sniff via directory hints."""
    if (path / "alembic").exists() or any(path.glob("**/alembic.ini")):
        return "postgres"
    if any(path.glob("**/prisma/schema.prisma")):
        return "postgres"
    if any(path.glob("**/mongo*.js")):
        return "mongo"
    return None


_BATCH_NAME_RE = ("batch", "cron", "scheduler")


def classify(name: str, path: str | None) -> Classification:
    """Combined classifier. Worktree first, name-hint second.

    For batch-style names, override the worktree's PROCESSOR/BACKEND verdict
    with BATCH while keeping the worktree-detected ``tech_stack`` and
    ``db_flavor`` — name signals layer better than dependencies for cron /
    queue-driven workers, but the manifest still tells us the language.

    Defaults to ``XLMRepoLayer.SHARED`` if both stages fail — flagged in logs
    so the user knows to add a NAME_HINTS rule.
    """
    if path:
        from_disk = classify_from_worktree(Path(path))
        if from_disk:
            if any(needle in name.lower() for needle in _BATCH_NAME_RE):
                return Classification(
                    layer=XLMRepoLayer.BATCH,
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
        hint="add a NAME_HINTS rule in classify/mode_detection.py",
    )
    return Classification(layer=XLMRepoLayer.SHARED, tech_stack=None, db_flavor=None)


async def classify_all_repos() -> dict[str, Classification]:
    """Classify every ``XLMTrackedRepo`` and write results back.

    Returns ``{repo_name: Classification}`` for the CLI to summarise.
    """
    results: dict[str, Classification] = {}
    async with AsyncSessionLocal() as session:
        repos = (await session.execute(select(XLMTrackedRepo))).scalars().all()
        for repo in repos:
            classification = classify(repo.name, repo.path)
            repo.repo_layer = classification.layer
            repo.tech_stack = classification.tech_stack
            repo.db_flavor = classification.db_flavor
            results[repo.name] = classification
        await session.commit()
    return results
