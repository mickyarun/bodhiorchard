# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Design system extractor — uses LLM to analyze frontend source files.

Discovers design-related files in a repository (theme configs, styles,
package.json), sends them to the configured LLM (via Claude Code CLI),
and gets back structured markdown with design tokens, CDN boilerplate,
and a pattern library.

Falls back to basic regex extraction if the CLI is unavailable.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExtractionResult:
    """Result of a design system extraction."""

    content: str
    source_hash: str
    method: str  # "llm", "regex_fallback", "minimal"
    error: str | None = None  # Non-fatal error (e.g. LLM timeout)


# Glob patterns to discover design-related files (broad search)
_DESIGN_FILE_PATTERNS = [
    # Vuetify / Vue config
    "**/vuetify.ts",
    "**/vuetify.js",
    "**/vuetify.config.*",
    # Theme / style files
    "**/theme.ts",
    "**/theme.js",
    "**/theme.config.*",
    "**/themes/**/*.ts",
    "**/themes/**/*.js",
    # CSS / SCSS / SASS
    "**/main.scss",
    "**/main.css",
    "**/variables.scss",
    "**/variables.css",
    "**/tokens.scss",
    "**/tokens.css",
    "**/global.scss",
    "**/global.css",
    # Tailwind
    "tailwind.config.*",
    "**/tailwind.config.*",
    # MUI / Material UI
    "**/createTheme.*",
    "**/palette.*",
    # package.json (for framework detection & CDN versions)
    "package.json",
]

# Directories to skip during file discovery
_SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    "__pycache__",
}

# Max file size to include in the prompt (50KB)
_MAX_FILE_SIZE = 50_000

# Max total content to send to LLM (200KB)
_MAX_TOTAL_CONTENT = 200_000


async def extract_design_system(repo_path: Path) -> ExtractionResult:
    """Extract design system from a repository using the LLM.

    Discovers design-related files, sends them to Claude Code CLI for
    intelligent extraction, and returns structured markdown.

    Falls back to regex-based extraction if the CLI is unavailable or times out.

    Args:
        repo_path: Path to the repository root.

    Returns:
        ExtractionResult with content, hash, method used, and any non-fatal error.
    """
    # 1. Discover design-related files
    discovered = _discover_design_files(repo_path)
    if not discovered:
        logger.warning("no_design_files_found", repo_path=str(repo_path))
        content, source_hash = _fallback_minimal(repo_path)
        return ExtractionResult(
            content=content,
            source_hash=source_hash,
            method="minimal",
        )

    # 2. Read file contents
    file_contents = _read_discovered_files(discovered)
    source_hash = _compute_hash(file_contents)

    # 3. Try LLM-powered extraction
    from app.services.claude_runner import is_claude_cli_available

    llm_error: str | None = None
    if is_claude_cli_available():
        try:
            markdown, llm_err = await _llm_extract(repo_path, file_contents)
            if markdown:
                logger.info(
                    "design_system_extracted_via_llm",
                    repo_path=str(repo_path),
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
            logger.exception("llm_extraction_failed", repo_path=str(repo_path))
    else:
        llm_error = "Claude Code CLI not available"

    # 4. Fallback to regex extraction
    logger.info("design_system_fallback_regex", repo_path=str(repo_path))
    markdown = _regex_extract(repo_path, file_contents)
    return ExtractionResult(
        content=markdown,
        source_hash=source_hash,
        method="regex_fallback",
        error=llm_error or "LLM extraction returned empty result — used regex fallback",
    )


def discover_design_files(repo_path: Path) -> list[Path]:
    """Find design-related files in the repository using glob patterns.

    Args:
        repo_path: Repository root path.

    Returns:
        Sorted list of discovered file paths.
    """
    found: set[Path] = set()
    for pattern in _DESIGN_FILE_PATTERNS:
        for path in repo_path.glob(pattern):
            if path.is_file() and not _in_skip_dir(path, repo_path):
                found.add(path)

    # Sort by path for deterministic ordering
    return sorted(found)


# Backwards-compat alias
_discover_design_files = discover_design_files


def _in_skip_dir(path: Path, root: Path) -> bool:
    """Check if a path is inside a directory we should skip."""
    try:
        relative = path.relative_to(root)
        return any(part in _SKIP_DIRS for part in relative.parts)
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


# Backwards-compat alias
_read_discovered_files = read_discovered_files


def compute_hash(file_contents: dict[str, str]) -> str:
    """Compute SHA256 hash of all discovered file contents."""
    combined = "".join(f"{k}:{v}" for k, v in sorted(file_contents.items()))
    return hashlib.sha256(combined.encode()).hexdigest()


# Backwards-compat alias
_compute_hash = compute_hash


async def _get_gitnexus_context(repo_path: Path) -> str:
    """Query GitNexus for a quick project structure overview.

    Uses GitNexus CLI to find design-relevant files and framework info,
    avoiding the need to glob/read everything ourselves.

    Args:
        repo_path: Repository root path.

    Returns:
        Summary string (may be empty if GitNexus unavailable).
    """
    from app.services.gitnexus_utils import find_npx, run_npx

    npx = find_npx()
    if not npx:
        return ""

    try:
        stdout, _, rc = await run_npx(
            npx,
            ["query", "theme design system style colors typography"],
            cwd=str(repo_path),
            timeout=15,
        )
        if rc == 0 and stdout.strip():
            return f"## GitNexus Context\n\n{stdout.strip()}\n"
    except Exception:
        logger.debug("gitnexus_context_unavailable", repo_path=str(repo_path))

    return ""


async def _llm_extract(
    repo_path: Path,
    file_contents: dict[str, str],
) -> tuple[str | None, str | None]:
    """Use Claude Code CLI to intelligently extract the design system.

    Sends discovered file paths (and small file contents inline) to the
    LLM, which can read additional files from the repo via its tools.
    Optionally includes GitNexus context for faster navigation.

    Args:
        repo_path: Repository root (used as working_dir for CLI).
        file_contents: Dict of filename → content for design-related files.

    Returns:
        Tuple of (markdown_content_or_none, error_message_or_none).
    """
    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    # Get GitNexus context for faster file discovery
    gitnexus_ctx = await _get_gitnexus_context(repo_path)

    # Inline all design files (theme configs are rarely >20KB).
    # Only list paths for truly large files like full package.json with 100+ deps.
    inline_parts = []
    path_only_files = []
    for filename, content in file_contents.items():
        if len(content) < 20_000:
            inline_parts.append(f"### {filename}\n```\n{content}\n```")
        else:
            path_only_files.append(f"- `{filename}` ({len(content)} bytes)")

    file_context = "\n\n".join(inline_parts) if inline_parts else "(none inlined)"
    paths_section = "\n".join(path_only_files) if path_only_files else ""

    prompt_parts = [
        "You are a design system analyzer. Extract the design system "
        "from this repository into structured markdown.\n",
    ]

    if gitnexus_ctx:
        prompt_parts.append(gitnexus_ctx)

    prompt_parts.append(f"## Key Files (inlined)\n\n{file_context}\n")

    if paths_section:
        prompt_parts.append(f"## Additional Files (read from disk if needed)\n\n{paths_section}\n")

    prompt_parts.append(
        "## Instructions\n\n"
        "Analyze the source files and produce a design system reference "
        "document in markdown with these sections:\n\n"
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

    prompt = "\n".join(prompt_parts)

    result = await run_claude_code(
        prompt=prompt,
        working_dir=repo_path,
        config=ClaudeRunnerConfig(max_turns=15, timeout_seconds=300),
    )

    if not result.success:
        logger.warning(
            "llm_extract_failed",
            error=result.error,
            output_preview=result.output[:200],
        )
        return None, result.error or "LLM extraction failed"

    output = result.output.strip()

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


def _fallback_minimal(repo_path: Path) -> tuple[str, str]:
    """Produce a minimal design system when no files are found.

    Args:
        repo_path: Repository root path.

    Returns:
        Tuple of (markdown_content, source_hash).
    """
    # Try reading at least package.json
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
