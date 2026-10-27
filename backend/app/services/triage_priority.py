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

"""Map the free-text priority a triage request carries onto ``BUDPriority``.

Kept apart from the Slack intake flow so the API schema can show the
priority an approved BUD will get without importing that flow.
"""

import structlog

from app.models.bud import BUDPriority

logger = structlog.get_logger(__name__)

# Free-text priority synonyms accepted from the triage form / Slack
# replies. Keys are lowercase and contain only [a-z0-9] — the lookup
# strips every other character first, so ``"P-0"``, ``"P0!"`` and
# ``"sev 0"`` all collapse to ``"p0"``. Anything not in this map (or
# NULL / empty) falls through to the default P2, matching the column's
# NOT NULL DEFAULT 'P2'.
_PRIORITY_ALIASES: dict[str, BUDPriority] = {
    "p0": BUDPriority.P0,
    "sev0": BUDPriority.P0,
    "critical": BUDPriority.P0,
    "urgent": BUDPriority.P0,
    "blocker": BUDPriority.P0,
    "asap": BUDPriority.P0,
    "highest": BUDPriority.P0,
    "p1": BUDPriority.P1,
    "sev1": BUDPriority.P1,
    "high": BUDPriority.P1,
    "p2": BUDPriority.P2,
    "sev2": BUDPriority.P2,
    "medium": BUDPriority.P2,
    "normal": BUDPriority.P2,
    "p3": BUDPriority.P3,
    "sev3": BUDPriority.P3,
    "low": BUDPriority.P3,
    "minor": BUDPriority.P3,
    "lowest": BUDPriority.P3,
    "nicetohave": BUDPriority.P3,
}


def normalize_triage_priority(raw: str | None) -> BUDPriority:
    """Map a free-text priority value from triage into ``BUDPriority``.

    The triage form has historically accepted any string. The structured
    BUD column needs one of P0..P3, so unknown / missing values default
    to P2 (matching the column's server_default).

    Unknown-but-truthy values are logged so operators can spot bad
    triage input — empty / NULL stays silent because that's the
    documented "no opinion" case.
    """
    if not raw:
        return BUDPriority.P2
    key = "".join(ch for ch in raw.lower() if ch.isalnum())
    if key in _PRIORITY_ALIASES:
        return _PRIORITY_ALIASES[key]
    logger.warning("triage_priority_unknown", raw=raw)
    return BUDPriority.P2
