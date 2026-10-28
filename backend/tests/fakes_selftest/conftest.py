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

"""The fakes' own tests: each fake driven through the real app code it replaces."""

from tests.fakes.fixtures import (
    data_dir,
    event_recorder,
    external_guard,
    fake_claude,
    fake_embeddings,
    fake_github,
    fake_jira,
    fake_slack,
    git_repo,
    git_repo_factory,
    http_router,
)

__all__ = [
    "data_dir",
    "event_recorder",
    "external_guard",
    "fake_embeddings",
    "fake_claude",
    "fake_github",
    "fake_jira",
    "fake_slack",
    "git_repo",
    "git_repo_factory",
    "http_router",
]
