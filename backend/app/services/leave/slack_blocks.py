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

"""Slack Block Kit layouts for leave approvals (pure, no I/O).

The text is the same privacy-safe line as every other leave DM: who, what
kind, which dates. Never the leave type or reason.
"""

import uuid
from collections.abc import Sequence
from typing import Any

APPROVE = "leave_approve"
REJECT = "leave_reject"
OPEN = "leave_open"
REJECT_VIEW = "leave_reject_note"
NOTE_BLOCK = "note"
NOTE_INPUT = "note_input"

Block = dict[str, Any]


def escape(text: str) -> str:
    """Escape Slack's control characters so names can't inject mrkdwn links."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _plain(text: str) -> dict[str, str]:
    return {"type": "plain_text", "text": text}


def _section(text: str) -> Block:
    return {"type": "section", "text": {"type": "mrkdwn", "text": escape(text)}}


def _context(lines: Sequence[str]) -> list[Block]:
    """Small grey lines; none at all when there's nothing to say."""
    if not lines:
        return []
    elements = [{"type": "mrkdwn", "text": escape(line)} for line in lines]
    return [{"type": "context", "elements": elements}]


def approval_blocks(
    text: str, request_id: uuid.UUID, link: str, context: Sequence[str] = ()
) -> list[Block]:
    """The request line, any ``context`` lines, then Approve, Reject and Open."""
    value = str(request_id)
    return [
        _section(text),
        *_context(context),
        {
            "type": "actions",
            "block_id": "leave_decision",
            "elements": [
                {
                    "type": "button",
                    "action_id": APPROVE,
                    "style": "primary",
                    "text": _plain("Approve"),
                    "value": value,
                    "confirm": {
                        "title": _plain("Approve this request?"),
                        "text": {"type": "mrkdwn", "text": escape(text)},
                        "confirm": _plain("Approve"),
                        "deny": _plain("Not yet"),
                    },
                },
                {
                    "type": "button",
                    "action_id": REJECT,
                    "style": "danger",
                    "text": _plain("Reject"),
                    "value": value,
                },
                {"type": "button", "action_id": OPEN, "text": _plain("Open"), "url": link},
            ],
        },
    ]


def outcome_blocks(text: str, outcome: str) -> list[Block]:
    """The request line with its outcome instead of buttons."""
    return [
        _section(text),
        {"type": "context", "elements": [{"type": "mrkdwn", "text": escape(outcome)}]},
    ]


def reject_view(request_id: uuid.UUID, text: str) -> Block:
    """A modal asking why; the reason goes to the requester."""
    return {
        "type": "modal",
        "callback_id": REJECT_VIEW,
        "private_metadata": str(request_id),
        "title": _plain("Reject request"),
        "submit": _plain("Reject"),
        "close": _plain("Cancel"),
        "blocks": [
            _section(text),
            {
                "type": "input",
                "block_id": NOTE_BLOCK,
                "label": _plain("Why? They'll see this note."),
                "element": {
                    "type": "plain_text_input",
                    "action_id": NOTE_INPUT,
                    "multiline": True,
                    "min_length": 3,
                    "max_length": 500,
                },
            },
        ],
    }
