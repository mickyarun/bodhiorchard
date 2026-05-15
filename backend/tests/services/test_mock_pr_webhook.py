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

"""Pure-function checks on the mock-PR-webhook driver.

The full driver hits Postgres + the local backend; those paths are
exercised by the smoke harness. These tests just cover the pure-function
helpers that have correctness implications:

* HMAC signature shape matches the backend verifier so a real webhook
  POST would round-trip.
* Payload includes the seven fields the backend reads on the merge
  path (so a missing field doesn't 500 the dispatcher silently).
* The mock-files fixture writer merges into an existing JSON file
  instead of clobbering — multi-scenario harness runs accumulate keys
  under one ``BODHI_MOCK_PR_FILES_PATH`` value.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def driver():  # type: ignore[no-untyped-def]
    """Import the script as a module (it lives under ``backend/scripts``)."""
    here = Path(__file__).resolve().parent.parent.parent  # backend/
    spec = importlib.util.spec_from_file_location(
        "mock_pr_webhook_driver",
        str(here / "scripts" / "mock_pr_webhook.py"),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hmac_signature_matches_backend_verifier(driver) -> None:  # type: ignore[no-untyped-def]
    """Round-trip against the same algorithm the webhook handler uses."""
    from app.api.v1.github_webhook import _verify_github_signature

    secret = "test-secret-abc"
    body = b'{"action":"closed"}'
    sig = driver._hmac_signature(secret, body)
    assert sig.startswith("sha256=")
    assert _verify_github_signature(secret, body, sig)
    # And rejects a wrong secret — proves we're not always returning True.
    assert not _verify_github_signature("other-secret", body, sig)


def test_payload_carries_fields_the_handler_reads(driver) -> None:  # type: ignore[no-untyped-def]
    payload = driver._build_payload(
        full_name="owner/example",
        pr_number=42,
        base_sha="basesha",
        head_sha="headsha",
        base_ref="main",
    )
    pr = payload["pull_request"]
    assert payload["action"] == "closed"
    assert pr["merged"] is True
    assert pr["number"] == 42
    assert pr["merge_commit_sha"] == "headsha"
    assert pr["head"]["sha"] == "headsha"
    assert pr["base"]["sha"] == "basesha"
    assert pr["base"]["ref"] == "main"
    repo = payload["repository"]
    assert repo["full_name"] == "owner/example"
    assert repo["owner"]["login"] == "owner"
    assert repo["name"] == "example"


def test_fixture_writer_merges_into_existing_file(  # type: ignore[no-untyped-def]
    driver, tmp_path: Path
) -> None:
    """Append-on-write so a multi-scenario harness session accumulates keys."""
    fixture = tmp_path / "pr_files.json"
    fixture.write_text(json.dumps({"owner/example:7": ["a.py"]}))

    driver._write_mock_files_fixture(
        fixture_path=str(fixture),
        full_name="owner/example",
        pr_number=8,
        changed_files=["b.py"],
    )
    data = json.loads(fixture.read_text())
    assert data == {
        "owner/example:7": ["a.py"],
        "owner/example:8": ["b.py"],
    }


def test_fixture_writer_creates_parent_dirs(  # type: ignore[no-untyped-def]
    driver, tmp_path: Path
) -> None:
    """Mock-files dir may not exist yet on a fresh checkout."""
    fixture = tmp_path / "deep" / "nested" / "pr_files.json"
    driver._write_mock_files_fixture(
        fixture_path=str(fixture),
        full_name="o/r",
        pr_number=1,
        changed_files=[],
    )
    assert fixture.exists()
    assert json.loads(fixture.read_text()) == {"o/r:1": []}


def test_fixture_writer_recovers_from_invalid_json(  # type: ignore[no-untyped-def]
    driver, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Corrupted prior fixture should be overwritten, not raise."""
    fixture = tmp_path / "pr_files.json"
    fixture.write_text("not json {")
    driver._write_mock_files_fixture(
        fixture_path=str(fixture),
        full_name="o/r",
        pr_number=1,
        changed_files=["x.py"],
    )
    assert json.loads(fixture.read_text()) == {"o/r:1": ["x.py"]}
    captured = capsys.readouterr()
    assert "not valid JSON" in captured.err


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/api/v1/webhooks/github",
        "http://127.0.0.1:8000/api/v1/webhooks/github",
        # IPv6 hosts must be bracketed in URLs per RFC 3986.
        "http://[::1]:8000/api/v1/webhooks/github",
    ],
)
def test_guard_allows_loopback_hosts(driver, url: str) -> None:  # type: ignore[no-untyped-def]
    """Loopback hosts pass without --allow-non-localhost."""
    # Must NOT raise.
    driver._guard_target_host(url, allow_non_localhost=False)


def test_guard_refuses_non_loopback_by_default(driver) -> None:  # type: ignore[no-untyped-def]
    """Bare ``--webhook-url`` against a remote host exits before any
    DB read — prevents accidentally replaying a real org's webhook
    secret against production.
    """
    with pytest.raises(SystemExit) as exc:
        driver._guard_target_host(
            "https://prod.example.com/api/v1/webhooks/github",
            allow_non_localhost=False,
        )
    assert "refusing to POST to non-loopback host" in str(exc.value)


def test_guard_allows_non_loopback_with_explicit_flag(  # type: ignore[no-untyped-def]
    driver, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--allow-non-localhost`` is the documented escape hatch."""
    driver._guard_target_host(
        "https://staging.example.com/api/v1/webhooks/github",
        allow_non_localhost=True,
    )
    captured = capsys.readouterr()
    assert "warning: posting to non-loopback host" in captured.err
