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

export class OrgRoomState extends Schema {
  @type("string") version = "1.0.0"
  @type("string") orgId = ""

  /** All members keyed by user_id. */
  @type({ map: MemberState }) members = new MapSchema<MemberState>()

  /** All active agent robots keyed by agentId (typically task_id). */
  @type({ map: AgentState }) agents = new MapSchema<AgentState>()
}
