# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Backend SSH deploy keypair for cloning private GitHub repositories.

The first time we need to clone an ``ssh://`` or ``git@…`` URL we lazily
generate an ed25519 keypair and store it under ``/data/ssh/``, which is a
persistent Docker volume in Full Docker mode. The public half is exposed
through ``GET /api/setup/deploy-key`` so the user can paste it into GitHub's
*Repo Settings → Deploy keys*; the private half never leaves the container.

Why ed25519: small (80 chars pub), fast, GitHub-supported since 2022, no
key-size decisions to make. Why one key per installation: a deploy key on
GitHub is scoped to a single repo, so a multi-repo setup asks the user to
paste the same public key into each repo's deploy-key list. That's lower
friction than generating a separate key per repo and remains scoped to the
repos the user explicitly opts in.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

logger = structlog.get_logger(__name__)

SSH_DIR = Path("/data/ssh")
PRIVATE_KEY_PATH = SSH_DIR / "id_ed25519"
PUBLIC_KEY_PATH = SSH_DIR / "id_ed25519.pub"
KNOWN_HOSTS_PATH = SSH_DIR / "known_hosts"

# GitHub's current SSH host keys (ssh-keyscan github.com). Hardcoded because
# (a) we want zero DNS at first boot, (b) key rotations are rare and publicly
# announced, (c) trusting an arbitrary first-seen key would defeat the point
# of StrictHostKeyChecking.
GITHUB_KNOWN_HOSTS = """\
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
"""


def _ensure_dir() -> None:
    """Ensure ``/data/ssh`` exists with mode 0700 (private key hygiene)."""
    SSH_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def _generate_keypair() -> None:
    """Create a fresh ed25519 keypair under ``/data/ssh/``.

    The private key is written with mode 0600 — OpenSSH refuses to use keys
    with looser permissions.
    """
    _ensure_dir()
    private_key = ed25519.Ed25519PrivateKey.generate()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    # GitHub shows the key's comment in its UI — make it obvious what it's for.
    public_line = public_bytes + b" bodhiorchard@deploy\n"

    PRIVATE_KEY_PATH.write_bytes(private_bytes)
    PRIVATE_KEY_PATH.chmod(0o600)
    PUBLIC_KEY_PATH.write_bytes(public_line)
    PUBLIC_KEY_PATH.chmod(0o644)
    logger.info("ssh_deploy_key_generated", path=str(PUBLIC_KEY_PATH))


def _ensure_known_hosts() -> None:
    """Write the bundled GitHub host keys if known_hosts is missing/empty."""
    _ensure_dir()
    if KNOWN_HOSTS_PATH.exists() and KNOWN_HOSTS_PATH.stat().st_size > 0:
        return
    KNOWN_HOSTS_PATH.write_text(GITHUB_KNOWN_HOSTS)
    KNOWN_HOSTS_PATH.chmod(0o644)


def ensure_deploy_key() -> None:
    """Lazy-init: generate keys and seed known_hosts if either is missing."""
    if not PRIVATE_KEY_PATH.exists() or not PUBLIC_KEY_PATH.exists():
        _generate_keypair()
    _ensure_known_hosts()


def get_public_key() -> str:
    """Return the one-line SSH public key, generating it on first call."""
    ensure_deploy_key()
    return PUBLIC_KEY_PATH.read_text().strip()


def git_ssh_command() -> str:
    """Build ``$GIT_SSH_COMMAND`` for clones that should use the deploy key.

    ``IdentitiesOnly=yes`` prevents ssh from offering any keys besides ours
    (otherwise a random agent-forwarded key could get tried first and
    confuse GitHub's auth).
    """
    ensure_deploy_key()
    return (
        f"ssh -i {PRIVATE_KEY_PATH} "
        f"-o IdentitiesOnly=yes "
        f"-o UserKnownHostsFile={KNOWN_HOSTS_PATH} "
        f"-o StrictHostKeyChecking=yes "
        f"-o PasswordAuthentication=no"
    )


def ssh_env() -> dict[str, str]:
    """Return an env overlay to pass to ``subprocess`` for SSH-auth git calls."""
    return {**os.environ, "GIT_SSH_COMMAND": git_ssh_command()}
