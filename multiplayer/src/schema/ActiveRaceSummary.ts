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
 * ActiveRaceSummary — compact "there's a race happening" row that the
 * OrgRoom publishes so garden viewers can see who's racing and click
 * through to `/raceview/{roomId}` without joining the race room first.
 *
 * Intentionally thin — racer-by-racer physics lives on the RaceRoom.
 */
import { ArraySchema, Schema, type } from "@colyseus/schema"

export class ActiveRaceSummary extends Schema {
  @type("string") roomId = ""
  @type("string") hostUserId = ""
  @type("string") hostName = ""
  @type("uint16") distanceM = 0
  /** Current phase — lets the watch banner say "Alice is racing" vs "lobby". */
  @type("string") phase = "lobby"
  @type("uint8") racerCount = 0
  /**
   * Host + invitees. The watch banner uses this to hide itself for anyone
   * already in the race — a racer seeing a "Watch" button pointing at their
   * own room is confusing.
   */
  @type(["string"]) participantUserIds = new ArraySchema<string>()
}
