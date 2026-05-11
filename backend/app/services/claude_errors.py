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

"""Translate raw Claude CLI termination conditions into structured error codes.

The Claude subprocess (``claude_runner.py``) can fail for several reasons:
the CLI binary is missing, the wall-clock timeout fires, the run exhausts
its ``max_turns`` budget, or the process exits non-zero for some other
reason. Historically the runner stuffed all of these into an ad-hoc
``error: str`` and shipped the raw text to the frontend, where users saw
opaque messages like ``Claude CLI: error_max_turns after 10 turns``.

This module is the single source of truth for mapping each terminal
condition to a stable ``ClaudeErrorCode`` plus a human-readable fallback
message. The frontend uses the code to render rich UI (router-link to
settings, role-aware CTAs); the message is the safety net for callers
that don't pass the code through.
"""

from enum import StrEnum

_DEFAULT_TURNS_PLACEHOLDER = "?"


class ClaudeErrorCode(StrEnum):
    """Stable identifiers for Claude subprocess terminal conditions.

    Values are kept short and snake_case so they round-trip cleanly
    through JSON and match the conventions in ``schemas/jobs.py``.
    """

    MAX_TURNS = "max_turns"
    TIMEOUT = "timeout"
    BINARY_MISSING = "binary_missing"
    UNKNOWN = "unknown"


# Maps raw ``error_subtype`` strings emitted by the Claude CLI's final
# JSON ``result`` event to our internal codes. Unknown subtypes fall
# through to ``UNKNOWN`` so the frontend still gets a friendly fallback.
_SUBTYPE_TO_CODE: dict[str, ClaudeErrorCode] = {
    "error_max_turns": ClaudeErrorCode.MAX_TURNS,
}


def _max_turns_message(turns: int | None) -> str:
    label = str(turns) if turns is not None else _DEFAULT_TURNS_PLACEHOLDER
    return (
        f"The AI agent reached its maximum turns limit ({label}). "
        "Increase max_turns in Settings → Agent Prompts, or contact your admin."
    )


def _timeout_message(timeout_s: int | None) -> str:
    label = f"{timeout_s} seconds" if timeout_s is not None else "the configured timeout"
    return (
        f"The AI agent timed out after {label}. Try again, or contact your "
        "admin if this keeps happening."
    )


def _binary_missing_message() -> str:
    return "The Claude CLI is not installed on this server. Contact your admin to install it."


def _unknown_message(detail: str | None) -> str:
    if detail:
        return f"The AI agent failed: {detail}. Contact your admin if this persists."
    return "The AI agent failed unexpectedly. Contact your admin if this persists."


def from_subtype(subtype: str | None, *, turns: int | None = None) -> tuple[ClaudeErrorCode, str]:
    """Translate a CLI ``error_subtype`` (e.g. ``error_max_turns``)."""
    code = _SUBTYPE_TO_CODE.get(subtype or "", ClaudeErrorCode.UNKNOWN)
    if code is ClaudeErrorCode.MAX_TURNS:
        return code, _max_turns_message(turns)
    if subtype:
        detail = f"{subtype} after {turns} turns" if turns is not None else subtype
    else:
        detail = None
    return code, _unknown_message(detail)


def from_timeout(timeout_s: int | None) -> tuple[ClaudeErrorCode, str]:
    """Translate an ``asyncio.TimeoutError`` from the runner."""
    return ClaudeErrorCode.TIMEOUT, _timeout_message(timeout_s)


def from_binary_missing() -> tuple[ClaudeErrorCode, str]:
    """Translate a ``FileNotFoundError`` for the ``claude`` binary."""
    return ClaudeErrorCode.BINARY_MISSING, _binary_missing_message()


def from_returncode(returncode: int, detail: str | None) -> tuple[ClaudeErrorCode, str]:
    """Translate a non-zero CLI exit code with an optional diagnostic detail."""
    suffix = f"exit code {returncode}"
    full_detail = f"{suffix}; {detail}" if detail else suffix
    return ClaudeErrorCode.UNKNOWN, _unknown_message(full_detail)
