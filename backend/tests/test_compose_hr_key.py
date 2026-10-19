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

"""The backend container must receive the HR encryption key.

Compose forwards only the variables it lists. If HR_ENCRYPTION_KEYS were
missing, production would refuse to start (good) and a dev stack would
show "key not configured" on every HR screen (confusing): catch it here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("compose_file", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_backend_receives_hr_key(compose_file: str) -> None:
    raw = yaml.safe_load((REPO_ROOT / compose_file).read_text())
    env = raw["services"]["backend"]["environment"]
    names = {item.split("=", 1)[0] for item in env} if isinstance(env, list) else set(env)
    assert "HR_ENCRYPTION_KEYS" in names
