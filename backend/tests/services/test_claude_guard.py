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

"""Phase A unit tests for the ``claude_guard`` security module."""

from __future__ import annotations

import os
import sys

import pytest

from app.services.claude_guard import apply_subprocess_rlimits, build_claude_env


class TestBuildClaudeEnv:
    """Env whitelist must drop secrets while keeping plumbing."""

    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Start each test from a deterministic env."""
        monkeypatch.setattr(os, "environ", {})

    def test_whitelisted_keys_pass_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/Users/test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        env = build_claude_env(None)

        assert env["PATH"] == "/usr/bin"
        assert env["HOME"] == "/Users/test"
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-test"

    @pytest.mark.parametrize(
        "secret_key",
        [
            "ENCRYPTION_KEY",
            "DATABASE_URL",
            "SECRET_KEY",
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "BODHIORCHARD_MCP_TOKEN",
            "BODHIORCHARD_DB_PASSWORD",
            "OPENAI_API_KEY",
            "SLACK_BOT_TOKEN",
            "NPM_TOKEN",
        ],
    )
    def test_secrets_are_dropped(self, monkeypatch: pytest.MonkeyPatch, secret_key: str) -> None:
        """The whitelist must not leak any of the known secret vars."""
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv(secret_key, "super-secret-value")

        env = build_claude_env(None)

        assert secret_key not in env
        assert "super-secret-value" not in env.values()

    def test_env_extra_merges_on_top(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/usr/bin")
        extra = {"AGENT_CONTEXT": "bud-123", "PATH": "/override/path"}

        env = build_claude_env(extra)

        assert env["AGENT_CONTEXT"] == "bud-123"
        # ``env_extra`` wins over whitelisted parent value — caller is trusted.
        assert env["PATH"] == "/override/path"

    def test_telemetry_knobs_default_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/usr/bin")
        env = build_claude_env(None)
        assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
        assert env["DISABLE_AUTOUPDATER"] == "1"

    def test_caller_can_override_telemetry_knobs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/usr/bin")
        env = build_claude_env({"DISABLE_AUTOUPDATER": "0"})
        assert env["DISABLE_AUTOUPDATER"] == "0"

    def test_returns_fresh_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Result must be a fresh dict so callers can hand it to asyncio."""
        monkeypatch.setenv("PATH", "/usr/bin")
        env = build_claude_env(None)
        assert isinstance(env, dict)
        env["MUTATION_TEST"] = "x"
        env2 = build_claude_env(None)
        assert "MUTATION_TEST" not in env2

    def test_none_env_extra_is_safe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/usr/bin")
        env = build_claude_env(None)
        assert "PATH" in env


class TestApplySubprocessRlimits:
    """``preexec_fn`` builder must be platform-aware."""

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
    def test_returns_callable_on_unix(self) -> None:
        fn = apply_subprocess_rlimits()
        assert callable(fn)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_returns_none_on_windows(self) -> None:
        assert apply_subprocess_rlimits() is None

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
    def test_callable_does_not_raise_under_generous_limits(self) -> None:
        """Calling the preexec hook in-process must not crash the test runner.

        With generous caps (64 GiB AS, 65536 procs) the call is a no-op in
        practice; the goal is only to verify the wiring does not raise.
        """
        fn = apply_subprocess_rlimits(
            address_space_bytes=64 * 1024 * 1024 * 1024,
            process_cap=65536,
        )
        assert fn is not None
        # Must not raise. setsid may fail under pytest; the hook swallows it.
        fn()


class TestClaudeRunnerIntegration:
    """End-to-end shape: ``run_claude_code`` builds the right argv + env.

    These tests stub the subprocess spawn so we can inspect the command
    list, env mapping, and tempfile mode without launching real ``claude``.
    """

    @pytest.mark.asyncio
    async def test_add_dir_pins_workspace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        """``run_claude_code`` must append ``--add-dir <abs-cwd>`` to argv."""
        from app.services import claude_runner

        captured: dict[str, object] = {}

        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return b'{"type":"result","result":"ok","total_cost_usd":0}', b""

        async def _fake_spawn(*args: object, **kwargs: object) -> _FakeProc:
            captured["args"] = args
            captured["kwargs"] = kwargs
            return _FakeProc()

        monkeypatch.setattr(claude_runner.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(claude_runner.asyncio, "create_subprocess_exec", _fake_spawn)

        await claude_runner.run_claude_code(
            prompt="ping",
            config=claude_runner.ClaudeRunnerConfig(timeout_seconds=5),
            working_dir=str(tmp_path),
        )

        argv = list(captured["args"])  # type: ignore[arg-type]
        assert "--add-dir" in argv, f"missing --add-dir in {argv}"
        idx = argv.index("--add-dir")
        assert argv[idx + 1] == str(tmp_path)

    @pytest.mark.asyncio
    async def test_env_passed_to_spawn_excludes_secrets(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        """The env handed to the subprocess must NOT contain secrets."""
        from app.services import claude_runner

        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("DATABASE_URL", "postgres://leak")
        monkeypatch.setenv("ENCRYPTION_KEY", "fernet-leak")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ok")

        captured: dict[str, object] = {}

        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return b'{"type":"result","result":"ok","total_cost_usd":0}', b""

        async def _fake_spawn(*args: object, **kwargs: object) -> _FakeProc:
            captured["env"] = kwargs.get("env")
            return _FakeProc()

        monkeypatch.setattr(claude_runner.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(claude_runner.asyncio, "create_subprocess_exec", _fake_spawn)

        await claude_runner.run_claude_code(
            prompt="ping",
            config=claude_runner.ClaudeRunnerConfig(timeout_seconds=5),
            working_dir=str(tmp_path),
        )

        env = captured["env"]
        assert isinstance(env, dict)
        assert "DATABASE_URL" not in env
        assert "ENCRYPTION_KEY" not in env
        assert env.get("ANTHROPIC_API_KEY") == "sk-ant-ok"
        assert env.get("PATH") == "/usr/bin"

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
    async def test_mcp_config_tmpfile_is_owner_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        """MCP config tempfile written by ``run_claude_code`` must be 0600."""
        from app.services import claude_runner

        captured: dict[str, object] = {}

        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return b'{"type":"result","result":"ok","total_cost_usd":0}', b""

        async def _fake_spawn(*args: object, **kwargs: object) -> _FakeProc:
            argv = list(args)
            try:
                idx = argv.index("--mcp-config")
                captured["mcp_path"] = argv[idx + 1]
                captured["mode"] = os.stat(argv[idx + 1]).st_mode & 0o777
            except ValueError:
                captured["mcp_path"] = None
            return _FakeProc()

        monkeypatch.setattr(claude_runner.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(claude_runner.asyncio, "create_subprocess_exec", _fake_spawn)

        mcp = claude_runner.MCPServerConfig(
            backend_url="http://localhost:8000",
            mcp_token="tok-secret",
            tool_names=["code_query"],
        )
        await claude_runner.run_claude_code(
            prompt="ping",
            config=claude_runner.ClaudeRunnerConfig(mcp=mcp, timeout_seconds=5),
            working_dir=str(tmp_path),
        )

        assert captured.get("mcp_path") is not None
        assert captured["mode"] == 0o600, f"got mode {oct(captured['mode'])}"  # type: ignore[arg-type, call-overload]
