"""GitNexus integration and documentation extraction for codebase indexing.

Runs the GitNexus CLI (via npx) to analyze a repository, then queries the
knowledge graph for communities (feature clusters) and execution flows.
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from app.services.gitnexus_utils import find_npx as _find_npx  # noqa: I001
from app.services.gitnexus_utils import parse_cypher_community_list as _parse_cypher_community_list
from app.services.gitnexus_utils import parse_markdown_table as _parse_markdown_table
from app.services.gitnexus_utils import parse_single_column as _parse_single_column
from app.services.gitnexus_utils import run_cypher as _run_cypher
from app.services.gitnexus_utils import run_npx as _run_npx

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


## _find_npx, _run_npx_sync, _run_npx, _run_cypher are imported from gitnexus_utils


async def index_repo_with_gitnexus(
    repo_path: str,
    *,
    force: bool = True,
) -> GitNexusResult:
    """Run GitNexus analyze then query the knowledge graph for features.

    Steps:
    1. Run `gitnexus analyze` to build/update the knowledge graph
    2. Query communities (feature clusters) with their member files
    3. Query execution flows (processes)
    4. Read meta.json for stats
    5. Read README.md first paragraph as repo overview

    Args:
        repo_path: Absolute path to the git repository root.
        force: If True, pass ``--force`` to re-index even if unchanged.
            Incremental scans pass False so GitNexus skips if the source
            hash is unchanged (fast no-op).

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
            "Install Node.js from https://nodejs.org/ and restart Bodhigrove."
        )

    # Step 1: Run gitnexus analyze
    try:
        logger.info("gitnexus_starting", repo=repo_path, force=force)
        analyze_args = ["analyze"]
        if force:
            analyze_args.append("--force")
        analyze_args.append(str(repo))
        stdout, stderr, returncode = await _run_npx(
            npx,
            analyze_args,
            cwd=str(repo),
            timeout=300,
        )

        if returncode != 0:
            # npm peer dependency warnings cause exit code 1 but analysis succeeds
            is_npm_warn_only = "npm warn" in stderr and "error" not in stderr.lower()
            if is_npm_warn_only:
                logger.info(
                    "gitnexus_npm_warnings_ignored",
                    returncode=returncode,
                    stderr_preview=stderr[:200],
                )
            else:
                logger.warning(
                    "gitnexus_nonzero_exit",
                    returncode=returncode,
                    stderr=stderr[:500],
                )
                result.error = (
                    f"GitNexus analyze failed (code {returncode}): "
                    f"{stderr[:200]}"
                )
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

    # Step 1b: Run gitnexus setup (generates CLAUDE.md integration for the repo)
    try:
        setup_stdout, setup_stderr, setup_rc = await _run_npx(
            npx,
            ["setup"],
            cwd=str(repo),
            timeout=60,
        )
        if setup_rc != 0:
            logger.warning(
                "gitnexus_setup_nonzero", returncode=setup_rc, stderr=setup_stderr[:300]
            )
        else:
            logger.info("gitnexus_setup_complete", repo=repo_path)
    except TimeoutError:
        logger.warning("gitnexus_setup_timeout", repo=repo_path)
    except (FileNotFoundError, OSError):
        logger.warning("gitnexus_setup_failed", repo=repo_path)

    # Step 1c: Register gitnexus MCP server so Claude Code can use it
    from app.services.claude_runner import ensure_gitnexus_mcp

    await ensure_gitnexus_mcp()

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


## _parse_markdown_table, _parse_cypher_community_list, _parse_single_column
## are imported from gitnexus_utils


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
