// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AgentState — server-authoritative state for one agent/robot character.
 *
 * Agents are spawned by skill_invoked events and despawned by skill_completed.
 * Walking and work animations are driven server-side and synced to clients.
 */
import { Schema, type } from "@colyseus/schema"

export class AgentState extends Schema {
  // Identity
  @type("string") agentId = ""           // task_id or unique key
  @type("string") skillSlug = ""
  @type("string") skillName = ""
  @type("string") actorName = ""

  // Target
  @type("string") repoName = ""          // current repo tree
  @type("number") budNumber = 0

  // Position
  @type("number") x = 0
  @type("number") y = 0
  @type("number") z = 0
  @type("number") yaw = 0

  // Animation state: spawning | walking | working | completing | fading | done
  @type("string") state = "spawning"
  @type("string") action = ""            // current work action (grab/spin/miniguns)

  // Label
  @type("string") message = ""           // e.g., "Analyzing code..."
}
