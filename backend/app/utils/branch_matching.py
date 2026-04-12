"""Branch name matching with optional glob pattern support."""

from fnmatch import fnmatch


def branch_matches(ref: str, pattern: str) -> bool:
    """Check if a branch ref matches a configured pattern.

    Supports exact match (``release/uat``) and ``fnmatch``-style wildcards
    (``release*`` matches ``release/uat``, ``release/v2.1``). Patterns
    without glob characters fall back to simple equality.
    """
    if "*" in pattern or "?" in pattern or "[" in pattern:
        return fnmatch(ref, pattern)
    return ref == pattern
