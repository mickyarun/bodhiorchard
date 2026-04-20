// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * OrgRoomState — full server-authoritative state for one org's 3D world.
 *
 * Contains all members (NPCs + player-controlled) and all agent robots.
 * Every client viewing the same org joins the same room and receives
 * this state synced at the Colyseus default (~20Hz).
 *
 * Version field for client/server schema mismatch detection.
 */
import { Schema, MapSchema, type } from "@colyseus/schema"
import { MemberState } from "./MemberState"
import { AgentState } from "./AgentState"
import { ActiveRaceSummary } from "./ActiveRaceSummary"

export class OrgRoomState extends Schema {
  @type("string") version = "1.2.0"
  @type("string") orgId = ""

  /** All members keyed by user_id. */
  @type({ map: MemberState }) members = new MapSchema<MemberState>()

  /** All active agent robots keyed by agentId (typically task_id). */
  @type({ map: AgentState }) agents = new MapSchema<AgentState>()

  /**
   * Active races keyed by roomId. Garden viewers subscribe to this map
   * to render the "X is racing — Watch →" banner and click through to
   * `/raceview/{roomId}`. Entries are added by OrgRoom's `race_create`
   * handler and removed when the RaceRoom disposes.
   */
  @type({ map: ActiveRaceSummary }) activeRaces = new MapSchema<ActiveRaceSummary>()
}
