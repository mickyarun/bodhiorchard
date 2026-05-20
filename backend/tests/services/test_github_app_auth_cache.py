# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Unit tests for the installation-token cache control surface.

``invalidate_installation_token`` is the escape hatch used by the
BUD-agent retry path when the cached token itself is the rejected one —
without it, ``get_installation_token`` would keep handing back the dead
token until natural TTL expiry.
"""

from app.services import github_app_auth


def test_invalidate_removes_cached_entry() -> None:
    github_app_auth._token_cache["org-A"] = ("ghs_old", 9_999_999_999.0)
    github_app_auth.invalidate_installation_token("org-A")
    assert "org-A" not in github_app_auth._token_cache


def test_invalidate_unknown_org_is_noop() -> None:
    github_app_auth._token_cache.pop("org-missing", None)
    # Must not raise — the BUD-agent retry calls this unconditionally.
    github_app_auth.invalidate_installation_token("org-missing")


def test_invalidate_only_targets_named_org() -> None:
    github_app_auth._token_cache["org-keep"] = ("ghs_keep", 9_999_999_999.0)
    github_app_auth._token_cache["org-drop"] = ("ghs_drop", 9_999_999_999.0)
    github_app_auth.invalidate_installation_token("org-drop")
    assert "org-keep" in github_app_auth._token_cache
    assert "org-drop" not in github_app_auth._token_cache
    github_app_auth._token_cache.pop("org-keep", None)
