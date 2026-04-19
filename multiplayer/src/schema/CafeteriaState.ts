// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
