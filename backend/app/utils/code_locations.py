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
