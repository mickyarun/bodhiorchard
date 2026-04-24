# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Platform registry — detects the frontend/UI toolchain of a repository.

Public API:

    >>> from pathlib import Path
    >>> from app.services.platforms import detect_platform
    >>> platform = detect_platform(Path("/path/to/repo"))
    >>> platform.slug
    'flutter'

See ``README.md`` in this package for the recipe to add a new platform.
"""

from app.services.platforms import android_native as _android_native  # noqa: F401
from app.services.platforms import avalonia as _avalonia  # noqa: F401
from app.services.platforms import backend_fallback as _backend_fallback  # noqa: F401
from app.services.platforms import blazor as _blazor  # noqa: F401
from app.services.platforms import capacitor as _capacitor  # noqa: F401
from app.services.platforms import compose_desktop as _compose_desktop  # noqa: F401
from app.services.platforms import design_tokens as _design_tokens  # noqa: F401
from app.services.platforms import dotnet_maui as _dotnet_maui  # noqa: F401
from app.services.platforms import electron as _electron  # noqa: F401
from app.services.platforms import eleventy as _eleventy  # noqa: F401
from app.services.platforms import expo as _expo  # noqa: F401
from app.services.platforms import flutter as _flutter  # noqa: F401
from app.services.platforms import hugo as _hugo  # noqa: F401
from app.services.platforms import ionic as _ionic  # noqa: F401
from app.services.platforms import ios_native as _ios_native  # noqa: F401
from app.services.platforms import jekyll as _jekyll  # noqa: F401
from app.services.platforms import qt as _qt  # noqa: F401
from app.services.platforms import react_native as _react_native  # noqa: F401
from app.services.platforms import shopify_liquid as _shopify_liquid  # noqa: F401
from app.services.platforms import swiftui_macos as _swiftui_macos  # noqa: F401
from app.services.platforms import tauri as _tauri  # noqa: F401
from app.services.platforms import web_js as _web_js  # noqa: F401
from app.services.platforms import wpf as _wpf  # noqa: F401
from app.services.platforms.base import (
    DEFAULT_COMMON_GLOBS,
    DEFAULT_SKIP_DIRS,
    UI_KINDS,
    Platform,
    PlatformKind,
)
from app.services.platforms.registry import (
    all_platforms,
    detect_platform,
    get_platform,
    register,
)

__all__ = [
    "DEFAULT_COMMON_GLOBS",
    "DEFAULT_SKIP_DIRS",
    "Platform",
    "PlatformKind",
    "UI_KINDS",
    "all_platforms",
    "detect_platform",
    "get_platform",
    "register",
]
