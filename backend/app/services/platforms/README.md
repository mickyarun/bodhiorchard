# Platforms Registry

Classifies a repository by its frontend / UI toolchain (Flutter, React, Android,
Tauri, …) so downstream services — design-system extraction, skill analysis,
MCP context — can adapt to the idioms of that toolchain.

## Adding a new platform — 5 steps

1. **Create** `backend/app/services/platforms/<slug>.py`.

   ```python
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

   """<Slug> platform detection."""

   from pathlib import Path

   from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
   from app.services.platforms.registry import register


   @register
   class MyPlatform:
       slug = "my_slug"
       kind = PlatformKind.DESKTOP
       priority = 60

       def detect(self, repo: Path) -> bool:
           return (repo / "marker.file").exists()

       @property
       def design_globs(self) -> tuple[str, ...]:
           return DEFAULT_COMMON_GLOBS + (
               "src/theme/**/*.ts",
           )

       @property
       def skip_dirs(self) -> tuple[str, ...]:
           return ("build", ".cache")

       @property
       def prompt_hint(self) -> str:
           return "Target: My Platform. Extract ... tokens."
   ```

2. **Register the module import** in `__init__.py` (alphabetical, one line).

3. **Add a fixture** under `backend/tests/services/platforms/fixtures/<slug>/`
   with the minimum marker files needed to trigger detection.

4. **Add a test** `backend/tests/services/platforms/test_<slug>.py` asserting
   `detect_platform(fixture_dir).slug == "<slug>"`.

5. **Run** `ruff check .`, `mypy app/`, and `pytest tests/services/platforms/`.

That is the entire diff. No edits to `scan_pipeline.py`,
`design_system_extractor.py`, `registry.py`, or `base.py`.

## Priority ordering

Detection iterates platforms from highest `priority` to lowest. Current
assignments (keep this table in sync with the `priority` constants in each
platform module):

| Priority | Platforms |
|---|---|
| 85 | SwiftUI macOS (must outrank `ios_native`'s xcodeproj grab) |
| 80 | Flutter, Android native, iOS native |
| 70 | React Native, Expo, Ionic |
| 65 | Capacitor, Tauri |
| 60 | Electron, Blazor, .NET MAUI, WPF, Avalonia |
| 55 | Qt, Compose Desktop |
| 50 | Shopify Liquid, Jekyll, Hugo, Eleventy |
| 40 | Design tokens (tokens.json, Style Dictionary, Theo) |
| 30 | Generic web JS (Vue, React, Svelte, Astro, …) |
| 0  | `backend_fallback` (matches everything) |

Ties in priority are broken by `slug` (secondary sort key in
`registry.all_platforms()`), so order is deterministic regardless of import
sequence. Keep the `__init__.py` imports alphabetical anyway — it makes the
file easier to scan.

## Contract

Each platform supplies:

- `slug` — stable string used in job payloads and logs.
- `kind` — coarse category used for gating (see `PlatformKind`).
- `priority` — detection order.
- `detect(repo)` — boolean, must be cheap (< 50 ms) and robust to malformed files.
- `design_globs` — repo-relative glob patterns pointing at design-token sources.
- `skip_dirs` — directory names the discovery walker should skip, *on top of*
  the universal `DEFAULT_SKIP_DIRS` in `base.py`.
- `prompt_hint` — one sentence fragment that gets prepended to the LLM
  extraction prompt. Should name the platform's token idioms (e.g. "ThemeData"
  for Flutter, "XAML ResourceDictionary" for WPF).

## What this package must NOT import

- `app.models`, `app.api`, `app.agents`
- SQLAlchemy, FastAPI, any DB session
- The `design_system_extractor` module itself (no cycles)

Only `pathlib`, stdlib, and `structlog` for logging.
