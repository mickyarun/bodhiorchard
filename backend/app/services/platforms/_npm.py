# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Shared npm / package.json helpers for JS-family platforms.

Private to the platforms package — not part of the public API.
"""

from __future__ import annotations

import json
from pathlib import Path


def read_package_json(repo: Path) -> dict[str, object] | None:
    """Parse ``<repo>/package.json``. Returns None on missing / malformed files."""
    pkg = repo / "package.json"
    if not pkg.exists():
        return None
    try:
        data = json.loads(pkg.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def package_has_any_dep(repo: Path, candidates: frozenset[str]) -> bool:
    """True if ``package.json`` lists any of ``candidates`` in (dev)Dependencies."""
    data = read_package_json(repo)
    if data is None:
        return False
    deps_field = data.get("dependencies")
    dev_deps_field = data.get("devDependencies")
    names: set[str] = set()
    if isinstance(deps_field, dict):
        names |= set(deps_field.keys())
    if isinstance(dev_deps_field, dict):
        names |= set(dev_deps_field.keys())
    return bool(names & candidates)
