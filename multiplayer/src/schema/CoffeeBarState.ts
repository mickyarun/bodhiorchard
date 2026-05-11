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
 * CoffeeBarState — shared state for the coffee bar interior.
 *
 * One CoffeeBarRoom per org. Holds:
 *   - players: visitors currently inside (re-uses PlayerState like HouseRoom)
 *   - queue:   userIds waiting for the machine in FIFO order
 *   - active:  the single in-progress order (phase-driven)
 *
 * The server owns all phase transitions; clients render from state only.
 */
import { Schema, MapSchema, ArraySchema, type } from "@colyseus/schema"
import { PlayerState } from "./PlayerState"

/**
 * Phase values kept as plain strings rather than an enum so the schema stays
 * compatible with Colyseus's JSON state sync and existing clients reading via
 * typeof state.active.phase === "string".
 *
 * idle        — nobody being served; queue drains into approaching on next tick
 * approaching — character is walking from queue position to the machine
 * brewing     — character stands at machine; brew animation plays
 * dispensed   — drink is ready; shows Refreshed label; waits for client ack
 */
export type CoffeeActionPhase =
  | "idle"
  | "approaching"
  | "brewing"
  | "dispensed"

export class CoffeeAction extends Schema {
  /** Who is being served. Real player: userId. NPC: "npc:{memberId}". */
  @type("string") userId: string = ""
  @type("string") drink: string = ""
  @type("string") phase: string = "idle"
  /** Server Date.now() at the moment phase was entered. */
  @type("number") phaseStartMs: number = 0
}

export class CoffeeBarState extends Schema {
  @type("string") version = "1.0.0"
  @type("string") orgId = ""

  /** Visitors currently inside the coffee bar. Keyed by sessionId. */
  @type({ map: PlayerState }) players = new MapSchema<PlayerState>()

  /** Waiting line. Entries are userIds (or "npc:{id}"), FIFO order. */
  @type(["string"]) queue = new ArraySchema<string>()

  @type(CoffeeAction) active = new CoffeeAction()
}
