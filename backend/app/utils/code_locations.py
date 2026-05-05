# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pure helpers for the ``code_locations`` JSON shape used on
``feature_to_repo`` PRIMARY junction rows.

Lives in ``app.utils`` so any layer (repositories, services, MCP)
can use the shape without circular imports.
"""


def merge_code_locations(
    existing: dict[str, list[str]] | None,
    incoming: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    """Merge two code_locations dicts, unioning paths per layer."""
    merged: dict[str, list[str]] = {}
    all_layers = set((existing or {}).keys()) | set((incoming or {}).keys())
    for layer in sorted(all_layers):
        existing_paths: list[str] = (existing or {}).get(layer, [])
        incoming_paths: list[str] = (incoming or {}).get(layer, [])
        seen: set[str] = set(existing_paths)
        combined = list(existing_paths)
        for p in incoming_paths:
            if p not in seen:
                seen.add(p)
                combined.append(p)
        merged[layer] = combined
    return merged
