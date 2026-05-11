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

The designer prompt now generates **plain HTML + CSS** wireframes (see
``chat_prompts.py``), so a tag-allowlist sanitizer like nh3 is still
unsuitable — we keep ``<style>``, ``<script>``, structural tags, and
inline event handlers. We strip only patterns with no legitimate place
in a wireframe: ``javascript:`` / ``vbscript:`` URLs and
plugin-execution tags (``<object>``, ``<embed>``, ``<applet>``).

Inline event handlers (``onclick``, ``onchange``, …) are intentionally
**preserved** — the wireframes route interactivity through them, and
``<script>`` is already trusted, which is strictly more powerful than
an inline handler.

If the threat model ever changes (rendering wireframes authored by
external collaborators outside the org), add
``sandbox="allow-scripts"`` to the iframe on the frontend and tighten
this module to an allowlist.
"""

import re

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


def sanitize_design_html(html: str) -> str:
    """Sanitize AI-generated design HTML for iframe rendering.

    Strips ``javascript:`` URLs and plugin-execution tags while preserving
    full HTML document structure, ``<script>``/``<style>``, inline styles,
    and inline event handlers needed for plain-HTML wireframes.

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

    return result
