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
 * CafeteriaState — shared state for the cafeteria interior.
 *
 * One CafeteriaRoom per org. Mirrors CoffeeBarState with renamed fields
 * (drink → meal, brewing → cooking) so the frontend can consume a
 * parallel snapshot shape without special-casing either interior.
 */
import { Schema, MapSchema, ArraySchema, type } from "@colyseus/schema"
import { PlayerState } from "./PlayerState"

/**
 * idle        — nobody being served; queue drains into approaching on next tick
 * approaching — character walks from queue to the counter
 * cooking     — character stands at counter; meal is prepared
 * dispensed   — meal is ready; waits for client ack or timeout
 */
export type CafeteriaActionPhase =
  | "idle"
  | "approaching"
  | "cooking"
  | "dispensed"

export class CafeteriaAction extends Schema {
  @type("string") userId: string = ""
  @type("string") meal: string = ""
  @type("string") phase: string = "idle"
  /** Server Date.now() at the moment phase was entered. */
  @type("number") phaseStartMs: number = 0
}

export class CafeteriaState extends Schema {
  @type("string") version = "1.0.0"
  @type("string") orgId = ""

  /** Visitors currently inside the cafeteria. Keyed by sessionId. */
  @type({ map: PlayerState }) players = new MapSchema<PlayerState>()

  /** Waiting line. Entries are userIds, FIFO order. */
  @type(["string"]) queue = new ArraySchema<string>()

  @type(CafeteriaAction) active = new CafeteriaAction()
}
