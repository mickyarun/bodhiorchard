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

"""Compose never ships a fixed SECRET_KEY; Full Docker gets one per install."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _backend(compose_file: str) -> dict[str, object]:
    raw = yaml.safe_load((REPO_ROOT / compose_file).read_text())
    return dict(raw["services"]["backend"])


def _service(compose_file: str, name: str) -> dict[str, object]:
    raw = yaml.safe_load((REPO_ROOT / compose_file).read_text())
    return dict(raw["services"][name])


SECRETS = ("SECRET_KEY", "ENCRYPTION_KEY", "COLYSEUS_BRIDGE_SECRET")


def test_secrets_are_only_ever_passed_through() -> None:
    for compose_file in ("docker-compose.yml", "docker-compose.prod.yml"):
        env = dict(_backend(compose_file)["environment"])  # type: ignore[call-overload]
        for name in SECRETS:
            # "${NAME}" or "${NAME:-}": never a value baked into the file.
            assert str(env[name]) in (f"${{{name}}}", f"${{{name}:-}}"), (compose_file, name)
    multiplayer = dict(_service("docker-compose.yml", "multiplayer")["environment"])  # type: ignore[call-overload]
    assert multiplayer["COLYSEUS_BRIDGE_SECRET"] == "${COLYSEUS_BRIDGE_SECRET:-}"


def test_full_docker_keeps_its_generated_key_on_a_volume() -> None:
    volumes = _backend("docker-compose.yml")["volumes"]
    assert "secrets_data:/data/secrets" in volumes  # type: ignore[operator]
    entrypoint = (REPO_ROOT / "backend" / "entrypoint.sh").read_text()
    assert "instance-secrets.sh" in entrypoint and "rotate_from_default_key" in entrypoint
    # Multiplayer reads the generated bridge secret from the same volume.
    assert (
        "secrets_data:/data/secrets:ro" in _service("docker-compose.yml", "multiplayer")["volumes"]
    )  # type: ignore[operator]
