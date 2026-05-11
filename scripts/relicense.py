#!/usr/bin/env python3
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

"""One-shot license sweep: AGPL-3.0 → Apache-2.0 headers.

Run from the repo root:

    python3 scripts/relicense.py            # dry-run, prints what would change
    python3 scripts/relicense.py --apply    # actually rewrite files

Strips the existing 2-line AGPL SPDX header where present and prepends the
full Apache 2.0 boilerplate in the correct comment syntax for each file type.
Preserves shebangs and Python coding-declaration magic comments.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

COPYRIGHT_LINE = "Copyright 2025-2026 Arun Rajkumar"

APACHE_BODY = [
    "Licensed under the Apache License, Version 2.0 (the \"License\");",
    "you may not use this file except in compliance with the License.",
    "You may obtain a copy of the License at",
    "",
    "    http://www.apache.org/licenses/LICENSE-2.0",
    "",
    "Unless required by applicable law or agreed to in writing, software",
    "distributed under the License is distributed on an \"AS IS\" BASIS,",
    "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
    "See the License for the specific language governing permissions and",
    "limitations under the License.",
]

AGPL_SPDX = "SPDX-License-Identifier: AGPL-3.0-or-later"
AGPL_COPYRIGHT_PREFIX = "Copyright (C) 2026 Arun Rajkumar"

# Directories that must not be touched at all.
SKIP_DIRS = {
    ".git",
    ".claude",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    ".next",
    ".vite",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "engine_bkup",  # frontend/src/engine_bkup — old engine backup
    "vendor",
    "third_party",
}

# Specific files that should never be rewritten by this script (e.g., self).
SKIP_EXACT_PATHS = {
    "scripts/relicense.py",
}

SKIP_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "pnpm-lock.yaml",
}


@dataclass(frozen=True)
class LangSpec:
    """Comment-syntax description for one source language."""

    prefix: str          # comment-line prefix, e.g. "# " or "// "
    block_open: str | None = None   # for block comments like /* */
    block_close: str | None = None

    def line_comment(self, text: str) -> str:
        if self.block_open is not None:
            return text  # caller assembles block separately
        # For line comments, prefix every line; blank lines become bare prefix.
        return (self.prefix + text).rstrip() if text else self.prefix.rstrip()

    def build_header(self) -> str:
        if self.block_open and self.block_close:
            inner = "\n".join(
                [f" * {COPYRIGHT_LINE}", " *"]
                + [f" * {line}" if line else " *" for line in APACHE_BODY]
            )
            return f"{self.block_open}\n{inner}\n {self.block_close}\n"
        # line-comment style
        out_lines = [self.line_comment(COPYRIGHT_LINE), self.line_comment("")]
        out_lines.extend(self.line_comment(line) for line in APACHE_BODY)
        return "\n".join(out_lines) + "\n"


LANG_BY_EXT: dict[str, LangSpec] = {
    ".py":   LangSpec(prefix="# "),
    ".sh":   LangSpec(prefix="# "),
    ".bash": LangSpec(prefix="# "),
    ".ts":   LangSpec(prefix="// "),
    ".tsx":  LangSpec(prefix="// "),
    ".js":   LangSpec(prefix="// "),
    ".jsx":  LangSpec(prefix="// "),
    ".mjs":  LangSpec(prefix="// "),
    ".cjs":  LangSpec(prefix="// "),
    ".css":  LangSpec(prefix="", block_open="/*", block_close="*/"),
    ".scss": LangSpec(prefix="", block_open="/*", block_close="*/"),
    ".vue":  LangSpec(prefix="", block_open="<!--", block_close="-->"),
}


@dataclass
class FileResult:
    path: Path
    action: str  # "header-added", "agpl-replaced", "already-apache", "skipped:reason"


def is_skipped_path(path: Path) -> str | None:
    """Return a reason string if this path should be skipped, else None."""
    rel = path.relative_to(REPO_ROOT)
    rel_str = rel.as_posix()
    if rel_str in SKIP_EXACT_PATHS:
        return "self-script"
    for seg in rel.parts:
        if seg in SKIP_DIRS:
            return f"in-{seg}"
    if path.name in SKIP_FILENAMES:
        return "lockfile"
    if path.name.endswith(".min.js") or path.name.endswith(".min.css"):
        return "minified"
    return None


def has_apache_header(text: str) -> bool:
    return "Licensed under the Apache License, Version 2.0" in text[:2000]


def strip_existing_agpl(lines: list[str]) -> tuple[list[str], bool]:
    """If the file has the AGPL SPDX header pattern at the top, remove it.

    The repo's existing pattern is two contiguous comment lines:
        # SPDX-License-Identifier: AGPL-3.0-or-later
        # Copyright (C) 2026 Arun Rajkumar
    or with // for TS/JS, or inside <!-- --> for Vue.
    Returns (lines_without_agpl_block, was_agpl_present).
    """
    # Scan the first ~6 lines for the SPDX marker; remove that line plus
    # the adjacent copyright line if it matches.
    scan_limit = min(len(lines), 8)
    spdx_idx: int | None = None
    for i in range(scan_limit):
        if AGPL_SPDX in lines[i]:
            spdx_idx = i
            break
    if spdx_idx is None:
        return lines, False

    # Identify the contiguous AGPL header block to remove. Typically:
    #   line N:   <comment> SPDX-License-Identifier: AGPL-3.0-or-later
    #   line N+1: <comment> Copyright (C) 2026 Arun Rajkumar
    # Plus optionally a trailing blank line.
    remove_from = spdx_idx
    remove_to = spdx_idx + 1
    if remove_to < len(lines) and AGPL_COPYRIGHT_PREFIX in lines[remove_to]:
        remove_to += 1
    # Eat one trailing blank line if present so we don't accumulate blanks.
    if remove_to < len(lines) and lines[remove_to].strip() == "":
        remove_to += 1

    return lines[:remove_from] + lines[remove_to:], True


def find_insertion_point(lines: list[str], suffix: str) -> int:
    """Find the line index after any preserved structural prefix.

    - Shebangs at line 0 (any extension) are preserved.
    - Python encoding declarations on line 0 or 1 are preserved.
    """
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    if suffix == ".py":
        # PEP 263: encoding decl may be on line 1 or 2.
        for j in (idx, idx + 1):
            if j < len(lines) and "coding" in lines[j] and lines[j].lstrip().startswith("#"):
                idx = j + 1
                break
    return idx


def process_file(path: Path, apply: bool) -> FileResult:
    suffix = path.suffix.lower()
    spec = LANG_BY_EXT.get(suffix)
    if spec is None:
        return FileResult(path, f"skipped:ext-{suffix or 'noext'}")

    skip_reason = is_skipped_path(path)
    if skip_reason:
        return FileResult(path, f"skipped:{skip_reason}")

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return FileResult(path, "skipped:binary")

    if has_apache_header(text):
        return FileResult(path, "already-apache")

    lines = text.splitlines(keepends=True)
    lines, had_agpl = strip_existing_agpl(lines)
    insertion = find_insertion_point(lines, suffix)

    header = spec.build_header()
    # Ensure exactly one blank line between header and the following content.
    after = lines[insertion:]
    while after and after[0].strip() == "":
        after = after[1:]
    new_lines = lines[:insertion] + [header, "\n"] + after
    new_text = "".join(new_lines)

    if apply:
        path.write_text(new_text, encoding="utf-8")

    return FileResult(path, "agpl-replaced" if had_agpl else "header-added")


def iter_source_files() -> list[Path]:
    """Walk REPO_ROOT and yield candidate source files."""
    out: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in LANG_BY_EXT:
            continue
        out.append(path)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    args = parser.parse_args()

    files = iter_source_files()
    results: list[FileResult] = []
    for path in files:
        results.append(process_file(path, apply=args.apply))

    by_action: dict[str, int] = {}
    for r in results:
        by_action[r.action] = by_action.get(r.action, 0) + 1

    print(f"Scanned {len(results)} files under {REPO_ROOT}")
    for action, count in sorted(by_action.items()):
        print(f"  {action:30s} {count}")

    if not args.apply:
        print("\n(dry-run — re-run with --apply to write changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
