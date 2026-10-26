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

"""Every backend setting documented for production actually reaches the container.

``docker-compose.prod.yml`` hands the backend an explicit ``environment:``
allow-list, and ``deploy.sh``'s ``--env-file`` only substitutes ``${VARS}``
in the compose file — it does not inject them into containers. So a setting
documented in ``.env.production.example`` but missing from that list is
silently ignored in production: the operator sets it, the deploy succeeds,
and the backend never sees it. ``GIPHY_API_KEY`` shipped that way once.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic_settings import BaseSettings

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _setting_names(cls: type[BaseSettings]) -> set[str]:
    """Every environment variable name the backend settings read."""
    names: set[str] = set()
    for field_name, field in cls.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseSettings):
            names |= _setting_names(annotation)
        else:
            names.add(field.alias or field_name.upper())
    return names


def _documented_production_keys() -> list[str]:
    keys = []
    for line in (REPO_ROOT / ".env.production.example").read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            keys.append(stripped.split("=", 1)[0].strip())
    return keys


def test_documented_backend_settings_are_passed_to_the_prod_container() -> None:
    backend_reads = _setting_names(Settings)
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.prod.yml").read_text())
    passed = set(compose["services"]["backend"]["environment"])
    documented = [k for k in _documented_production_keys() if k in backend_reads]
    # Guard against the test quietly checking nothing.
    assert "SECRET_KEY" in documented
    missing = sorted(k for k in documented if k not in passed)
    assert not missing, (
        f"{missing} are documented in .env.production.example and read by the backend, "
        "but docker-compose.prod.yml never passes them to the backend container. Add each "
        "as `NAME: ${NAME:-}` under services.backend.environment."
    )


def test_giphy_key_is_passed_through_in_both_compose_files() -> None:
    for compose_file in ("docker-compose.yml", "docker-compose.prod.yml"):
        compose = yaml.safe_load((REPO_ROOT / compose_file).read_text())
        env = compose["services"]["backend"]["environment"]
        # Passed through, never a value baked into the file.
        assert env["GIPHY_API_KEY"] == "${GIPHY_API_KEY:-}", compose_file
