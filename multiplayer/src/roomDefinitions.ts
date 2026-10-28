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
 * Colyseus room registrations, kept apart from `main.ts` (which starts the
 * server on import) so the matchmaking rules can be tested.
 *
 * Clients reach the shared rooms with `joinOrCreate`, which joins ANY open
 * room of that name unless the handler filters on a creation option. The
 * shared rooms are therefore partitioned by the option that names their
 * owner: one org room, coffee bar and cafeteria per `orgId`, one house room
 * per `ownerId`. Race, mini-game and backlash rooms are created per match
 * and joined by id, so they need no filter.
 */
import { defineRoom } from "colyseus"
import { OrgRoom } from "./rooms/OrgRoom"
import { HouseRoom } from "./rooms/HouseRoom"
import { CoffeeBarRoom } from "./rooms/CoffeeBarRoom"
import { CafeteriaRoom } from "./rooms/CafeteriaRoom"
import { RaceRoom } from "./rooms/RaceRoom"
import { MinigameRoom } from "./rooms/MinigameRoom"
import { BacklashRoom } from "./rooms/BacklashRoom"

export const roomDefinitions = {
  org: defineRoom(OrgRoom).filterBy(["orgId"]),
  house: defineRoom(HouseRoom).filterBy(["ownerId"]),
  coffeebar: defineRoom(CoffeeBarRoom).filterBy(["orgId"]),
  cafeteria: defineRoom(CafeteriaRoom).filterBy(["orgId"]),
  race: defineRoom(RaceRoom),
  minigame: defineRoom(MinigameRoom),
  backlash: defineRoom(BacklashRoom),
}
