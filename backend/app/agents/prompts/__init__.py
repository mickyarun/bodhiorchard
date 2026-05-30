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

"""Prompt builders for stage-specific agents that don't fit the legacy
``app.services.agent_prompts`` module's section-writing pattern.

The Learning Agent lives here rather than in ``agent_prompts`` because
its output (a retrospective recap) is not a BUD-document section the
existing builders manipulate — it consumes structured metrics and
writes to ``feature_learnings.retrospective_md`` instead.
"""
