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

import { Schema, type } from "@colyseus/schema"

/**
 * Authoritative state for one solo mini-game session.
 *
 * Deliberately thin: a solo game has a single viewer, so there is no shared
 * state to reconcile. The running `score` is the only value the client must
 * trust (it is computed by the server, never reported by the client), and
 * everything game-specific — the firefly sequence, the fishing zone, the mote
 * field — flows over discrete messages instead of synced schema.
 */
export class MinigameRoomState extends Schema {
  @type("string") game = ""
  @type("string") userId = ""
  @type("string") orgId = ""
  /** "playing" | "finished" */
  @type("string") phase = "playing"
  /** Server-computed running score (also the final score once finished). */
  @type("uint16") score = 0
  /** Round/level/cast counter for display (game-specific meaning). */
  @type("uint16") round = 0
}
