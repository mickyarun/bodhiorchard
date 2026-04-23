# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Prompt-section formatters for the AI-PERT estimation LLM call.

Pure string formatting — no DB, no LLM, no math. Lives apart from
``estimation_llm`` so the latter stays focused on the prompt assembly +
LLM I/O loop, and so each formatter can be unit-tested without
constructing the full prompt around it.

Every formatter returns a string that already includes its trailing
newline (or empty when the section should be omitted), so the caller
can simply concatenate without checking emptiness.
"""

from __future__ import annotations

import re

from app.models.bud import BUDDocument

# Cap for verbose Markdown sections passed to the LLM. 20K characters is
# well below the model's context limit but large enough that practical
# PRDs and tech specs are not truncated. Centralised so prompt size
# growth shows up in one place.
_MAX_SECTION_CHARS = 20_000

# How many wireframe annotation lines to inline before truncating; full
# wireframe HTML is too noisy and the leading annotations carry the
# load-bearing signals.
_MAX_ANNOTATIONS_INLINED = 8


def format_capacity_block(
    capacity_summary: list[tuple[str, float, str]] | None,
) -> str:
    """Render the per-role capacity context for the prompt.

    Empty / None summary → empty string (the prompt simply omits the
    block, behaviour-preserving for callers that have not been migrated).
    Pre-formatted tuples (role, capacity, narration) keep all
    prompt-formatting concerns here, away from the engine.
    """
    if not capacity_summary:
        return ""
    lines = ["Team capacity right now (1.0 = fully available):"]
    for role, capacity, narration in capacity_summary:
        lines.append(f"  {role}: {capacity:.2f} ({narration})")
    return "\n".join(lines) + "\n"


def format_bug_line(bug_context: dict | None) -> str:
    """One-line open-bug summary, or empty when there are none / no data."""
    if not bug_context:
        return ""
    count = bug_context.get("open_bug_count", 0)
    if count <= 0:
        return ""
    return f"Open bugs against this BUD: {count}\n"


def format_historical_note(historical_n_used: int, complexity: int) -> str:
    """Tell the LLM when the engine is mixing in past cycle times.

    Helps the model avoid over-padding for safety — if 7 comparable
    BUDs already inform the forecast, the LLM should give an honest
    central estimate rather than a defensive one. Empty when no past
    data is in play.
    """
    if historical_n_used <= 0:
        return ""
    return (
        f"Historical mix: {historical_n_used} comparable BUD(s) at "
        f"complexity ~{complexity} — your estimate will be blended with "
        "their actual cycle times.\n"
    )


def build_phase_context(bud: BUDDocument) -> str:
    """Build context from BUD artifacts for the estimation LLM.

    Passes full PRD + tech spec content (capped at ``_MAX_SECTION_CHARS``)
    and an extracted summary from design wireframe HTML.
    """
    lines: list[str] = []

    req = bud.requirements_md or ""
    if req:
        lines.append("PRD content:")
        lines.append(req[:_MAX_SECTION_CHARS])
    else:
        lines.append("PRD: not yet generated")

    designs = bud.designs or []
    ready = [d for d in designs if getattr(d, "status", "") == "ready"]
    if ready:
        lines.append(f"Designs: {len(ready)} wireframes ready")
        for d in ready:
            summary = _summarize_design_html(getattr(d, "design_html", "") or "")
            if summary:
                lines.append(summary)
    elif designs:
        lines.append(f"Designs: {len(designs)} in progress")

    spec = bud.tech_spec_md or ""
    if spec:
        lines.append("Tech spec content:")
        lines.append(spec[:_MAX_SECTION_CHARS])
    else:
        lines.append("Tech spec: not yet generated")

    auto = bud.qa_automation_cases or []
    manual = bud.qa_manual_cases or []
    if auto or manual:
        lines.append(f"QA: {len(auto)} automation + {len(manual)} manual test cases")

    return "\n".join(lines) + "\n"


def _summarize_design_html(html: str) -> str:
    """Extract estimation-relevant signals from wireframe HTML."""
    if not html:
        return ""
    annotations = re.findall(r"<!--\s*([A-Z][\w-]*:.+?)-->", html)
    buttons = len(re.findall(r"<(?:button|v-btn)[^>]*>", html, re.I))
    inputs = len(re.findall(r"<(?:input|v-text-field|select|textarea)[^>]*>", html, re.I))
    parts: list[str] = []
    if annotations:
        parts.append(f"  Wireframe annotations: {len(annotations)}")
        for a in annotations[:_MAX_ANNOTATIONS_INLINED]:
            parts.append(f"    - {a.strip()}")
    if buttons:
        parts.append(f"  Interactive elements: {buttons} buttons")
    if inputs:
        parts.append(f"  Form inputs: {inputs}")
    return "\n".join(parts)
