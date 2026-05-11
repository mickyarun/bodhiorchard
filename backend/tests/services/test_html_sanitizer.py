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

"""Tests for design HTML sanitization."""

from app.services.html_sanitizer import sanitize_design_html


def test_preserves_inline_event_handlers() -> None:
    # Plain-HTML wireframes wire tab switching and button states through
    # inline handlers; stripping them breaks interactivity. <script> is
    # already trusted in the same iframe — onclick is strictly weaker,
    # so stripping it would be inconsistent. See module docstring.
    html = '<div class="wf-tab" onclick="showTab(\'mobile\')">Mobile</div>'
    assert "onclick=\"showTab('mobile')\"" in sanitize_design_html(html)


def test_neutralizes_javascript_urls() -> None:
    html = '<a href="javascript:alert(1)">x</a>'
    out = sanitize_design_html(html)
    assert "javascript:" not in out
    assert "about:blank" in out


def test_strips_object_tag_with_content() -> None:
    html = '<div>before<object data="evil.swf">payload</object>after</div>'
    out = sanitize_design_html(html)
    assert "<object" not in out
    assert "payload" not in out
    assert "before" in out and "after" in out


def test_strips_void_embed_tag() -> None:
    html = '<div>before<embed src="evil.swf"/>after</div>'
    out = sanitize_design_html(html)
    assert "<embed" not in out
    assert "before" in out and "after" in out


def test_preserves_scripts_and_styles() -> None:
    # Plain-HTML wireframes carry inline <script> for demo interactivity
    # and <style> for design-system tokens; both must survive.
    html = (
        "<html><head><style>.x{color:red}</style></head>"
        "<body><script>console.log('demo')</script></body></html>"
    )
    out = sanitize_design_html(html)
    assert "<style>.x{color:red}</style>" in out
    assert "<script>console.log('demo')</script>" in out
