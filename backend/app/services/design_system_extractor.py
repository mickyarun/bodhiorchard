# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Design system extractor — uses LLM to analyze frontend source files.

Discovers design-related files in a repository (theme configs, styles,
package.json), sends them to the configured LLM (via Claude Code CLI),
and gets back structured markdown with design tokens, CDN boilerplate,
and a pattern library.

Falls back to basic regex extraction if the CLI is unavailable. File
discovery globs and the LLM prompt idiom are supplied by the detected
:class:`app.services.platforms.Platform`, so mobile (Flutter / Android /
iOS), desktop, static-site and token-only repos work in the same pipeline
as web apps.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.services.platforms import DEFAULT_SKIP_DIRS, Platform, PlatformKind

logger = structlog.get_logger(__name__)


@dataclass
class ExtractionResult:
    """Result of a design system extraction."""

    content: str
    source_hash: str
    method: str  # "llm", "regex_fallback", "minimal"
    error: str | None = None  # Non-fatal error (e.g. LLM timeout)


# Max file size to include in the prompt (50KB)
_MAX_FILE_SIZE = 50_000

# Max total content to send to LLM (200KB)
_MAX_TOTAL_CONTENT = 200_000


async def extract_design_system(repo_path: Path, platform: Platform) -> ExtractionResult:
    """Extract design system from a repository using the LLM.

    Discovers design-related files (via the platform's ``design_globs``),
    sends them to Claude Code CLI for intelligent extraction, and returns
    structured markdown.

    Falls back to regex-based extraction if the CLI is unavailable or times out.

    Args:
        repo_path: Path to the repository root.
        platform: The detected platform supplying globs, skip dirs, and
            prompt idiom.

    Returns:
        ExtractionResult with content, hash, method used, and any non-fatal error.
    """
    # 1. Discover design-related files
    discovered = discover_design_files(repo_path, platform)
    if not discovered:
        logger.warning(
            "no_design_files_found",
            repo_path=str(repo_path),
            platform=platform.slug,
        )
        content, source_hash = _fallback_minimal(repo_path, platform)
        return ExtractionResult(
            content=content,
            source_hash=source_hash,
            method="minimal",
        )

    # 2. Read file contents
    file_contents = read_discovered_files(discovered)
    source_hash = compute_hash(file_contents)

    # 3. Try LLM-powered extraction
    from app.services.claude_runner import is_claude_cli_available

    llm_error: str | None = None
    if is_claude_cli_available():
        try:
            markdown, llm_err = await _llm_extract(repo_path, file_contents, platform)
            if markdown:
                logger.info(
                    "design_system_extracted_via_llm",
                    repo_path=str(repo_path),
                    platform=platform.slug,
                    file_count=len(file_contents),
                    hash=source_hash[:12],
                )
                return ExtractionResult(
                    content=markdown,
                    source_hash=source_hash,
                    method="llm",
                )
            llm_error = llm_err
        except Exception as exc:
            llm_error = str(exc)[:200]
            logger.exception(
                "llm_extraction_failed",
                repo_path=str(repo_path),
                platform=platform.slug,
            )
    else:
        llm_error = "Claude Code CLI not available"

    # 4. Fallback.
    # The regex extractor only understands web/Vuetify idioms, so for
    # non-web platforms (Flutter, Android, iOS, ...) running it would
    # produce Vuetify CDN HTML that is actively misleading. Emit a
    # platform-aware placeholder instead.
    logger.info(
        "design_system_fallback",
        repo_path=str(repo_path),
        platform=platform.slug,
        reason=llm_error,
    )
    if platform.kind == PlatformKind.WEB:
        markdown = _regex_extract(repo_path, file_contents)
        method = "regex_fallback"
    else:
        markdown = _platform_aware_fallback(platform, file_contents, llm_error)
        method = "minimal"
    return ExtractionResult(
        content=markdown,
        source_hash=source_hash,
        method=method,
        error=llm_error or "LLM extraction returned empty result — used fallback",
    )


def discover_design_files(repo_path: Path, platform: Platform) -> list[Path]:
    """Find design-related files in the repository using platform-aware globs.

    Args:
        repo_path: Repository root path.
        platform: Detected platform whose ``design_globs`` and ``skip_dirs``
            drive the search.

    Returns:
        Sorted list of discovered file paths.
    """
    skip = DEFAULT_SKIP_DIRS | frozenset(platform.skip_dirs)
    found: set[Path] = set()
    for pattern in platform.design_globs:
        for path in repo_path.glob(pattern):
            if path.is_file() and not _in_skip_dir(path, repo_path, skip):
                found.add(path)

    # Sort by path for deterministic ordering
    return sorted(found)


def _in_skip_dir(path: Path, root: Path, skip: frozenset[str]) -> bool:
    """Check if a path is inside a directory in the skip set."""
    try:
        relative = path.relative_to(root)
        return any(part in skip for part in relative.parts)
    except ValueError:
        return False


def read_discovered_files(
    files: list[Path],
) -> dict[str, str]:
    """Read discovered files, respecting size limits.

    Args:
        files: List of file paths to read.

    Returns:
        Dict mapping relative path strings to file contents.
    """
    result: dict[str, str] = {}
    total_size = 0

    for path in files:
        try:
            size = path.stat().st_size
            if size > _MAX_FILE_SIZE:
                continue
            if total_size + size > _MAX_TOTAL_CONTENT:
                break
            content = path.read_text(encoding="utf-8", errors="replace")
            # Use the filename or short relative path as key
            key = path.name
            if key in result:
                # Disambiguate with parent directory
                key = f"{path.parent.name}/{path.name}"
            result[key] = content
            total_size += size
        except (OSError, UnicodeDecodeError):
            continue

    return result


def compute_hash(file_contents: dict[str, str]) -> str:
    """Compute SHA256 hash of all discovered file contents."""
    combined = "".join(f"{k}:{v}" for k, v in sorted(file_contents.items()))
    return hashlib.sha256(combined.encode()).hexdigest()


def _extraction_instructions(platform: Platform) -> str:
    """Build the LLM instructions block — platform-aware.

    Web platforms get the full 6-section layout (Color Palette, Typography,
    Component Defaults, CSS Variables, CDN Boilerplate, Pattern Library) —
    downstream wireframe generators depend on the CDN boilerplate.

    Non-web platforms get a focused 3-section layout (Color Palette,
    Typography, Platform Tokens). Asking a Flutter / Android / iOS repo
    to produce CDN HTML or Vuetify component defaults is what pushed the
    LLM past the 10-minute timeout.
    """
    if platform.kind == PlatformKind.WEB:
        return (
            "## Instructions\n\n"
            "Produce a design system reference document in markdown with "
            "these sections:\n\n"
            "1. **Color Palette**: ALL theme colors as a markdown table "
            "(`| Token | Value |`). Include dark/light themes.\n"
            "2. **Typography**: Font families, sizes, weights.\n"
            "3. **Component Defaults**: Configured component defaults "
            "(Vuetify defaults, MUI overrides, etc.).\n"
            "4. **CSS Variables / Tokens**: Custom properties, SCSS "
            "variables, design tokens.\n"
            "5. **CDN Boilerplate**: Complete HTML boilerplate using the "
            "project's UI framework via CDN with the EXACT version from "
            "package.json. Include: CDN links, framework init with theme "
            "colors, icon library, font imports, runnable template.\n"
            "6. **Pattern Library**: Common component patterns as concise "
            "examples.\n\n"
            "Output ONLY the markdown starting with "
            "`# Design System Reference`. No preamble."
        )
    return (
        "## Instructions\n\n"
        "Produce a focused design system reference in markdown with "
        "these three sections **only** (do NOT emit CDN HTML, Vuetify "
        "boilerplate, or CSS variable tables — this is a "
        f"{platform.kind.value} repository):\n\n"
        "1. **Color Palette**: All semantic colors as a markdown table "
        "(`| Token | Value | Notes |`). Include dark / light variants "
        "when the codebase defines them. Express colours in hex.\n"
        "2. **Typography**: Font families, sizes, weights, line heights "
        "— in the platform's idiom (Flutter `TextStyle`, Android "
        "`TextAppearance`, iOS `Font`, XAML `TextBlock` styles).\n"
        "3. **Platform Tokens**: Any other design-relevant constants "
        "(spacing scale, radii, elevations, motion durations). Use the "
        "platform's native value types.\n\n"
        "**Budget discipline (important):**\n"
        "- Cap tool calls at 4 file reads + 1 code_query call total. Do "
        "NOT walk every widget.\n"
        "- If the repo lacks a dedicated theme module, extract what you "
        "can from inline `Color(0x…)` / `TextStyle(…)` literals found "
        "in the inlined files and STOP. Imperfect-but-shipped beats "
        "exhaustive-and-timed-out.\n"
        "- Keep the output tight: 150-300 lines total.\n\n"
        "Output ONLY the markdown starting with "
        "`# Design System Reference`. No preamble."
    )


async def _llm_extract(
    repo_path: Path,
    file_contents: dict[str, str],
    platform: Platform,
) -> tuple[str | None, str | None]:
    """Use Claude Code CLI to intelligently extract the design system.

    Sends discovered file paths (and small file contents inline) to the
    LLM, which can read additional files from the repo via its tools
    (the bodhi ``code_*`` MCP tools when registered, else ``Read``).

    Args:
        repo_path: Repository root (used as working_dir for CLI).
        file_contents: Dict of filename → content for design-related files.
        platform: Detected platform whose ``prompt_hint`` is prepended so
            the LLM parses tokens in the idioms of that platform.

    Returns:
        Tuple of (markdown_content_or_none, error_message_or_none).
    """
    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    # Inline design files up to 10KB each. The previous 20KB cap meant a
    # real Flutter app could easily ship 80KB of prompt, which combined
    # with the 15-turn exploration budget timed out at 10 minutes on
    # large repos. Keep inlining lean and let the LLM navigate via the
    # Read tool for anything bigger.
    inline_parts = []
    path_only_files = []
    for filename, content in file_contents.items():
        if len(content) < 10_000:
            inline_parts.append(f"### {filename}\n```\n{content}\n```")
        else:
            path_only_files.append(f"- `{filename}` ({len(content)} bytes)")

    file_context = "\n\n".join(inline_parts) if inline_parts else "(none inlined)"
    paths_section = "\n".join(path_only_files) if path_only_files else ""

    prompt_parts = [
        "You are a design system analyzer. Extract the design system "
        "from this repository into structured markdown.\n",
    ]

    if platform.prompt_hint:
        prompt_parts.append(f"## Platform Context\n\n{platform.prompt_hint}\n")

    # Navigation hint: bodhi's own MCP exposes ``code_query`` /
    # ``code_context`` against the per-repo cached call graph. When
    # available these are 5-10× faster than reading individual files
    # by name; when not registered the CLI just ignores the suggestion.
    prompt_parts.append(
        "## Navigation\n\n"
        "If the bodhi `code_*` MCP tools are connected, **prefer them "
        "over filesystem scans**:\n"
        '- `code_query` with query="theme color typography" to '
        "locate design-related symbols by name.\n"
        "- `code_context` with a symbol name to get its definition "
        "+ callers without reading the whole file.\n"
        "Fall back to `Read` only for files the indexer doesn't surface.\n"
    )

    prompt_parts.append(f"## Key Files (inlined)\n\n{file_context}\n")

    if paths_section:
        prompt_parts.append(f"## Additional Files (read from disk if needed)\n\n{paths_section}\n")

    prompt_parts.append(_extraction_instructions(platform))

    prompt = "\n".join(prompt_parts)

    # 15 turns let Claude explore the whole repo; 8 was too tight for
    # Flutter repos without dedicated theme files (inline colours force
    # several Read calls). 12 is the sweet spot: room for 1-2 code_query
    # calls + 4-6 Read calls + 1-2 refinement passes, still bounded.
    result = await run_claude_code(
        prompt=prompt,
        working_dir=repo_path,
        config=ClaudeRunnerConfig(max_turns=12, timeout_seconds=600),
    )

    # Even on non-success (e.g. ``error_max_turns``) Claude often has
    # written a usable partial design-system doc to ``result.output``
    # before the cap hit. ``output_tokens=1824`` on a real atoa_pax run
    # was ~80% of a complete doc — throwing it away forced the fallback.
    # Only hard-fail if the output is truly empty / doesn't look like the
    # expected markdown shape.
    output = (result.output or "").strip()
    partial_ok = bool(output) and "Design System" in output

    if not result.success and not partial_ok:
        logger.warning(
            "llm_extract_failed",
            error=result.error,
            output_preview=output[:200],
        )
        return None, result.error or "LLM extraction failed"

    if not result.success and partial_ok:
        logger.info(
            "llm_extract_partial_salvaged",
            error=result.error,
            output_length=len(output),
        )

    # Claude may wrap in markdown fences — strip them
    if output.startswith("```markdown"):
        output = output[len("```markdown") :].strip()
    if output.startswith("```"):
        output = output[3:].strip()
    if output.endswith("```"):
        output = output[:-3].strip()

    # Validate it looks like markdown
    if not output or "Design System" not in output:
        logger.warning(
            "llm_extract_invalid_output",
            output_preview=output[:200],
        )
        return None, "LLM returned invalid output"

    return output, None


# ── Regex fallback ────────────────────────────────────────────────


def _regex_extract(
    repo_path: Path,
    file_contents: dict[str, str],
) -> str:
    """Fallback: extract design system using regex patterns.

    Used when the LLM is unavailable. Produces basic but functional output.

    Args:
        repo_path: Repository root path.
        file_contents: Dict of filename → content for design-related files.

    Returns:
        Markdown string with extracted design system.
    """
    sections: list[str] = ["# Design System Reference\n"]

    # Find and parse Vuetify/theme config
    theme_found = False
    for filename, content in file_contents.items():
        if "vuetify" in filename.lower() or "theme" in filename.lower():
            themes = _extract_vuetify_theme(content)
            defaults = _extract_component_defaults(content)
            if themes:
                sections.append(_format_theme_section(themes))
                theme_found = True
            if defaults:
                sections.append(_format_defaults_section(defaults))

    if not theme_found:
        sections.append(
            "## Color Palette\n\n"
            "> Theme config not found or unrecognized format. "
            "Try re-extracting with Claude Code CLI available.\n"
        )

    # Extract SCSS/CSS tokens
    for filename, content in file_contents.items():
        if filename.endswith((".scss", ".css")):
            tokens = _extract_scss_tokens(content)
            if tokens:
                sections.append(_format_scss_section(tokens))
                break

    # Extract versions from package.json
    vuetify_version = "3.5.0"
    vue_version = "3.4.0"
    for filename, content in file_contents.items():
        if filename == "package.json":
            vuetify_version = _extract_package_version(content, "vuetify") or vuetify_version
            vue_version = _extract_package_version(content, "vue") or vue_version
            break

    sections.append(_format_cdn_boilerplate(vuetify_version, vue_version))
    sections.append(_format_pattern_library())

    return "\n".join(sections)


def _fallback_minimal(repo_path: Path, platform: Platform) -> tuple[str, str]:
    """Produce a minimal design system when no design files were discovered.

    For web platforms the output is the Vuetify CDN boilerplate (preserves
    existing behaviour). For non-web platforms we emit a platform-aware
    placeholder — emitting Vuetify HTML for a Flutter / Android / iOS repo
    would be actively misleading.

    Args:
        repo_path: Repository root path.
        platform: The detected platform. Controls which idiom the
            placeholder is written in.

    Returns:
        Tuple of (markdown_content, source_hash).
    """
    if platform.kind == PlatformKind.WEB:
        return _fallback_minimal_web(repo_path)

    source_hash = hashlib.sha256(platform.slug.encode()).hexdigest()
    return _platform_aware_fallback(platform, file_contents={}, reason=None), source_hash


def _fallback_minimal_web(repo_path: Path) -> tuple[str, str]:
    """Web-specific minimal fallback — emits the Vuetify CDN boilerplate."""
    pkg_path = repo_path / "package.json"
    vuetify_version = "3.5.0"
    vue_version = "3.4.0"
    source = ""

    if pkg_path.exists():
        try:
            source = pkg_path.read_text(encoding="utf-8")
            vuetify_version = _extract_package_version(source, "vuetify") or vuetify_version
            vue_version = _extract_package_version(source, "vue") or vue_version
        except OSError:
            pass

    md = (
        "# Design System Reference\n\n"
        "## Color Palette\n\n"
        "> No design files found in this repository. "
        "The CDN boilerplate uses default framework settings.\n\n"
        + _format_cdn_boilerplate(vuetify_version, vue_version)
        + _format_pattern_library()
    )

    source_hash = hashlib.sha256(source.encode()).hexdigest()
    return md, source_hash


def _platform_aware_fallback(
    platform: Platform,
    file_contents: dict[str, str],
    reason: str | None,
) -> str:
    """Emit a platform-aware placeholder markdown when the LLM path can't run.

    The key goal is: **do not emit Vuetify CDN HTML for a non-web repo.**
    This document makes the degraded state obvious to the user and lists
    the discovered design files so they can re-run extraction later (once
    the Claude CLI is configured) with full context.
    """
    idiom = _PLATFORM_IDIOM_HINTS.get(platform.kind, "design tokens")
    lines: list[str] = [
        "# Design System Reference",
        "",
        f"> **Platform detected:** `{platform.slug}` ({platform.kind.value}).",
        "",
        "## Status",
        "",
        (
            "The automated extractor could not produce a structured design "
            f"system for this {platform.kind.value} repository. The full LLM "
            "extraction path is required to parse this platform's native "
            "theme sources."
        ),
        "",
    ]
    if reason:
        lines.extend(["**Reason:**", "", f"> {reason}", ""])
    lines.extend(
        [
            "## What the extractor was looking for",
            "",
            platform.prompt_hint or f"{idiom} for this platform.",
            "",
        ],
    )
    if file_contents:
        lines.extend(["## Discovered design files", ""])
        for filename in sorted(file_contents):
            size = len(file_contents[filename])
            lines.append(f"- `{filename}` ({size} bytes)")
        lines.append("")
    else:
        lines.extend(
            [
                "## Discovered design files",
                "",
                "_None._ The platform's globs did not match any files at this path.",
                "",
            ],
        )
    lines.extend(
        [
            "## Next steps",
            "",
            "1. Ensure the Claude Code CLI is available and authenticated "
            "for this organization (Settings → AI Config).",
            f"2. Re-run design extraction on this repository from the "
            f"Settings → Design Systems page. The LLM will use the "
            f"`{platform.slug}` idiom hint to extract the correct tokens.",
            "",
        ],
    )
    return "\n".join(lines)


# Kind → short idiom description used in fallback copy.
_PLATFORM_IDIOM_HINTS: dict[PlatformKind, str] = {
    PlatformKind.WEB: "CSS custom properties, Tailwind config, or MUI/Vuetify theme objects",
    PlatformKind.MOBILE_NATIVE: (
        "Flutter ThemeData, Android XML resources, or iOS Asset Catalog colors"
    ),
    PlatformKind.MOBILE_CROSS: (
        "React Native StyleSheet tokens, Ionic CSS variables, or Capacitor theme config"
    ),
    PlatformKind.DESKTOP: (
        "XAML ResourceDictionary, QML Theme singletons, or Swift/Kotlin theme modules"
    ),
    PlatformKind.STATIC_SITE: "SCSS variables or site-generator theme config",
    PlatformKind.TOKENS_ONLY: "W3C Design Tokens Format JSON",
    PlatformKind.BACKEND: "no design tokens expected",
}


# ── Regex helpers ─────────────────────────────────────────────────


def _extract_vuetify_theme(content: str) -> dict[str, dict[str, str]]:
    """Regex-parse theme config for color palettes."""
    themes: dict[str, dict[str, str]] = {}
    theme_pattern = re.compile(
        r"const\s+(\w+)\s*(?::\s*\w+)?\s*=\s*\{"
        r"([^}]*dark\s*:\s*(true|false)[^}]*"
        r"colors\s*:\s*\{([^}]+)\})",
        re.DOTALL,
    )
    for match in theme_pattern.finditer(content):
        name = match.group(1)
        colors_block = match.group(4)
        colors = {}
        for cm in re.finditer(
            r"['\"]?([\w-]+)['\"]?\s*:\s*['\"]([^'\"]+)['\"]",
            colors_block,
        ):
            colors[cm.group(1)] = cm.group(2)
        if colors:
            themes[name] = colors
    return themes


def _extract_component_defaults(
    content: str,
) -> dict[str, dict[str, str]]:
    """Extract component defaults from Vuetify config."""
    defaults: dict[str, dict[str, str]] = {}
    defaults_match = re.search(
        r"defaults\s*:\s*\{(.+?)\n\s*\}",
        content,
        re.DOTALL,
    )
    if not defaults_match:
        return defaults
    block = defaults_match.group(1)
    for comp_match in re.finditer(r"(\w+)\s*:\s*\{([^}]+)\}", block):
        comp_name = comp_match.group(1)
        props = {}
        for pm in re.finditer(
            r"(\w+)\s*:\s*(?:['\"]([^'\"]*)['\"]|(\w+))",
            comp_match.group(2),
        ):
            key = pm.group(1)
            val = pm.group(2) if pm.group(2) is not None else pm.group(3)
            props[key] = val
        if props:
            defaults[comp_name] = props
    return defaults


def _extract_scss_tokens(content: str) -> dict[str, str]:
    """Extract CSS/SCSS variables and tokens."""
    tokens: dict[str, str] = {}
    font_match = re.search(r"font-family\s*:\s*([^;]+);", content)
    if font_match:
        tokens["font-family"] = font_match.group(1).strip()
    for vm in re.finditer(r"\$(\w[\w-]*)\s*:\s*([^;]+);", content):
        tokens[f"${vm.group(1)}"] = vm.group(2).strip()
    for pm in re.finditer(r"--([\w-]+)\s*:\s*([^;]+);", content):
        tokens[f"--{pm.group(1)}"] = pm.group(2).strip()
    return tokens


def _extract_package_version(
    pkg_content: str,
    package_name: str,
) -> str | None:
    """Get a package version from package.json."""
    try:
        pkg = json.loads(pkg_content)
        deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        version = deps.get(package_name, "")
        return re.sub(r"^[\^~>=]+", "", version) or None
    except (json.JSONDecodeError, KeyError):
        return None


# ── Formatting helpers ────────────────────────────────────────────


def _format_theme_section(themes: dict[str, dict[str, str]]) -> str:
    """Format extracted themes as markdown tables."""
    lines = ["## Color Palette\n"]
    for name, colors in themes.items():
        is_dark = "dark" in name.lower()
        label = f"{'Dark' if is_dark else 'Light'} Theme (`{name}`)"
        lines.append(f"### {label}\n")
        lines.append("| Token | Value |")
        lines.append("|-------|-------|")
        for token, value in colors.items():
            lines.append(f"| `{token}` | `{value}` |")
        lines.append("")
    return "\n".join(lines)


def _format_defaults_section(
    defaults: dict[str, dict[str, str]],
) -> str:
    """Format component defaults as a markdown list."""
    lines = ["## Component Defaults\n"]
    for comp, props in defaults.items():
        props_str = ", ".join(f"{k}={v!r}" for k, v in props.items())
        lines.append(f"- **{comp}**: {props_str}")
    lines.append("")
    return "\n".join(lines)


def _format_scss_section(tokens: dict[str, str]) -> str:
    """Format SCSS tokens as a markdown table."""
    lines = ["## Typography & Tokens\n"]
    lines.append("| Token | Value |")
    lines.append("|-------|-------|")
    for token, value in tokens.items():
        lines.append(f"| `{token}` | `{value}` |")
    lines.append("")
    return "\n".join(lines)


def _format_cdn_boilerplate(
    vuetify_version: str,
    vue_version: str,
) -> str:
    """Generate the Vuetify CDN HTML boilerplate."""
    mdi = "https://cdn.jsdelivr.net/npm/@mdi/font@7/css/materialdesignicons.min.css"
    vcss = f"https://cdn.jsdelivr.net/npm/vuetify@{vuetify_version}/dist/vuetify.min.css"
    font = "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
    vjs = f"https://cdn.jsdelivr.net/npm/vue@{vue_version}/dist/vue.global.prod.js"
    vuejs = f"https://cdn.jsdelivr.net/npm/vuetify@{vuetify_version}/dist/vuetify.min.js"

    return f"""## Vuetify CDN Boilerplate

Use this HTML template as the starting point for all wireframes:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Wireframe</title>
  <link href="{mdi}" rel="stylesheet" />
  <link href="{vcss}" rel="stylesheet" />
  <link href="{font}" rel="stylesheet" />
  <style>
    body {{ font-family: 'Inter', sans-serif; }}
  </style>
</head>
<body>
  <div id="app">
    <v-app>
      <!-- Your wireframe content here -->
    </v-app>
  </div>
  <script src="{vjs}"><\\/script>
  <script src="{vuejs}"><\\/script>
  <script>
    const {{ createApp }} = Vue;
    const {{ createVuetify }} = Vuetify;

    const vuetify = createVuetify({{
      theme: {{
        defaultTheme: 'dark',
        themes: {{
          dark: {{
            colors: {{
              /* Paste extracted theme colors here */
            }}
          }}
        }}
      }}
    }});

    createApp({{}}).use(vuetify).mount('#app');
  </script>
</body>
</html>
```
"""


def _format_pattern_library() -> str:
    """Generate a pattern library section with common patterns."""
    return """## Pattern Library

When generating wireframes, prefer these patterns:

- **Cards**: Use the project's card component with default props
- **Status chips**: Tonal variant with semantic colors
- **Data tables**: Compact density for dense data
- **Forms**: Outlined variant, comfortable density
- **Navigation**: Permanent drawer for sidebars
- **Dialogs**: Card inside dialog, max-width constrained
- **Empty states**: Centered icon + text + action button
- **Loading**: Indeterminate progress indicator or skeleton loader

### UX Annotations

Include UX considerations as HTML comments:

```html
<!-- UX: Confirmation dialog before destructive actions -->
<!-- UX: Support sorting/filtering for >20 items -->
<!-- A11Y: Ensure color contrast ratio meets WCAG 2.1 AA -->
```
"""
