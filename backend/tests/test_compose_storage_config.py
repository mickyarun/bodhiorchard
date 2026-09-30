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

"""The backend container must actually receive its storage configuration.

Compose forwards only the variables it lists, and pydantic-settings reads
the process environment — so a storage setting that is not listed here
never reaches the app. That failure is invisible: the operator sets
``FILE_STORAGE_S3=true``, the backend boots happily on local disk, and
uploads land on one container's volume instead of the bucket. Nothing
errors, so nothing gets investigated until the files are missing.

These tests read the compose files as data and assert the wiring, which
is the only place this class of bug is observable before deployment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app.config import FileStorageConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.prod.yml")

# Every env var the storage layer reads, taken from the config model
# itself so a newly added setting fails here rather than being silently
# dropped on the way to the container.
STORAGE_ENV_VARS = sorted(
    field.alias for field in FileStorageConfig.model_fields.values() if field.alias is not None
)


def _backend_environment(compose_file: str) -> dict[str, Any]:
    """Return the backend service's ``environment`` mapping."""
    raw = yaml.safe_load((REPO_ROOT / compose_file).read_text())
    env = raw["services"]["backend"]["environment"]
    if isinstance(env, list):  # compose also allows a ["KEY=value"] list
        return dict(item.split("=", 1) for item in env)
    return dict(env)


def test_storage_env_vars_are_discovered_from_the_config_model() -> None:
    """Guard the guard: the list below must not silently become empty."""
    assert "FILE_STORAGE_S3" in STORAGE_ENV_VARS
    assert "FILE_STORAGE_S3_BUCKET" in STORAGE_ENV_VARS
    assert "AWS_ACCESS_KEY_ID" in STORAGE_ENV_VARS


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
@pytest.mark.parametrize("var", STORAGE_ENV_VARS)
def test_backend_receives_every_storage_setting(compose_file: str, var: str) -> None:
    """Each storage variable is forwarded to the backend container."""
    assert var in _backend_environment(compose_file), (
        f"{compose_file} does not pass {var} to the backend, so an operator "
        f"setting it has no effect inside the container."
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_s3_toggle_defaults_to_a_parseable_boolean(compose_file: str) -> None:
    """The toggle must never interpolate to an empty string.

    ``FILE_STORAGE_S3`` is a bool on the config model, and pydantic
    refuses to parse ``""`` — which fails the whole ``Settings`` class at
    import time, so the backend does not start at all. ``${VAR:-false}``
    substitutes for unset *and* empty, so an operator with a blank line
    in their .env still gets a valid value; ``${VAR-false}`` would not.
    """
    value = _backend_environment(compose_file)["FILE_STORAGE_S3"]
    assert ":-" in str(value), (
        f"{compose_file} must default FILE_STORAGE_S3 with ${{VAR:-false}}; "
        "an empty value stops the backend booting."
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_local_dir_matches_the_mounted_volume(compose_file: str) -> None:
    """The mounted volume must cover the path the app actually writes to.

    WORKDIR is /app and the default is the relative ``data/uploads``, so
    the two have to agree or uploads land outside the volume and vanish
    on the next redeploy.
    """
    raw = yaml.safe_load((REPO_ROOT / compose_file).read_text())
    backend = raw["services"]["backend"]

    default = str(_backend_environment(compose_file)["FILE_STORAGE_LOCAL_DIR"])
    assert "data/uploads" in default

    mounts = [m for m in backend["volumes"] if isinstance(m, str)]
    assert any(m.endswith(":/app/data/uploads") for m in mounts), (
        f"{compose_file} must mount a volume at /app/data/uploads"
    )


def test_dockerignore_keeps_secrets_and_uploads_out_of_the_image() -> None:
    """The backend context needs its own ignore file.

    The backend builds with ``context: ./backend``, so the repo-root
    .dockerignore does not apply — without this file ``COPY . .`` bakes
    a developer's real .env into the image, and a local uploads
    directory both ships their files and masks the missing-mountpoint
    permission bug by making the path exist at build time.
    """
    patterns = {
        line.strip()
        for line in (REPO_ROOT / "backend" / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert ".env" in patterns
    assert "data/" in patterns
    # The sample config is documentation and must survive the .env rules.
    assert "!.env.example" in patterns


def test_dockerfile_creates_the_upload_mountpoint() -> None:
    """The image must own /app/data/uploads before the volume is created.

    Docker seeds a new named volume's ownership from the image directory
    only when that directory exists at build time. Miss it and Docker
    creates the mountpoint root:root while the container runs as
    appuser, so every upload fails with PermissionError.
    """
    dockerfile = (REPO_ROOT / "backend" / "Dockerfile").read_text()
    mkdir_line = next(
        line for line in dockerfile.splitlines() if line.startswith("RUN mkdir -p /data/")
    )
    assert "/app/data/uploads" in mkdir_line
    # The chown that follows is what actually applies appuser ownership.
    assert "chown -R appuser:appuser /app /data" in dockerfile
