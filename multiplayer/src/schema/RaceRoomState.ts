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
 * RaceRoomState — server-authoritative state for one race-v2 room.
 *
 * Driven by `RaceRoom`: phase transitions, `racers` physics updates at
 * 20Hz during running, `placings` populated once on transition to
 * `finished`. Clients observe via Colyseus state sync; there is no
 * client→server message that mutates these fields directly — the only
 * inputs are `race_join`, `race_start`, `race_move`, `race_sprint_tap`.
 */
import { Schema, MapSchema, ArraySchema, type } from "@colyseus/schema"
import { RacerState } from "./RacerState"
import { PlacingState } from "./PlacingState"

export class RaceRoomState extends Schema {
  @type("string") version = "2.0.0"
  @type("string") orgId = ""
  @type("string") hostUserId = ""
  @type("string") hostName = ""
  @type("uint16") distanceM = 0

  /** `lobby` → `countdown` → `running` → `finished`. Matches shared RacePhase. */
  @type("string") phase = "lobby"
  /** Server wall-clock (ms) when the current phase started. */
  @type("uint64") phaseStartMs = 0
  /** Ms elapsed since the running phase started. Ticked each sim step. */
  @type("uint32") runningElapsedMs = 0

  /** Invited user ids (set at creation). Not all may join — "joined" is encoded in `racers`. */
  @type(["string"]) invitedUserIds = new ArraySchema<string>()

  /** Racers keyed by user id. Populated on `race_join` while `phase === 'lobby'`. */
  @type({ map: RacerState }) racers = new MapSchema<RacerState>()

  /** Final rankings — populated once when phase transitions to `finished`. */
  @type([PlacingState]) placings = new ArraySchema<PlacingState>()
}
