// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * PlacingState — one finish-ranking entry, Colyseus-synced.
 *
 * Mirrors `Placing` from shared/race/types. Server populates the
 * `RaceRoomState.placings` array when the round transitions to
 * `finished`; clients render the results panel directly from it.
 */
import { Schema, type } from "@colyseus/schema"

export class PlacingState extends Schema {
  @type("string") racerId = ""
  @type("uint8") place = 0
  @type("boolean") finished = false
  @type("uint32") finishTimeMs = 0
  @type("number") distanceM = 0
}
