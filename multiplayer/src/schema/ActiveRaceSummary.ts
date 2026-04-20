// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
