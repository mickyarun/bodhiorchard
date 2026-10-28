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

"""Fail a test that reaches a real external service or runs a real agent CLI.

:class:`ExternalCallGuard` patches three doors out of the process:

* ``socket.getaddrinfo`` and ``socket.socket.connect`` refuse any host that
  is not loopback (the test Postgres container is published on loopback).
  Unix sockets (the Docker daemon) are allowed.
* ``socket.socket.connect`` also refuses the dev database and the dev Redis
  named in the app settings, so a test can never write to them by accident.
* ``asyncio.create_subprocess_exec`` and ``subprocess.Popen`` refuse the
  ``claude``, ``codex`` and ``copilot`` binaries. ``git`` still runs, but
  with ``GIT_ALLOW_PROTOCOL=file`` so it can only fetch from and push to
  local repositories (a stray ``https://github.com`` remote fails at once).

Every refusal raises in the caller (so the code under test sees a failed
connection, the same as the network being down) *and* is recorded; the
fixture fails the test at teardown if anything was recorded, so code that
swallows the error still cannot pass silently.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import subprocess
from typing import Any
from urllib.parse import urlsplit

import pytest

from app.config import settings

AGENT_BINARIES = frozenset({"claude", "codex", "copilot"})
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


class ExternalCallBlockedError(ConnectionRefusedError):
    """Raised in place of a real network connection or agent CLI spawn."""


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _settings_port(url: str, default: int) -> int | None:
    """Port of a configured dev service, or None when it is not on loopback."""
    parts = urlsplit(url.replace("+asyncpg", ""))
    if parts.hostname is None or not _is_loopback(parts.hostname):
        return None
    return parts.port or default


def binary_name(argv0: object) -> str:
    """Basename of an argv[0] (``/usr/local/bin/claude`` → ``claude``)."""
    if isinstance(argv0, str | os.PathLike):
        return os.path.basename(os.fspath(argv0))
    return ""


class ExternalCallGuard:
    """Records and refuses calls that would leave the test process."""

    def __init__(self) -> None:
        self.violations: list[str] = []
        self.allowed_ports: set[int] = set()
        self._blocked_ports = {
            port
            for port in (
                _settings_port(settings.db.database_url, 5432),
                _settings_port(settings.redis.redis_url, 6379),
            )
            if port is not None
        }

    def allow_port(self, port: int) -> None:
        """Let a loopback port through even if it matches a dev service port."""
        self.allowed_ports.add(port)

    def _refuse(self, what: str) -> ExternalCallBlockedError:
        self.violations.append(what)
        return ExternalCallBlockedError(f"blocked by ExternalCallGuard: {what}")

    def check_host(self, host: object) -> None:
        """Refuse DNS lookups for anything that is not loopback."""
        if host is None:
            return
        text = host.decode() if isinstance(host, bytes) else str(host)
        if not _is_loopback(text):
            raise self._refuse(f"network lookup for {text!r}")

    def check_address(self, family: int, address: Any) -> None:
        """Refuse connects to non-loopback hosts and to dev service ports."""
        if family == getattr(socket, "AF_UNIX", -1):
            return
        if not isinstance(address, tuple) or len(address) < 2:
            return
        host, port = str(address[0]), int(address[1])
        if not _is_loopback(host):
            raise self._refuse(f"connect to {host}:{port}")
        if port in self._blocked_ports and port not in self.allowed_ports:
            raise self._refuse(f"connect to dev service on loopback port {port}")

    def check_argv(self, argv0: object) -> None:
        """Refuse spawning a real agent CLI."""
        name = binary_name(argv0)
        if name in AGENT_BINARIES:
            raise self._refuse(f"spawn of the real {name!r} binary")

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch the socket and subprocess entry points for one test."""
        real_getaddrinfo = socket.getaddrinfo
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex
        real_spawn = asyncio.create_subprocess_exec
        real_popen_init = subprocess.Popen.__init__

        def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
            self.check_host(host)
            return real_getaddrinfo(host, *args, **kwargs)

        def connect(sock: socket.socket, address: Any) -> None:
            self.check_address(sock.family, address)
            real_connect(sock, address)

        def connect_ex(sock: socket.socket, address: Any) -> int:
            self.check_address(sock.family, address)
            return real_connect_ex(sock, address)

        async def spawn(program: Any, *args: Any, **kwargs: Any) -> Any:
            self.check_argv(program)
            return await real_spawn(program, *args, **kwargs)

        def popen_init(proc: subprocess.Popen[Any], args: Any, *rest: Any, **kw: Any) -> None:
            first = args[0] if isinstance(args, list | tuple) and args else args
            self.check_argv(first)
            real_popen_init(proc, args, *rest, **kw)

        monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
        monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        monkeypatch.setattr(socket.socket, "connect", connect)
        monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(subprocess.Popen, "__init__", popen_init)

    def assert_clean(self) -> None:
        """Fail the test if anything tried to leave the process."""
        if self.violations:
            pytest.fail(
                "test tried to reach a real external service:\n  - "
                + "\n  - ".join(self.violations),
                pytrace=False,
            )
