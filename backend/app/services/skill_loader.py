"""Skill loader for FlowDev agent skills.

Reads skill definition markdown files from backend/app/agents/skills/,
parses YAML frontmatter, and returns structured Skill objects.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "agents" / "skills"


@dataclass
class Skill:
    """A loaded agent skill definition."""

    name: str
    description: str
    tools: list[str]
    mcp_tools: list[str]
    prompt: str  # Full markdown body (after frontmatter)


def load_skill(skill_name: str) -> Skill:
    """Load a skill from its markdown file.

    Args:
        skill_name: The skill filename without extension (e.g., 'product-manager').

    Returns:
        A Skill object with parsed frontmatter and body.

    Raises:
        FileNotFoundError: If the skill file doesn't exist.
        ValueError: If the file has invalid frontmatter.
    """
    skill_path = SKILLS_DIR / f"{skill_name}.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_path}")

    content = skill_path.read_text()
    frontmatter, body = _parse_frontmatter(content)

    return Skill(
        name=frontmatter.get("name", skill_name),
        description=frontmatter.get("description", ""),
        tools=_parse_list(frontmatter.get("tools", "")),
        mcp_tools=_parse_list(frontmatter.get("mcp_tools", "")),
        prompt=body.strip(),
    )


def list_available_skills() -> list[str]:
    """List all available skill names (filenames without .md extension).

    Returns:
        Sorted list of skill names.
    """
    if not SKILLS_DIR.exists():
        return []
    return sorted(p.stem for p in SKILLS_DIR.glob("*.md"))


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: Raw markdown file content.

    Returns:
        Tuple of (frontmatter dict, body text).

    Raises:
        ValueError: If frontmatter delimiters are missing or YAML is invalid.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError("Invalid frontmatter: missing --- delimiters")

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}") from e

    return frontmatter, match.group(2)


def _parse_list(value: str | list) -> list[str]:
    """Parse a comma-separated string or list into a list of stripped strings.

    Args:
        value: Either a comma-separated string or already a list.

    Returns:
        List of stripped, non-empty strings.
    """
    if isinstance(value, list):
        return [s.strip() for s in value if s.strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]
