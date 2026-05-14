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

"""BUD section + stage constants and their derived helpers.

Split out of :mod:`app.schemas.bud` so the Pydantic DTO module stays
narrow. This module holds only domain constants and the lookup maps
derived from them — no request/response classes, no SQL, no service
glue. Consumers (handlers, services, notification fan-out) import
from here directly, not from :mod:`app.schemas.bud`.
"""

from typing import NamedTuple


class BUDSectionInfo(NamedTuple):
    """Metadata for a single BUD section."""

    tab: str
    label: str
    exportable: bool


# Canonical section config: DB field → (tab slug, UI label, exportable?)
# Backend notification service, job handlers, and API validation all derive from this.
# Frontend has a mirror in frontend/src/types/index.ts → BUD_SECTIONS.
BUD_SECTIONS: dict[str, BUDSectionInfo] = {
    "requirements_md": BUDSectionInfo("requirements", "Requirements", True),
    "tech_spec_md": BUDSectionInfo("tech-spec", "Tech Spec", True),
    "test_plan_md": BUDSectionInfo("test-plan", "Test Plan", True),
    "testing": BUDSectionInfo("testing", "Testing", False),
    "design": BUDSectionInfo("design", "Design", False),
}

# Derived helpers
SECTION_TO_TAB: dict[str, str] = {k: v.tab for k, v in BUD_SECTIONS.items()}
TAB_TO_SECTION: dict[str, str] = {v.tab: k for k, v in BUD_SECTIONS.items()}
SECTION_LABELS: dict[str, str] = {k: v.label for k, v in BUD_SECTIONS.items()}
VALID_SECTIONS: set[str] = set(BUD_SECTIONS)
EXPORTABLE_SECTIONS: tuple[str, ...] = tuple(k for k, v in BUD_SECTIONS.items() if v.exportable)
SECTION_PATTERN: str = "^(" + "|".join(BUD_SECTIONS) + ")$"

# Maximum number of chat turns reusable on a single CLI session before
# the repository rotates the session id. Keeps prompt cache reads warm on
# short threads but bounds the per-session prompt growth that would
# otherwise blow past the 5-minute cache TTL anyway.
SECTION_SESSION_MESSAGE_CAP: int = 20

# BUD stages in which a user may chat against each section. Enforced as a
# hard 409 at the chat endpoint so a section edit cannot land while the
# BUD is in the wrong lifecycle phase. Mirrors the edit-lock contract in
# :mod:`app.services.bud_edit_policy`: one stage per section, matching
# ``FIELD_OWNING_STATUS`` + ``DESIGN_OWNING_STATUS``. Sections absent from
# this map (e.g. ``test_plan_md``, ``code_review``) reject chat at every
# stage; the surrounding handler surfaces a "chat not available" message.
SECTION_REQUIRED_STAGES: dict[str, frozenset[str]] = {
    "requirements_md": frozenset({"bud"}),
    "tech_spec_md": frozenset({"tech_arch"}),
    "design": frozenset({"design"}),
    "testing": frozenset({"testing"}),
}

# BUD agent task type -> section authored by that agent. Used by the
# originating-agent session bookkeeping so each agent claims a CLI
# session id keyed by the section it owns; chat resumes that exact
# session. ``code_review`` writes to ``test_plan_md`` (test plan + review
# comments share the row) so it shares the test-plan thread.
BUD_AGENT_SECTIONS: dict[str, str] = {
    "bud": "requirements_md",
    "tech_arch": "tech_spec_md",
    "code_review": "test_plan_md",
    "testing": "test_plan_md",
}
