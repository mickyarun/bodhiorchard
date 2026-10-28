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

"""Slack request signing: the v0 HMAC check and the per-org lookup.

The clock is frozen through the module's ``time`` reference so the
five-minute replay window is tested at its exact edges.
"""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import slack_verify
from app.services.slack_verify import MAX_AGE_SECONDS, verified_org, verify_slack_signature

NOW = 1_800_000_000
SECRET = "8f742231b10e8888abcd99yyyzzz85a5"
BODY = b'{"type":"event_callback","team_id":"T1","event":{"text":"caf\xc3\xa9"}}'


def _sign(timestamp: str, body: bytes = BODY, secret: str = SECRET) -> str:
    """The ``X-Slack-Signature`` Slack would send for ``body``."""
    base = f"v0:{timestamp}:{body.decode('utf-8')}".encode()
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``time.time()`` as seen by the verifier."""
    monkeypatch.setattr(slack_verify, "time", SimpleNamespace(time=lambda: float(NOW)))


def test_a_fresh_correctly_signed_request_is_valid() -> None:
    ts = str(NOW - 2)
    assert verify_slack_signature(SECRET, ts, BODY, _sign(ts)) == (True, "")


def test_a_request_exactly_at_the_replay_window_is_still_accepted() -> None:
    ts = str(NOW - MAX_AGE_SECONDS)
    assert verify_slack_signature(SECRET, ts, BODY, _sign(ts))[0] is True


def test_a_request_one_second_past_the_window_is_refused() -> None:
    ts = str(NOW - MAX_AGE_SECONDS - 1)
    valid, reason = verify_slack_signature(SECRET, ts, BODY, _sign(ts))
    assert valid is False
    assert reason == f"timestamp_drift={MAX_AGE_SECONDS + 1}s"


def test_a_timestamp_too_far_in_the_future_is_refused() -> None:
    ts = str(NOW + MAX_AGE_SECONDS + 1)
    valid, reason = verify_slack_signature(SECRET, ts, BODY, _sign(ts))
    assert valid is False
    assert reason.startswith("timestamp_drift=")


@pytest.mark.parametrize("timestamp", ["", "abc", "1.5", "12 34"])
def test_a_non_integer_timestamp_is_refused(timestamp: str) -> None:
    assert verify_slack_signature(SECRET, timestamp, BODY, "v0=00") == (False, "bad_timestamp")


def test_a_tampered_body_is_refused() -> None:
    ts = str(NOW)
    valid, reason = verify_slack_signature(SECRET, ts, BODY + b" ", _sign(ts))
    assert valid is False
    assert reason == f"hmac_mismatch body_len={len(BODY) + 1}"


def test_a_signature_made_with_another_secret_is_refused() -> None:
    ts = str(NOW)
    assert verify_slack_signature(SECRET, ts, BODY, _sign(ts, secret="other"))[0] is False


def test_a_signature_replayed_with_a_new_timestamp_is_refused() -> None:
    """The timestamp is part of the signed base string, so it can't be refreshed."""
    old = str(NOW - 600)
    assert verify_slack_signature(SECRET, str(NOW), BODY, _sign(old))[0] is False


@pytest.mark.parametrize("signature", ["", "v0=", "v1=" + "0" * 64, "garbage-é"])
def test_malformed_signatures_are_refused_without_raising(signature: str) -> None:
    assert verify_slack_signature(SECRET, str(NOW), BODY, signature)[0] is False


def test_the_refusal_reason_never_contains_the_secret() -> None:
    for ts in (str(NOW), str(NOW - 999), "x"):
        _, reason = verify_slack_signature(SECRET, ts, BODY, "v0=bad")
        assert SECRET not in reason


class _Org:
    """The two organisation columns the lookup reads."""

    def __init__(self, team: str, stored_secret: str | None) -> None:
        self.slack_team_id = team
        self.slack_signing_secret = stored_secret


def _wire_orgs(monkeypatch: pytest.MonkeyPatch, *orgs: _Org) -> None:
    """Serve ``orgs`` by team id and decrypt ``enc:<x>`` to ``<x>``."""

    class _Repo:
        def __init__(self, db: Any) -> None:
            pass

        async def get_by_slack_team_id(self, team_id: str) -> _Org | None:
            return next((o for o in orgs if o.slack_team_id == team_id), None)

    monkeypatch.setattr(slack_verify, "OrganizationRepository", _Repo)
    monkeypatch.setattr(
        slack_verify, "decrypt_secret", lambda s: s[4:] if s.startswith("enc:") else ""
    )


async def test_verified_org_returns_the_org_whose_secret_signed_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acme = _Org("T1", f"enc:{SECRET}")
    _wire_orgs(monkeypatch, acme, _Org("T2", "enc:other-secret"))
    ts = str(NOW)
    assert await verified_org(None, "T1", ts, BODY, _sign(ts)) is acme  # type: ignore[arg-type]


async def test_verified_org_refuses_a_request_signed_by_another_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signed with T2's secret but claiming T1 must not resolve to either org."""
    _wire_orgs(monkeypatch, _Org("T1", f"enc:{SECRET}"), _Org("T2", "enc:other-secret"))
    ts = str(NOW)
    signed_by_t2 = _sign(ts, secret="other-secret")
    assert await verified_org(None, "T1", ts, BODY, signed_by_t2) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("team", "timestamp", "signature"),
    [("", str(NOW), "v0=x"), ("T1", "", "v0=x"), ("T1", str(NOW), "")],
)
async def test_verified_org_refuses_requests_missing_a_field(
    monkeypatch: pytest.MonkeyPatch, team: str, timestamp: str, signature: str
) -> None:
    _wire_orgs(monkeypatch, _Org("T1", f"enc:{SECRET}"))
    assert await verified_org(None, team, timestamp, BODY, signature) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("stored", [None, "", "enc-broken"])
async def test_verified_org_refuses_when_the_org_has_no_usable_secret(
    monkeypatch: pytest.MonkeyPatch, stored: str | None
) -> None:
    _wire_orgs(monkeypatch, _Org("T1", stored))
    ts = str(NOW)
    assert await verified_org(None, "T1", ts, BODY, _sign(ts)) is None  # type: ignore[arg-type]


async def test_verified_org_refuses_an_unknown_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_orgs(monkeypatch, _Org("T1", f"enc:{SECRET}"))
    ts = str(NOW)
    assert await verified_org(None, "T9", ts, BODY, _sign(ts)) is None  # type: ignore[arg-type]
