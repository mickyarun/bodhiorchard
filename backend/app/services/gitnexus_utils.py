# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Shared GitNexus CLI utilities for Cypher queries and markdown parsing.

Extracted from repo_scanner.py so tree_data.py can reuse the same
query and parsing logic without duplicating code.
"""

import asyncio
import shutil
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def find_npx() -> str | None:
    """Find the npx binary, checking common Node.js install locations."""
    npx = shutil.which("npx")
    if npx:
        return npx
    for candidate in [
        Path.home() / ".nvm" / "current" / "bin" / "npx",
        Path("/usr/local/bin/npx"),
        Path("/opt/homebrew/bin/npx"),
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def _run_npx_sync(
    npx: str,
    args: list[str],
    cwd: str,
    timeout: int = 60,
) -> tuple[str, str, int]:
    """Run a gitnexus command via npx synchronously (for use in a thread)."""
    import subprocess

    result = subprocess.run(
        [npx, "--yes", "gitnexus", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
    return (result.stdout, result.stderr, result.returncode)


async def run_npx(
    npx: str,
    args: list[str],
    cwd: str,
    timeout: int = 60,
) -> tuple[str, str, int]:
    """Run a gitnexus command via npx and return (stdout, stderr, returncode).

    Uses subprocess.run in a thread to avoid asyncio pipe buffer truncation
    with large outputs (>8KB).
    """
    return await asyncio.to_thread(_run_npx_sync, npx, args, cwd, timeout)


async def run_cypher(
    npx: str,
    query: str,
    cwd: str,
    repo_name: str,
    timeout: int = 30,
) -> tuple[str, str, int]:
    """Run a gitnexus cypher query with --repo flag for multi-repo disambiguation."""
    return await run_npx(
        npx,
        ["cypher", "--repo", repo_name, query],
        cwd=cwd,
        timeout=timeout,
    )


def parse_markdown_table(markdown: str) -> list[list[str]]:
    """Parse a markdown table into a list of rows (each row is a list of cell values).

    Skips the header row and separator row. Returns only data rows.

    Args:
        markdown: Markdown table string.

    Returns:
        List of rows, where each row is a list of stripped cell strings.
    """
    lines = markdown.strip().split("\n")
    data_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("| ---")]
    if len(data_lines) < 2:
        return []
    rows: list[list[str]] = []
    for line in data_lines[1:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if cells:
            rows.append(cells)
    return rows


def parse_cypher_community_list(markdown: str) -> list[tuple[str, int]]:
    """Parse community list query: community, symbols.

    Deduplicates by name, summing symbol counts for communities with the same label.

    Args:
        markdown: Markdown table from cypher output.

    Returns:
        List of (name, total_symbols) tuples, deduplicated and sorted by symbols desc.
    """
    rows = parse_markdown_table(markdown)
    totals: dict[str, int] = {}
    for row in rows:
        if len(row) < 2:
            continue
        name = row[0]
        try:
            symbols = int(row[1])
        except ValueError:
            symbols = 0
        totals[name] = totals.get(name, 0) + symbols

    return sorted(totals.items(), key=lambda x: x[1], reverse=True)


def parse_single_column(markdown: str) -> list[str]:
    """Parse a single-column markdown table into a list of values.

    Args:
        markdown: Markdown table with one column.

    Returns:
        Deduplicated list of values.
    """
    seen: set[str] = set()
    result: list[str] = []
    for row in parse_markdown_table(markdown):
        if row and row[0] and row[0] not in seen:
            seen.add(row[0])
            result.append(row[0])
    return result
