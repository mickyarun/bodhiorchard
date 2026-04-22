// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
