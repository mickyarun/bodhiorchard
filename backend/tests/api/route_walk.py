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

"""Every route the API serves, with the dependency tree that runs for it.

Route-walking tests (the workspace gate, no-store on people routes) need
the *effective* routes: full path plus every dependency from the routers
it was included through. Older FastAPI copied included routes up into
``router.routes`` as ``APIRoute``s with their dependencies merged; from
0.15x an included router stays one entry, and its routes are only built
when serving (``effective_candidates()``). This walks both, and reads
the ``dependant`` (what FastAPI actually solves per request) rather than
the declared lists, so it checks behaviour on either version.

Callers assert a minimum route count: if FastAPI changes shape again,
these tests fail loudly instead of passing over zero routes.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIRouter, APIWebSocketRoute


@dataclass(frozen=True)
class ServedRoute:
    """One route as served: full path, its endpoint's module, its dependencies."""

    path: str
    module: str
    dependant: Dependant


def served_routes(router: APIRouter) -> list[ServedRoute]:
    """Every HTTP and websocket route reachable through ``router``."""
    return list(_walk(router.routes))


def _walk(entries: list[Any]) -> Iterator[ServedRoute]:
    for entry in entries:
        if isinstance(entry, APIRoute | APIWebSocketRoute):
            yield ServedRoute(entry.path, entry.endpoint.__module__, entry.dependant)
        elif hasattr(entry, "effective_candidates"):  # an included router (FastAPI 0.15x)
            yield from _walk_included(entry)


def _walk_included(included: Any) -> Iterator[ServedRoute]:
    for candidate in included.effective_candidates():
        if hasattr(candidate, "effective_candidates"):
            yield from _walk_included(candidate)
        elif getattr(candidate, "dependant", None) is not None:
            module = candidate.endpoint.__module__
            yield ServedRoute(candidate.path, module, candidate.dependant)


def depends_on(route: ServedRoute, matches: Callable[[Any], bool]) -> bool:
    """Whether any dependency in the route's tree satisfies ``matches(call)``."""
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if matches(dependency.call):
            return True
        stack.extend(dependency.dependencies)
    return False
