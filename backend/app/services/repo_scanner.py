"""GitNexus integration and documentation extraction for codebase indexing.

Runs the GitNexus CLI (via npx) to analyze a repository, then queries the
knowledge graph for communities (feature clusters) and execution flows.
"""

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FeatureEntry:
    """A feature cluster extracted from the GitNexus knowledge graph."""

    name: str
    overview: str
    files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class ProcessEntry:
    """An execution flow extracted from the GitNexus knowledge graph."""

    name: str
    step_count: int


@dataclass
class DocEntry:
    """A documentation file extracted from the repository."""

    title: str
    content: str
    source_ref: str


@dataclass
class GitNexusResult:
    """Structured output from a GitNexus indexing run."""

    repo_overview: str = ""
    features: list[FeatureEntry] = field(default_factory=list)
    processes: list[ProcessEntry] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    success: bool = False
    error: str | None = None


class GitNexusNotInstalledError(Exception):
    """Raised when npx/Node.js is not available to run GitNexus."""


def _find_npx() -> str | None:
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


async def _run_npx(
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


async def _run_cypher(
    npx: str,
    query: str,
    cwd: str,
    repo_name: str,
    timeout: int = 30,
) -> tuple[str, str, int]:
    """Run a gitnexus cypher query with --repo flag for multi-repo disambiguation."""
    return await _run_npx(
        npx,
        ["cypher", "--repo", repo_name, query],
        cwd=cwd,
        timeout=timeout,
    )


async def index_repo_with_gitnexus(repo_path: str) -> GitNexusResult:
    """Run GitNexus analyze then query the knowledge graph for features.

    Steps:
    1. Run `gitnexus analyze` to build/update the knowledge graph
    2. Query communities (feature clusters) with their member files
    3. Query execution flows (processes)
    4. Read meta.json for stats
    5. Read README.md first paragraph as repo overview

    Args:
        repo_path: Absolute path to the git repository root.

    Returns:
        GitNexusResult with communities as features and execution flows.

    Raises:
        GitNexusNotInstalledError: If npx is not found on the system.
    """
    result = GitNexusResult()
    repo = Path(repo_path)
    repo_name = repo.name  # Directory name used by gitnexus --repo flag

    if not repo.exists() or not (repo / ".git").exists():
        result.error = f"Not a valid git repository: {repo_path}"
        return result

    npx = _find_npx()
    if not npx:
        raise GitNexusNotInstalledError(
            "Node.js (npx) is required for codebase indexing. "
            "Install Node.js from https://nodejs.org/ and restart FlowDev."
        )

    # Step 1: Run gitnexus analyze
    try:
        logger.info("gitnexus_starting", repo=repo_path)
        stdout, stderr, returncode = await _run_npx(
            npx,
            ["analyze", "--force", str(repo)],
            cwd=str(repo),
            timeout=300,
        )

        if returncode != 0:
            logger.warning("gitnexus_nonzero_exit", returncode=returncode, stderr=stderr[:500])
            result.error = f"GitNexus analyze failed (code {returncode}): {stderr[:200]}"
            return result

        logger.info("gitnexus_analyze_complete", repo=repo_path)
    except TimeoutError:
        result.error = "GitNexus analyze timed out after 300s"
        return result
    except (FileNotFoundError, OSError) as exc:
        raise GitNexusNotInstalledError(
            f"Failed to run GitNexus via npx: {exc}. "
            "Ensure Node.js is installed and npx is on your PATH."
        ) from exc

    # Brief pause to let LadybugDB release the write lock before querying
    await asyncio.sleep(2)

    # Step 2: Read meta.json for stats
    meta_path = repo / ".gitnexus" / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            result.stats = meta.get("stats", {})
        except (json.JSONDecodeError, OSError):
            pass

    # Step 3: Query communities (feature clusters) from knowledge graph
    # Two-pass approach: Kuzu/LadybugDB doesn't allow ORDER BY on node properties
    # after aggregation, so we first get community list, then files per community.
    try:
        # 3a: Get top communities by symbol count
        comm_list_json, comm_list_stderr, rc = await _run_cypher(
            npx,
            "MATCH (c:Community) "
            "RETURN c.label AS community, c.symbolCount AS symbols "
            "ORDER BY symbols DESC LIMIT 50",
            cwd=str(repo),
            repo_name=repo_name,
        )

        logger.info(
            "gitnexus_cypher_community_list_raw",
            rc=rc,
            stdout_len=len(comm_list_json),
            stdout_preview=comm_list_json[:500] if comm_list_json else "(empty)",
            stderr=comm_list_stderr[:300] if comm_list_stderr else "(empty)",
        )

        if rc == 0 and comm_list_json.strip():
            comm_list_data = json.loads(comm_list_json)
            if "markdown" in comm_list_data:
                # Parse community names + symbols from the list query
                community_names = _parse_cypher_community_list(comm_list_data["markdown"])

                if community_names:
                    # 3b: Get files per community individually
                    # (gitnexus truncates cypher output at 64KB, so we
                    #  can't fetch all communities' files in one query)
                    community_files: dict[str, list[str]] = {}
                    unique_names = [name for name, _ in community_names]

                    for comm_name in unique_names:
                        # Escape single quotes in community name for cypher
                        safe_name = comm_name.replace("'", "\\'")
                        fj, _, frc = await _run_cypher(
                            npx,
                            f"MATCH (s)-[:CodeRelation]->(c:Community) "
                            f"WHERE c.label = '{safe_name}' "
                            f"RETURN DISTINCT s.filePath AS file "
                            f"LIMIT 30",
                            cwd=str(repo),
                            repo_name=repo_name,
                            timeout=15,
                        )
                        if frc == 0 and fj.strip():
                            try:
                                fd = json.loads(fj)
                                if "markdown" in fd:
                                    files = _parse_single_column(fd["markdown"])
                                    community_files[comm_name] = files
                            except json.JSONDecodeError:
                                pass

                    logger.info(
                        "gitnexus_community_files_loaded",
                        communities_with_files=len(community_files),
                    )

                    # Merge: community list + their files
                    result.features = _build_features(community_names, community_files)

            logger.info(
                "gitnexus_communities_loaded",
                count=len(result.features),
                repo=repo_path,
            )
        else:
            logger.warning(
                "gitnexus_cypher_communities_empty",
                rc=rc,
                repo=repo_path,
            )
    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("gitnexus_cypher_communities_failed", error=str(exc))

    # Step 4: Query execution flows (processes)
    try:
        processes_json, processes_stderr, rc = await _run_cypher(
            npx,
            "MATCH (p:Process) "
            "RETURN p.label AS process, p.stepCount AS steps "
            "ORDER BY p.stepCount DESC LIMIT 30",
            cwd=str(repo),
            repo_name=repo_name,
        )

        logger.info(
            "gitnexus_cypher_processes_raw",
            rc=rc,
            stdout_len=len(processes_json),
            stdout_preview=processes_json[:500] if processes_json else "(empty)",
            stderr=processes_stderr[:300] if processes_stderr else "(empty)",
        )

        if rc == 0 and processes_json.strip():
            processes_data = json.loads(processes_json)
            if "markdown" in processes_data:
                result.processes = _parse_cypher_processes(processes_data["markdown"])
            logger.info(
                "gitnexus_processes_loaded",
                count=len(result.processes),
                repo=repo_path,
            )
        else:
            logger.warning(
                "gitnexus_cypher_processes_empty",
                rc=rc,
                repo=repo_path,
            )
    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("gitnexus_cypher_processes_failed", error=str(exc))

    # Step 5: Build repo overview from README.md + stats
    readme = repo / "README.md"
    overview_parts: list[str] = []
    if result.stats:
        s = result.stats
        overview_parts.append(
            f"Codebase: {s.get('files', 0)} files, "
            f"{s.get('nodes', 0)} symbols, "
            f"{s.get('edges', 0)} relationships, "
            f"{s.get('communities', 0)} feature clusters, "
            f"{s.get('processes', 0)} execution flows."
        )
    if readme.exists():
        readme_content = readme.read_text(errors="replace")
        # Take first meaningful paragraph (skip headings)
        for para in readme_content.split("\n\n"):
            stripped = para.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 30:
                overview_parts.append(stripped[:1000])
                break
    result.repo_overview = "\n\n".join(overview_parts)

    result.success = True
    return result


def _parse_markdown_table(markdown: str) -> list[list[str]]:
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


def _parse_cypher_community_list(markdown: str) -> list[tuple[str, int]]:
    """Parse community list query: community, symbols.

    Deduplicates by name, summing symbol counts for communities with the same label.

    Args:
        markdown: Markdown table from cypher output.

    Returns:
        List of (name, total_symbols) tuples, deduplicated and sorted by symbols desc.
    """
    rows = _parse_markdown_table(markdown)
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


def _parse_single_column(markdown: str) -> list[str]:
    """Parse a single-column markdown table into a list of values.

    Args:
        markdown: Markdown table with one column.

    Returns:
        Deduplicated list of values.
    """
    seen: set[str] = set()
    result: list[str] = []
    for row in _parse_markdown_table(markdown):
        if row and row[0] and row[0] not in seen:
            seen.add(row[0])
            result.append(row[0])
    return result


def _build_features(
    community_names: list[tuple[str, int]],
    community_files: dict[str, list[str]],
) -> list[FeatureEntry]:
    """Build FeatureEntry list from community names and file mappings.

    Args:
        community_names: List of (name, total_symbols) from the list query.
        community_files: Dict of community name → file paths from the files query.

    Returns:
        List of FeatureEntry objects.
    """
    features: list[FeatureEntry] = []
    for name, symbols in community_names:
        files = community_files.get(name, [])[:30]
        overview = f"{name} — {symbols} symbols across {len(files)} files."
        features.append(
            FeatureEntry(
                name=name,
                overview=overview,
                files=files,
                tags=[],
            )
        )
    return features


def _parse_cypher_processes(markdown: str) -> list[ProcessEntry]:
    """Parse the markdown table from a cypher process query.

    Expected columns: process, steps

    Args:
        markdown: Markdown table string from gitnexus cypher output.

    Returns:
        List of ProcessEntry objects.
    """
    processes: list[ProcessEntry] = []
    for row in _parse_markdown_table(markdown):
        if len(row) < 2:
            continue
        name = row[0]
        try:
            steps = int(row[1])
        except ValueError:
            steps = 0
        processes.append(ProcessEntry(name=name, step_count=steps))
    return processes


async def extract_repo_docs(repo_path: str) -> list[DocEntry]:
    """Find documentation files (README.md, docs/*.md) and return them.

    Excludes GitNexus-generated files (CLAUDE.md, AGENTS.md) since those
    contain agent instructions, not codebase documentation.

    Args:
        repo_path: Absolute path to the git repository root.

    Returns:
        List of DocEntry objects with title, content, and source reference.
    """
    docs: list[DocEntry] = []
    repo = Path(repo_path)

    # Top-level docs (skip CLAUDE.md and AGENTS.md — those are GitNexus agent instructions)
    for name in ["README.md", "CONTRIBUTING.md", "ARCHITECTURE.md"]:
        doc_path = repo / name
        if doc_path.exists():
            content = doc_path.read_text(errors="replace")
            if content.strip():
                docs.append(
                    DocEntry(
                        title=name.replace(".md", "").replace("-", " ").title(),
                        content=content[:10000],
                        source_ref=name,
                    )
                )

    # docs/ directory
    docs_dir = repo / "docs"
    if docs_dir.is_dir():
        for md_file in sorted(docs_dir.glob("**/*.md")):
            content = md_file.read_text(errors="replace")
            if content.strip():
                rel_path = str(md_file.relative_to(repo))
                title = md_file.stem.replace("-", " ").replace("_", " ").title()
                docs.append(
                    DocEntry(
                        title=title,
                        content=content[:10000],
                        source_ref=rel_path,
                    )
                )

    logger.info("extract_repo_docs", repo=repo_path, doc_count=len(docs))
    return docs
