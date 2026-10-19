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


def test_secret_key_is_only_ever_passed_through() -> None:
    for compose_file in ("docker-compose.yml", "docker-compose.prod.yml"):
        env = dict(_backend(compose_file)["environment"])  # type: ignore[call-overload]
        assert str(env["SECRET_KEY"]).startswith("${SECRET_KEY"), compose_file


def test_full_docker_keeps_its_generated_key_on_a_volume() -> None:
    volumes = _backend("docker-compose.yml")["volumes"]
    assert "secrets_data:/data/secrets" in volumes  # type: ignore[operator]
    entrypoint = (REPO_ROOT / "backend" / "entrypoint.sh").read_text()
    assert "/data/secrets" in entrypoint and "token_urlsafe" in entrypoint
