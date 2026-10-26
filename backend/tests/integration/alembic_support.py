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

"""Run Alembic against an integration-test database."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _config() -> Config:
    """Alembic config for the backend's migration tree."""
    alembic_cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    return alembic_cfg


def parent_revision(revision: str) -> str:
    """The single ``down_revision`` of ``revision``, read from its migration file."""
    parent = ScriptDirectory.from_config(_config()).get_revision(revision).down_revision
    if not isinstance(parent, str):
        raise ValueError(f"Revision {revision} has no single parent: {parent!r}")
    return parent


def run_alembic(async_url: str, action: Literal["upgrade", "downgrade"], revision: str) -> None:
    """Run ``alembic upgrade|downgrade <revision>`` against ``async_url``.

    Synchronous: env.py drives the migration with ``asyncio.run``, so call
    this from a sync fixture or test, never from inside a running loop.
    """
    alembic_cfg = _config()
    # Alembic's env.py reads DATABASE_URL from os.environ. Stash the
    # current value (if any) and restore afterwards so we don't leak
    # the container URL into the rest of the session.
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    try:
        if action == "upgrade":
            command.upgrade(alembic_cfg, revision)
        else:
            command.downgrade(alembic_cfg, revision)
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior
