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

"""HTML sanitization for AI-generated design wireframes.

Design HTML is stored in the database and rendered on the frontend via
an ``iframe srcdoc`` (see ``BUDDesignPanel.vue``). ``srcdoc`` iframes
inherit the parent document's origin, so the wireframe runs in the
**same origin** as the host app — it can read cookies, ``localStorage``,
and the parent DOM.

We accept this trust posture because the AI generating the HTML is
gated by the same org-level auth as the surrounding app: the threat
model is **prompt drift / accidental misuse**, not adversarial input.
A hostile prompt operator could already mint a BUD, write a malicious
agent run, and exfiltrate org data via legitimate API calls; an
iframe-side exfiltration is no worse than what the existing API
surface allows.

Because Vuetify CDN wireframes use:
- Custom Vue component tags (``v-app``, ``v-card``, ``v-btn``, etc.)
- ``<script>`` tags for Vue 3 + Vuetify CDN loading
- Full HTML document structure (``<!DOCTYPE>``, ``<html>``, ``<head>``)

... a tag-allowlist sanitizer like nh3 is unsuitable (it strips custom
tags, structural tags, and scripts). Instead, we strip only the patterns
with no legitimate place in a wireframe: ``javascript:`` / ``vbscript:``
URLs and plugin-execution tags (``<object>``, ``<embed>``, ``<applet>``).

Inline event handlers (``onclick``, ``onchange``, …) are intentionally
**preserved** — the wireframes route interactivity through them (tab
switching, button states), and ``<script>`` is already trusted, which
is strictly more powerful than an inline handler.

If the threat model ever changes (rendering wireframes authored by
external collaborators outside the org), the frontend should add
``sandbox="allow-scripts"`` to the iframe AND pre-compile Vue templates
server-side (Vue's runtime template compiler is blocked under sandbox
in some Chromium versions). This module would then tighten to an
allowlist.
"""

import re

import structlog

logger = structlog.get_logger(__name__)

# javascript: / vbscript: URLs in href/src/action attributes
_JS_URL_RE = re.compile(
    r"""((?:href|src|action)\s*=\s*)(["'])(?:\s*(?:javascript|vbscript)\s*:[^"']*)\2""",
    re.IGNORECASE,
)

# <object>, <embed>, <applet> tags and their content
_DANGEROUS_TAGS_RE = re.compile(
    r"<(?:object|embed|applet)\b[^>]*>.*?</(?:object|embed|applet)>",
    re.IGNORECASE | re.DOTALL,
)

# Standalone <object>, <embed>, <applet> (self-closing or unclosed)
_DANGEROUS_TAGS_VOID_RE = re.compile(
    r"<(?:object|embed|applet)\b[^>]*/?>",
    re.IGNORECASE,
)

# `<v-app` already present — wrapper exists, no fix needed
_HAS_V_APP_RE = re.compile(r"<v-app[\s>]", re.IGNORECASE)

# Any Vuetify component tag — signal that this is a Vuetify wireframe
_HAS_VUETIFY_TAG_RE = re.compile(r"<v-[a-z]", re.IGNORECASE)

# Mount point div: <div id="app"> (single or double quotes, optional attrs)
_APP_MOUNT_OPEN_RE = re.compile(
    r"""<div\s+[^>]*id\s*=\s*["']app["'][^>]*>""",
    re.IGNORECASE,
)

# Walking regexes for balancing nested <div> tags. The `\b` keeps us from
# matching <divider> or similar; the close pattern tolerates whitespace
# before `>` (e.g. `</div >`).
_DIV_OPEN_RE = re.compile(r"<div\b", re.IGNORECASE)
_DIV_CLOSE_RE = re.compile(r"</div\s*>", re.IGNORECASE)


def _find_matching_div_close(html: str, after_open: int) -> int:
    """Return the index of the ``</div>`` that closes a ``<div>`` whose
    opening tag ended at ``after_open``. ``-1`` if the input is unbalanced.

    Walks forward counting nested ``<div>`` opens vs closes — replaces the
    earlier "last ``</div>`` before ``</body>``" heuristic, which corrupted
    output for any wireframe with sibling ``<div>`` elements after ``#app``.

    Known limitation: does not special-case HTML comments, ``<script>``,
    or ``<style>`` blocks. A literal ``<div`` inside a Vue template string
    (``template: '<div>...</div>'``) skews the counter. Building that in
    would mean a real HTML mini-parser. When the count goes wrong, this
    returns ``-1`` and the caller leaves the HTML untouched, so the failure
    mode is benign (no wrap added) rather than corrupt output.
    """
    depth = 1
    pos = after_open
    while True:
        close_m = _DIV_CLOSE_RE.search(html, pos)
        if close_m is None:
            return -1
        open_m = _DIV_OPEN_RE.search(html, pos, close_m.start())
        if open_m is not None:
            depth += 1
            pos = open_m.end()
        else:
            depth -= 1
            if depth == 0:
                return close_m.start()
            pos = close_m.end()


def _ensure_v_app_wrapper(html: str) -> str:
    """Wrap mount-point contents in ``<v-app>`` if a Vuetify wireframe lacks it.

    Vuetify 3's ``<v-main>`` (and other layout-aware components) call
    ``useLayout()`` at setup, which reads a context injected only by
    ``<v-app>`` / ``<v-layout>``. AI-generated wireframes occasionally drop
    the wrapper, producing ``[Vuetify] Could not find injected layout`` and
    an empty ``<body>`` at iframe render time.

    We auto-wrap when the HTML clearly *is* a Vuetify wireframe (any
    ``<v-*>`` tag) but has no ``<v-app>``. Logged as a warning so prompt
    drift surfaces in observability rather than silently masking.
    """
    if _HAS_V_APP_RE.search(html) or not _HAS_VUETIFY_TAG_RE.search(html):
        return html

    open_match = _APP_MOUNT_OPEN_RE.search(html)
    if not open_match:
        return html

    div_close = _find_matching_div_close(html, open_match.end())
    if div_close == -1:
        logger.warning(
            "design_html_wrapper_skipped",
            reason="unbalanced_div_count_from_mount_point",
        )
        return html

    logger.warning(
        "design_html_autowrapped_v_app",
        reason="vuetify_wireframe_missing_v_app_wrapper",
    )
    return (
        html[: open_match.end()]
        + "<v-app>"
        + html[open_match.end() : div_close]
        + "</v-app>"
        + html[div_close:]
    )


def sanitize_design_html(html: str) -> str:
    """Sanitize AI-generated design HTML for iframe rendering.

    Strips ``javascript:`` URLs and plugin-execution tags while preserving
    full HTML document structure, custom Vue component tags, CDN scripts,
    inline styles, and inline event handlers needed for Vuetify wireframes.

    This is intentionally lighter than nh3 because the threat model is
    prompt drift, not adversarial input — see module docstring for the
    trust-posture argument.

    Args:
        html: Raw HTML string from AI generation or user input.

    Returns:
        Sanitized HTML string safe for iframe rendering.
    """
    result = html

    # Neutralize javascript:/vbscript: URLs → replace entire value
    result = _JS_URL_RE.sub(r"\1\2about:blank\2", result)

    # Remove <object>, <embed>, <applet> tags (plugin-based execution)
    result = _DANGEROUS_TAGS_RE.sub("", result)
    result = _DANGEROUS_TAGS_VOID_RE.sub("", result)

    # Defensively wrap content in <v-app> when AI dropped the wrapper —
    # otherwise Vuetify's layout injection fails and the iframe is blank.
    result = _ensure_v_app_wrapper(result)

    return result
