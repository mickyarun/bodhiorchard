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

"""Pydantic contract for the ``todo-generator`` agent's JSON output.

The agent runs at the BUD's dev-phase transition (or on user-triggered
regenerate) and emits a fenced JSON block matching
:class:`TodoGeneratorPayload`.  Pydantic length caps replace what the
old ``todo_parser.py`` regex used to enforce.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_TITLE_MAX = 500
_DESCRIPTION_MAX = 1000
_CONTEXT_MAX = 4000
_REPO_NAME_MAX = 120
_CODE_LOC_MAX_ITEMS = 10
_PAYLOAD_MAX_ITEMS = 200


class TodoGeneratorItem(BaseModel):
    """One TODO produced by the agent."""

    sequence: int = Field(ge=1, le=_PAYLOAD_MAX_ITEMS)
    title: str = Field(min_length=1, max_length=_TITLE_MAX)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX)
    repo_name: str | None = Field(default=None, max_length=_REPO_NAME_MAX)
    code_locations: list[str] = Field(
        default_factory=list,
        max_length=_CODE_LOC_MAX_ITEMS,
    )
    context_md: str | None = Field(default=None, max_length=_CONTEXT_MAX)
    is_checkpoint: bool = False
    phase: Literal["development"] = "development"

    model_config = ConfigDict(extra="ignore")


class TodoGeneratorPayload(BaseModel):
    """The full agent response: an ordered list of TODOs."""

    items: list[TodoGeneratorItem] = Field(max_length=_PAYLOAD_MAX_ITEMS)

    model_config = ConfigDict(extra="ignore")
