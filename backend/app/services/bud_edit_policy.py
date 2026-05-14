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

"""BUD section edit-policy: which fields are editable in which phase.

Each section of a BUD (requirements, tech spec, design, test plan, code
review comments) is owned by exactly one lifecycle phase. Editing those
fields outside the owning phase is rejected with HTTP 409 so out-of-band
edits can't corrupt a BUD that has already moved on.

Layering: :func:`is_section_editable` / :func:`is_design_editable` are
pure domain predicates returning a bool. :func:`assert_section_editable`
/ :func:`assert_design_editable` are HTTP wrappers that raise the 409
on failure. Both wrappers share the same ``bud_section_locked`` detail
shape — see :func:`_raise_section_locked`.

Frontend mirror lives in ``frontend/src/types/index.ts`` (the
``SECTION_EDIT_STATUS`` constant + ``isSectionEditable`` helper). Note
the namespace difference: the frontend constant is keyed by BUD-section
slug (``code_review``, ``testing``) for UI rendering; this backend
constant is keyed by BUDUpdate Pydantic field name
(``code_review_comments``, ``test_plan_md``) because that's what the
PATCH handler iterates over. Both maps encode the same policy — only
the key namespace differs.
"""

from typing import NoReturn

from fastapi import HTTPException, status

from app.models.bud import BUDDocument, BUDStatus

# Maps a BUDUpdate payload field name to the BUDStatus that owns it.
# Fields not in this map (``title``, ``status``, ``assignee_id``,
# ``status_override_reason``, ``metadata_``) are always allowed.
FIELD_OWNING_STATUS: dict[str, BUDStatus] = {
    "requirements_md": BUDStatus.BUD,
    "tech_spec_md": BUDStatus.TECH_ARCH,
    "test_plan_md": BUDStatus.TESTING,
    "code_review_comments": BUDStatus.CODE_REVIEW,
}

# Design content is edited via the dedicated ``bud_designs.py`` endpoints
# rather than the main PATCH, but the rule lives here so the policy has
# a single home.
DESIGN_OWNING_STATUS: BUDStatus = BUDStatus.DESIGN


def is_section_editable(bud: BUDDocument, field: str) -> bool:
    """Return ``True`` iff ``field`` may be written at the BUD's current status.

    Fields outside :data:`FIELD_OWNING_STATUS` (title, assignee, metadata)
    are always editable.
    """
    required = FIELD_OWNING_STATUS.get(field)
    return required is None or bud.status == required


def is_design_editable(bud: BUDDocument) -> bool:
    """Return ``True`` iff the BUD's design rows may be edited right now."""
    return bud.status == DESIGN_OWNING_STATUS


def _raise_section_locked(
    *,
    field: str,
    current: BUDStatus,
    required: BUDStatus,
    subject: str,
) -> NoReturn:
    """Raise the shared 409 ``bud_section_locked`` for any locked section."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "bud_section_locked",
            "field": field,
            "current_status": current.value,
            "required_status": required.value,
            "message": (
                f"Cannot edit {subject} while BUD is in '{current.value}'; "
                f"required phase: '{required.value}'."
            ),
        },
    )


def assert_section_editable(bud: BUDDocument, field: str) -> None:
    """HTTP wrapper: raise 409 if :func:`is_section_editable` returns False."""
    if is_section_editable(bud, field):
        return
    # Safe: predicate failed → field is in FIELD_OWNING_STATUS.
    _raise_section_locked(
        field=field,
        current=bud.status,
        required=FIELD_OWNING_STATUS[field],
        subject=f"'{field}'",
    )


def assert_design_editable(bud: BUDDocument) -> None:
    """HTTP wrapper: raise 409 if :func:`is_design_editable` returns False."""
    if is_design_editable(bud):
        return
    _raise_section_locked(
        field="design",
        current=bud.status,
        required=DESIGN_OWNING_STATUS,
        subject="designs",
    )
