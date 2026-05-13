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

"""Em-dash metadata-suffix parsing for :mod:`todo_parser`.

Pulls ``repo: <name>`` / ``files: <path1>, <path2>`` segments off the end
of an Implementation TODO line. Package-private — callers should use
:func:`app.services.todo_parser.parse_implementation_todos`.
"""

import re

# Em-dash separator the tech-planner uses between title and metadata.
# Matches both U+2014 (em-dash) and U+2013 (en-dash) to stay tolerant of
# editor auto-correct.
_METADATA_SPLIT_RE = re.compile(r"\s+[–—]\s+")
_REPO_KV_RE = re.compile(r"^repo\s*:\s*(.+?)\s*$", re.IGNORECASE)
_FILES_KV_RE = re.compile(r"^files\s*:\s*(.+?)\s*$", re.IGNORECASE)

_MAX_REPO_NAME_LEN = 120
_MAX_CODE_LOCATIONS = 10


def split_metadata_suffix(
    line_text: str,
    known_repos: set[str],
) -> tuple[str, str | None, list[str]]:
    """Pull ``repo:`` / ``files:`` segments off the end of a TODO line.

    Returns ``(title_without_suffix, repo_name_or_None, code_locations)``.
    Unknown repo names against ``known_repos`` resolve to ``None`` so a
    typo in the spec does not silently bind the TODO to a wrong repo.
    """
    segments = _METADATA_SPLIT_RE.split(line_text)
    if len(segments) == 1:
        return line_text.strip(), None, []

    title_parts: list[str] = [segments[0]]
    repo_name: str | None = None
    code_locations: list[str] = []

    for segment in segments[1:]:
        repo_match = _REPO_KV_RE.match(segment)
        files_match = _FILES_KV_RE.match(segment)
        if repo_match:
            candidate = repo_match.group(1).strip()[:_MAX_REPO_NAME_LEN]
            repo_name = candidate if candidate in known_repos else None
            continue
        if files_match:
            code_locations = _parse_file_list(files_match.group(1))
            continue
        # Unknown segment — keep it on the title so we don't drop content.
        title_parts.append(segment)

    return " — ".join(p.strip() for p in title_parts if p.strip()), repo_name, code_locations


def _parse_file_list(raw: str) -> list[str]:
    """Split a comma-separated file-paths string; dedupe; cap at 10."""
    seen: set[str] = set()
    paths: list[str] = []
    for piece in raw.split(","):
        path = piece.strip().strip("`")
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
        if len(paths) >= _MAX_CODE_LOCATIONS:
            break
    return paths
