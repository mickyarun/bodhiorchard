# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""HTML sanitization for AI-generated design wireframes.

Design HTML is stored in the database and rendered in blob-URL iframes
on the frontend. Blob-URL iframes are **origin-isolated** — they cannot
access the parent page's DOM, cookies, localStorage, or session.

Because Vuetify CDN wireframes use:
- Custom Vue component tags (``v-app``, ``v-card``, ``v-btn``, etc.)
- ``<script>`` tags for Vue 3 + Vuetify CDN loading
- Full HTML document structure (``<!DOCTYPE>``, ``<html>``, ``<head>``)

... a tag-allowlist sanitizer like nh3 is unsuitable (it strips custom
tags, structural tags, and scripts).  Instead, we use a lightweight
regex-based approach that strips only the truly dangerous patterns:
inline event handlers (``onclick``, ``onerror``, etc.) and
``javascript:`` URLs.
"""

import re

import structlog

logger = structlog.get_logger(__name__)

# Inline event handler attributes (onclick, onerror, onload, etc.)
_EVENT_HANDLER_RE = re.compile(
    r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)""",
    re.IGNORECASE,
)

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

    body_close = html.lower().rfind("</body>")
    if body_close == -1:
        return html

    # The `#app` div's matching `</div>` is the last one before `</body>`.
    div_close = html.lower().rfind("</div>", open_match.end(), body_close)
    if div_close == -1:
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

    Strips inline event handlers and ``javascript:`` URLs while preserving
    the full HTML document structure, custom Vue component tags, CDN scripts,
    and inline styles needed for Vuetify wireframes.

    This is intentionally lighter than nh3 because the HTML is always
    rendered in an origin-isolated blob-URL iframe.

    Args:
        html: Raw HTML string from AI generation or user input.

    Returns:
        Sanitized HTML string safe for iframe rendering.
    """
    result = html

    # Remove inline event handlers (onclick, onerror, onload, etc.)
    result = _EVENT_HANDLER_RE.sub("", result)

    # Neutralize javascript:/vbscript: URLs → replace entire value
    result = _JS_URL_RE.sub(r"\1\2about:blank\2", result)

    # Remove <object>, <embed>, <applet> tags (plugin-based execution)
    result = _DANGEROUS_TAGS_RE.sub("", result)
    result = _DANGEROUS_TAGS_VOID_RE.sub("", result)

    # Defensively wrap content in <v-app> when AI dropped the wrapper —
    # otherwise Vuetify's layout injection fails and the iframe is blank.
    result = _ensure_v_app_wrapper(result)

    return result
