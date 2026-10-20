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

"""backend/docker/instance-secrets.sh: per-install secrets for Full Docker."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.core.hr_crypto import decrypt, encrypt, parse_keyring

SCRIPT = Path(__file__).resolve().parents[2] / "docker" / "instance-secrets.sh"
SHOW = 'echo "$SECRET_KEY|$ENCRYPTION_KEY|$COLYSEUS_BRIDGE_SECRET|${ENCRYPTION_KEY_PREVIOUS:-}"'
LEGACY = "change-me-encryption-key"


def _run(
    commands: str, path_first: Path | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    path = f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"
    if path_first is not None:
        path = f"{path_first}:{path}"
    return subprocess.run(
        ["sh", "-c", f"set -e; . '{SCRIPT}'; {commands}"],
        env={"PATH": path, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_full_docker_install_gets_its_own_secrets(tmp_path: Path) -> None:
    secrets_dir = str(tmp_path / "s")
    first = _run(SHOW, INSTANCE_SECRETS_DIR=secrets_dir)
    assert first.returncode == 0, first.stderr
    secret, key, bridge, previous = first.stdout.strip().split("|")
    assert len({secret, key, bridge}) == 3 and all(len(v) >= 40 for v in (secret, key, bridge))
    # The old shared key stays readable so anything under it is re-encrypted.
    assert previous == LEGACY
    again = _run(SHOW, INSTANCE_SECRETS_DIR=secrets_dir)
    assert again.stdout == first.stdout


def test_values_from_the_environment_win_and_the_legacy_key_is_still_readable(
    tmp_path: Path,
) -> None:
    result = _run(
        SHOW,
        INSTANCE_SECRETS_DIR=str(tmp_path / "s"),
        SECRET_KEY="mine",
        ENCRYPTION_KEY="my-key",
        COLYSEUS_BRIDGE_SECRET="my-bridge",
        ENCRYPTION_KEY_PREVIOUS="older",
        HR_ENCRYPTION_KEYS="mine:a2V5",
    )
    assert result.stdout.strip() == f"mine|my-key|my-bridge|older,{LEGACY}"
    assert not (tmp_path / "s").exists()


def test_nothing_happens_outside_full_docker() -> None:
    result = _run(SHOW + "; rotate_from_default_key; echo done")
    assert result.stdout.strip().splitlines() == ["|||", "done"]


def test_an_unwritable_volume_stops_the_start(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    try:
        result = _run(SHOW, INSTANCE_SECRETS_DIR=str(locked / "s"))
    finally:
        locked.chmod(0o700)
    assert result.returncode != 0
    assert "Can't write" in result.stderr


def test_a_failed_rotation_does_not_stop_the_start(tmp_path: Path) -> None:
    secrets_dir = str(tmp_path / "s")
    # Generate the secrets with the real python first.
    assert _run("true", INSTANCE_SECRETS_DIR=secrets_dir).returncode == 0
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for code, expected in ((0, ""), (1, "couldn't be re-encrypted")):
        stub = stubs / "python"
        stub.write_text(f'#!/bin/sh\necho "python $*"\nexit {code}\n')
        stub.chmod(0o755)
        result = _run(
            "rotate_from_default_key; echo started",
            path_first=stubs,
            INSTANCE_SECRETS_DIR=secrets_dir,
        )
        assert result.returncode == 0, result.stderr
        assert "python -m scripts.rotate_encryption_key --rotate" in result.stdout
        assert result.stdout.strip().endswith("started")
        assert expected in result.stderr


def test_the_bridge_secret_lives_apart_from_the_backend_keys(tmp_path: Path) -> None:
    result = _run(
        SHOW,
        INSTANCE_SECRETS_DIR=str(tmp_path / "keys"),
        BRIDGE_SECRET_DIR=str(tmp_path / "bridge"),
    )
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (tmp_path / "bridge").iterdir()) == ["colyseus_bridge_secret"]
    assert "colyseus_bridge_secret" not in [p.name for p in (tmp_path / "keys").iterdir()]
    # Readable by the multiplayer container's non-root user.
    assert (tmp_path / "bridge" / "colyseus_bridge_secret").stat().st_mode & 0o044 == 0o044


def test_a_full_docker_install_gets_its_own_hr_keyring(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "s"
    first = _run('echo "$HR_ENCRYPTION_KEYS"', INSTANCE_SECRETS_DIR=str(secrets_dir))
    assert first.returncode == 0, first.stderr
    raw = first.stdout.strip()
    ring = parse_keyring(raw)
    assert len(ring.keys) == 1 and ring.current.startswith("k")
    assert decrypt(encrypt(b"pan", "aad", ring), "aad", ring) == b"pan"
    # Generated once: later starts reuse it, or every record becomes unreadable.
    again = _run('echo "$HR_ENCRYPTION_KEYS"', INSTANCE_SECRETS_DIR=str(secrets_dir))
    assert again.stdout.strip() == raw
    assert (secrets_dir / "hr_encryption_keys").stat().st_mode & 0o077 == 0


def test_an_hr_keyring_from_the_environment_wins(tmp_path: Path) -> None:
    result = _run(
        'echo "$HR_ENCRYPTION_KEYS"',
        INSTANCE_SECRETS_DIR=str(tmp_path / "s"),
        HR_ENCRYPTION_KEYS="mine:a2V5",
    )
    assert result.stdout.strip() == "mine:a2V5"
    assert not (tmp_path / "s" / "hr_encryption_keys").exists()
