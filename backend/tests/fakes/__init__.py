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

"""Deterministic fakes for the services Glideship calls out to.

* :mod:`.claude_runner` — the ``claude`` CLI, faked at the subprocess spawn,
  with scripted MCP tool calls run against the real MCP route.
* :mod:`.github`, :mod:`.slack`, :mod:`.jira` — in-memory REST APIs served
  through ``httpx.MockTransport`` by :mod:`.http_router`.
* :mod:`.signing`, :mod:`.github_payloads` — signed inbound webhooks.
* :mod:`.git_repo` — throwaway git repos with a local bare ``origin``.
* :mod:`.guard` — fails any test that still reaches the outside world.

Fixtures live in :mod:`.fixtures` (no database) and :mod:`.fixtures_db`
(integration database); see ``docs/testing/fakes.md``.
"""
