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

"""Tests for design HTML sanitization, including the v-app auto-wrap fallback."""

from app.services.html_sanitizer import sanitize_design_html


def test_preserves_inline_event_handlers() -> None:
    # Wireframes wire tab switching and button states through inline
    # handlers; stripping them breaks interactivity. <script> is already
    # trusted in the same iframe — onclick is strictly weaker, so the
    # asymmetry was inconsistent. See module docstring for trust posture.
    html = '<div class="wf-tab" onclick="showTab(\'mobile\')">Mobile</div>'
    assert 'onclick="showTab(\'mobile\')"' in sanitize_design_html(html)


def test_neutralizes_javascript_urls() -> None:
    html = '<a href="javascript:alert(1)">x</a>'
    out = sanitize_design_html(html)
    assert "javascript:" not in out
    assert "about:blank" in out


def test_preserves_html_when_v_app_present() -> None:
    html = (
        '<html><body><div id="app"><v-app><v-main>hi</v-main></v-app></div>'
        "</body></html>"
    )
    assert sanitize_design_html(html) == html


def test_skips_wrap_when_no_vuetify_tags() -> None:
    html = '<html><body><div id="app"><h1>Plain</h1></div></body></html>'
    assert sanitize_design_html(html) == html


def test_wraps_vuetify_content_missing_v_app() -> None:
    html = (
        '<html><body><div id="app">'
        "<v-main><v-card>Hi</v-card></v-main>"
        "</div></body></html>"
    )
    out = sanitize_design_html(html)
    assert "<v-app>" in out
    assert "</v-app>" in out
    assert out.index("<v-app>") < out.index("<v-main>")
    assert out.index("</v-main>") < out.index("</v-app>")


def test_wrap_handles_scripts_after_mount_div() -> None:
    html = (
        '<html><body><div id="app">'
        "<v-main>Hi</v-main>"
        "</div>"
        '<script src="vue.js"></script>'
        "</body></html>"
    )
    out = sanitize_design_html(html)
    assert "<v-app>" in out
    # The </v-app> must close before </div>, not swallow the <script>.
    assert out.index("</v-app>") < out.index("<script")


def test_wrap_with_attrs_on_app_div() -> None:
    html = (
        '<html><body><div class="root" id="app" data-x="1">'
        "<v-card>Hi</v-card>"
        "</div></body></html>"
    )
    out = sanitize_design_html(html)
    assert "<v-app>" in out and "</v-app>" in out


def test_wrap_handles_nested_divs_inside_mount() -> None:
    # Multiple nested <div> inside #app: the </v-app> close must land at
    # the matching </div> for #app, not at the first/innermost </div>.
    html = (
        '<html><body><div id="app">'
        '<div class="layout"><div class="sidebar"><v-card>Hi</v-card></div></div>'
        "</div></body></html>"
    )
    out = sanitize_design_html(html)
    assert "<v-app>" in out and "</v-app>" in out
    # </v-app> must close AFTER all nested </div>s for sidebar+layout,
    # but BEFORE the </div> that closes #app itself.
    assert out.count("</div>") == 3
    v_app_close = out.index("</v-app>")
    # Two </div> precede </v-app> (sidebar + layout); the third closes #app.
    assert out.count("</div>", 0, v_app_close) == 2


def test_wrap_handles_siblings_after_mount_div() -> None:
    # The old heuristic ("last </div> before </body>") would have put
    # </v-app> after the sibling footer div, swallowing it into v-app.
    html = (
        '<html><body><div id="app"><v-main>Hi</v-main></div>'
        '<div class="footer">unrelated</div>'
        "</body></html>"
    )
    out = sanitize_design_html(html)
    assert "<v-app>" in out and "</v-app>" in out
    # The sibling footer div must remain outside the v-app wrapper.
    assert out.index("</v-app>") < out.index('<div class="footer"')
