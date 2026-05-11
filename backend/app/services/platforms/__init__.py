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
