# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Shared helpers for MCP tool handlers.

``require_non_empty`` enforces that required parameters arrive with a
usable value. A missing or empty required field surfaces as a clean
``{"success": false, "error": ...}`` so Claude's agent sees the refusal
and either retries or fails loudly — no silent data loss from writing
empty strings over existing DB rows.

Every write-shaped MCP handler should call this before persisting
anything.
"""

from __future__ import annotations

from typing import Any


def require_non_empty(
    params: dict[str, Any],
    *fields: str,
) -> dict[str, Any] | None:
    """Return an error dict if any required field is missing or empty.

    Empty = ``None``, ``""``, whitespace-only string, empty list/dict/set.
    Numeric ``0`` and ``False`` count as present — they're legitimate
    values for fields like ``sequence: 0``.

    Example::

        err = require_non_empty(params, "title", "requirements_md")
        if err:
            return err

    Returns:
        ``None`` when every field has a value. Otherwise an MCP-style
        error dict the handler can return directly.
    """
    missing = [f for f in fields if not _has_value(params.get(f))]
    if not missing:
        return None

    if len(missing) == 1:
        msg = f"`{missing[0]}` is required"
    else:
        msg = "required parameters missing: " + ", ".join(f"`{m}`" for m in missing)
    return {"success": False, "error": msg}


def _has_value(v: Any) -> bool:
    """Return True when ``v`` is a non-empty, non-whitespace value.

    Treats ``None``, empty strings/collections, and whitespace-only
    strings as missing. Numeric zero and ``False`` count as present —
    they're legitimate values for required fields like ``sequence: 0``.
    """
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list | tuple | dict | set):
        return len(v) > 0
    return True
