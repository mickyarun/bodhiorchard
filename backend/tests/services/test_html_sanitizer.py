"""Tests for design HTML sanitization, including the v-app auto-wrap fallback."""

from app.services.html_sanitizer import sanitize_design_html


def test_strips_inline_event_handlers() -> None:
    html = '<button onclick="alert(1)" class="x">Hi</button>'
    assert "onclick" not in sanitize_design_html(html)


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
