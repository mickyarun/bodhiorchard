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

:class:`ExternalCallGuard` patches the doors out of the process:

* ``socket.getaddrinfo`` and ``socket.socket.connect`` refuse any host that
  is not loopback (the test Postgres container is published on loopback).
  Unix sockets (the Docker daemon) are allowed.
* Loopback connects to the local services named in the app settings (dev
  database, Redis, backend, frontend, multiplayer) and to Ollama are refused,
  so a test can never write to them by accident.
* ``asyncio.create_subprocess_exec`` and ``subprocess.Popen`` refuse any
  command line that runs ``claude``, ``codex`` or ``copilot``, wherever the
  binary appears in it (wrappers such as ``sandbox-exec`` or ``env`` too).
  ``git`` still runs, with ``GIT_ALLOW_PROTOCOL=file``, so it can only talk
  to local repositories.
* Env switches that would route around the fakes (the macOS agent sandbox,
  the PR-files mock file) are cleared.

Every refusal raises in the caller (the code sees a failed connection, the
same as the network being down) *and* is recorded; :meth:`assert_clean`
fails the test at teardown if anything was recorded, so code that swallows
the error still cannot pass silently.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import shlex
import socket
import subprocess
from typing import Any
from urllib.parse import urlsplit

import pytest

from app.config import settings

AGENT_BINARIES = frozenset({"claude", "codex", "copilot"})
OLLAMA_PORT = 11434
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
_CLEARED_ENV = ("BODHIORCHARD_HYBRID_SANDBOX", "BODHI_MOCK_PR_FILES_PATH")


class ExternalCallBlockedError(ConnectionRefusedError):
    """Raised in place of a real network connection or agent CLI spawn."""


def is_loopback(host: str) -> bool:
    """True for ``localhost`` and loopback addresses (IPv4-mapped included)."""
    if host in _LOOPBACK_NAMES:
        return True
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


def settings_port(url: str) -> int | None:
    """Port of a configured local service, or None when it is not on loopback."""
    parts = urlsplit(url.replace("+asyncpg", ""))
    if parts.hostname is None or not is_loopback(parts.hostname):
        return None
    defaults = {"postgresql": 5432, "redis": 6379, "http": 80, "https": 443, "ws": 80}
    return parts.port or defaults.get(parts.scheme)


def _local_service_ports() -> set[int]:
    urls = (
        settings.db.database_url,
        settings.redis.redis_url,
        settings.mcp_backend_url,
        settings.public_url,
        settings.frontend_url,
        settings.colyseus.url,
    )
    return {p for p in (settings_port(u) for u in urls) if p is not None} | {OLLAMA_PORT}


def binary_name(arg: object) -> str:
    """Basename of one argv element (``/usr/local/bin/claude`` → ``claude``)."""
    if isinstance(arg, bytes):
        arg = arg.decode(errors="replace")
    if isinstance(arg, str | os.PathLike):
        return os.path.basename(os.fspath(arg))
    return ""


def _argv_words(args: object) -> list[object]:
    if isinstance(args, str | bytes):
        text = args.decode(errors="replace") if isinstance(args, bytes) else args
        try:
            words = shlex.split(text)
        except ValueError:
            words = text.split()
        return list(words)
    if isinstance(args, list | tuple):
        return list(args)
    return [args]


class ExternalCallGuard:
    """Records and refuses calls that would leave the test process."""

    def __init__(self) -> None:
        self.violations: list[str] = []
        self.allowed_ports: set[int] = set()
        self.blocked_ports = _local_service_ports()

    def allow_port(self, port: int) -> None:
        """Let a loopback port through even if it matches a local service port."""
        self.allowed_ports.add(port)

    def _refuse(self, what: str) -> ExternalCallBlockedError:
        self.violations.append(what)
        return ExternalCallBlockedError(f"blocked by ExternalCallGuard: {what}")

    def check_host(self, host: object) -> None:
        """Refuse DNS lookups for anything that is not loopback."""
        if host is None:
            return
        text = host.decode() if isinstance(host, bytes) else str(host)
        if not is_loopback(text):
            raise self._refuse(f"network lookup for {text!r}")

    def check_address(self, family: int, address: Any) -> None:
        """Refuse connects to non-loopback hosts and to local service ports."""
        if family == getattr(socket, "AF_UNIX", -1):
            return
        if not isinstance(address, tuple) or len(address) < 2:
            return
        host, port = str(address[0]), int(address[1])
        if not is_loopback(host):
            raise self._refuse(f"connect to {host}:{port}")
        if port in self.blocked_ports and port not in self.allowed_ports:
            raise self._refuse(f"connect to a local service on loopback port {port}")

    def check_argv(self, args: object) -> None:
        """Refuse any command line that runs a real agent CLI."""
        for word in _argv_words(args):
            name = binary_name(word)
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
            self.check_argv([program, *args])
            return await real_spawn(program, *args, **kwargs)

        def popen_init(proc: subprocess.Popen[Any], args: Any, *rest: Any, **kw: Any) -> None:
            self.check_argv(args)
            real_popen_init(proc, args, *rest, **kw)

        for name in _CLEARED_ENV:
            monkeypatch.delenv(name, raising=False)
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
