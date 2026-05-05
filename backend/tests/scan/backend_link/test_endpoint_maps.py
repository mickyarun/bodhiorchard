# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for ``backend_link.endpoint_maps``.

Covers the function-bodied + arrow-bodied endpoint extractor that
turns ``GET_DETAILS(id) { return `business/${id}/users`; }`` into the
``GET_DETAILS → /business/:param/users`` constants entry.
"""

from __future__ import annotations

from app.services.scan.backend_link.endpoint_maps import iter_endpoint_paths


def test_method_body_with_template() -> None:
    """``KEY(args) { return `path/${var}` }`` extracts a normalised route."""
    text = """
const _employeeEndpoints = {
  GET_DETAILS(businessId: string, userId: string) {
    return `business/${businessId}/users/user/${userId}`;
  },
};
"""
    pairs = dict(iter_endpoint_paths(text))
    assert pairs["GET_DETAILS"] == "/business/:param/users/user/:param"


def test_method_body_with_nested_braces() -> None:
    """``if`` / ``else`` blocks inside the body don't break the scan.

    Prior bug: the regex's ``[^{}]*?`` body matcher rejected any body
    containing a nested ``{`` and silently dropped the endpoint.
    """
    text = """
const _x = {
  GET_OFFERS(id: string, storeId?: string) {
    if (storeId) {
      return `merchants/${id}/offer?storeId=${storeId}`;
    }
    return `merchants/${id}/offer`;
  },
};
"""
    pairs = dict(iter_endpoint_paths(text))
    assert pairs["GET_OFFERS"] == "/merchants/:param/offer"


def test_arrow_body_extracted() -> None:
    """``KEY: (args) => `path``` form is handled."""
    text = "const _x = { LOG_OUT: (id: string) => `merchant/employee/${id}/logout-web` };"
    pairs = dict(iter_endpoint_paths(text))
    assert pairs["LOG_OUT"] == "/merchant/employee/:param/logout-web"


def test_javascript_pseudo_protocol_rejected() -> None:
    """A method that returns ``"javascript:void(0)"`` does not produce a route."""
    text = """
const _x = {
  noop() {
    return "javascript:void(0)";
  },
};
"""
    pairs = dict(iter_endpoint_paths(text))
    assert "noop" not in pairs


def test_external_url_rejected() -> None:
    """``"https://..."`` is not a route."""
    text = 'const _x = { EXT: () => "https://example.com/api" };'
    pairs = dict(iter_endpoint_paths(text))
    assert "EXT" not in pairs


def test_string_without_slash_rejected() -> None:
    """A method that returns a non-path string is not promoted to a route."""
    text = "const _x = { msg: () => `something went wrong` };"
    pairs = dict(iter_endpoint_paths(text))
    assert "msg" not in pairs
