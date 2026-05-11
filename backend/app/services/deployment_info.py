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

"""Detect whether the backend is running inside a Docker container.

The UI uses this to branch the Claude auth experience: Docker deployments
cannot reach a host ``claude login`` session, so the only sensible option
is an Anthropic API key entered in Settings. Host deployments default to
trusting whatever ``claude login`` the user already has on their machine.
"""

from __future__ import annotations

import platform
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def is_running_in_docker() -> bool:
    """Return True when this process runs inside a Docker/containerd container.

    Docker creates ``/.dockerenv`` at the root of every container it starts;
    containerd-based runtimes (e.g. Kubernetes without dockershim) don't, so
    we also inspect ``/proc/1/cgroup`` as a fallback.
    """
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
    except OSError:
        return False
    return "docker" in cgroup or "containerd" in cgroup or "kubepods" in cgroup


def deployment_mode() -> str:
    """Return ``"docker"`` or ``"host"`` based on container detection."""
    return "docker" if is_running_in_docker() else "host"


def deployment_info() -> dict:
    """Summary dict surfaced to the setup UI."""
    in_docker = is_running_in_docker()
    return {
        "mode": "docker" if in_docker else "host",
        "hostname": platform.node(),
        # The auth mode the UI should default to. Docker deployments cannot
        # inherit a host `claude login` session, so an API key is the only
        # workable path unless ANTHROPIC_API_KEY is injected at the compose
        # layer. Host deployments default to trusting the user's login.
        "claude_auth_recommended": "api_key" if in_docker else "host",
    }
