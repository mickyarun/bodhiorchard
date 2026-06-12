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

"""Schemas for garden mini-game scoring and daily-streak status."""

from pydantic import BaseModel, Field


class MinigameScoreIn(BaseModel):
    """A finished play of one mini-game."""

    game: str = Field(min_length=1, max_length=64)
    score: int = Field(ge=0, le=1000)


class MinigameScoreResult(BaseModel):
    game: str
    xp_awarded: int
    first_play_today: bool
    total_xp: int | None
    level: int | None
    level_changed: bool
    streak_count: int


class MinigameInfo(BaseModel):
    key: str
    name: str
    played_today: bool
    max_xp: int


class MinigameStatusRead(BaseModel):
    games: list[MinigameInfo]
    streak_count: int
    streak_best: int
