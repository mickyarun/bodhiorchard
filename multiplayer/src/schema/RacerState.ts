// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RacerState — one participant's schema-synced slice of a race room.
 *
 * Mirrors `Racer` from shared/race/RacePhysics in fields the client needs
 * to render the avatar + HUD slot each frame. Server drives all mutation
 * via `RacePhysics.tick`; the client observes via Colyseus state.
 */
import { Schema, type } from "@colyseus/schema"

export class RacerState extends Schema {
  @type("string") id = ""
  @type("string") userId = ""
  @type("string") name = ""
  /** Encoded CharacterConfig string — parsed client-side for the avatar. */
  @type("string") characterModel = ""
  /** 0-based lane index — the scene uses this to pick the avatar's Z. */
  @type("uint8") laneIndex = 0
  @type("number") positionM = 0
  @type("number") velocityMps = 0
  @type("boolean") finished = false
  @type("uint32") finishTimeMs = 0
  @type("boolean") isMoving = false
  @type("uint32") sprintUntilMs = 0
  @type("boolean") connected = false
}
