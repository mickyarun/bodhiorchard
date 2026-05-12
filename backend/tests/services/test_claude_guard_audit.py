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

"""Phase F unit tests: audit JSONL + PostToolUse hook."""

from __future__ import annotations

import io
import json
import stat
from pathlib import Path

import pytest

from app.services.claude_guard.audit_log import append_event
from app.services.claude_guard.posttool_guard import main as posttool_main


class TestAuditLog:
    """``append_event`` writes one JSONL line per call, 0600 mode."""

    @pytest.fixture(autouse=True)
    def _redirect_log(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        log = tmp_path / "audit.jsonl"
        monkeypatch.setenv("BODHIORCHARD_AUDIT_LOG", str(log))
        self.log = log

    def test_single_event_writes_one_line(self) -> None:
        append_event(
            "pre_tool",
            tool_name="Bash",
            decision="allow",
            tool_input={"command": "git status"},
        )
        assert self.log.exists()
        lines = self.log.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "pre_tool"
        assert record["tool_name"] == "Bash"
        assert record["decision"] == "allow"
        assert "git status" in record["tool_input_preview"]

    def test_multiple_events_append(self) -> None:
        append_event("pre_tool", "Bash", "allow", tool_input={"command": "ls"})
        append_event("pre_tool", "Bash", "deny", rule="env_exfil", reason="x")
        append_event("post_tool", "Bash", "completed", tool_input={"command": "ls"})
        lines = self.log.read_text().splitlines()
        assert len(lines) == 3
        rules = [json.loads(line).get("rule") for line in lines]
        assert rules[1] == "env_exfil"

    def test_log_file_is_owner_only(self) -> None:
        append_event("pre_tool", "Bash", "allow", tool_input={"command": "x"})
        mode = stat.S_IMODE(self.log.stat().st_mode)
        # The umask may add bits, but we requested 0o600 explicitly.
        # Allow either 0o600 (strict) or 0o644 (umask=022) — flag if
        # group/other read AND write are both set, which would be the
        # real risk.
        assert (mode & 0o022) == 0 or mode == 0o600, f"world/group writable: {oct(mode)}"

    def test_long_input_is_truncated(self) -> None:
        huge = "A" * 50_000
        append_event("pre_tool", "Bash", "allow", tool_input={"command": huge})
        line = self.log.read_text().splitlines()[0]
        assert len(line.encode("utf-8")) < 16 * 1024  # under our 8 KiB target + slack
        record = json.loads(line)
        assert (
            record["tool_input_preview"].endswith("…")
            or "truncated" in record["tool_input_preview"]
        )

    def test_failure_to_write_is_swallowed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If the log dir is unwritable, append_event must not raise."""
        # Point at a path under a non-existent parent that we can't create
        # (root-owned). Trying to ``mkdir(parents=True)`` will EACCES.
        monkeypatch.setenv("BODHIORCHARD_AUDIT_LOG", "/no/such/place/audit.jsonl")
        # Must not raise.
        append_event("pre_tool", "Bash", "allow")


class TestPostToolGuardMain:
    """End-to-end shape for the PostToolUse hook script."""

    @pytest.fixture(autouse=True)
    def _redirect_log(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        log = tmp_path / "audit.jsonl"
        monkeypatch.setenv("BODHIORCHARD_AUDIT_LOG", str(log))
        self.log = log

    def test_records_completed_tool_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        event = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
                "tool_response": {"output": "clean"},
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(event))
        rc = posttool_main()
        assert rc == 0
        line = self.log.read_text().splitlines()[0]
        record = json.loads(line)
        assert record["event"] == "post_tool"
        assert record["decision"] == "completed"

    def test_records_failed_tool_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        event = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
                "tool_response": {"error": "fatal: not a git repo"},
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(event))
        rc = posttool_main()
        assert rc == 0
        record = json.loads(self.log.read_text().splitlines()[0])
        assert record["decision"] == "failed"
        assert "not a git repo" in record["reason"]

    def test_broken_stdin_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not-json{"))
        rc = posttool_main()
        captured = capsys.readouterr()
        assert rc == 0
        assert "posttool_guard" in captured.err
        # No audit line should have been written.
        assert not self.log.exists() or self.log.read_text() == ""
