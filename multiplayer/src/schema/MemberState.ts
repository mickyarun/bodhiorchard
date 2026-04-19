// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * MemberState — server-authoritative state for one org member.
 *
 * Position (x, y, z), facing direction (yaw), and animation state
 * are synced to all clients in the OrgRoom at ~20Hz.
 *
 * Activity label shows what the member is currently doing (e.g., "Coding...")
 * when driven by dev_activity events. Empty string = no label.
 *
 * takeoverSessionId: when non-empty, this member is being controlled by a
 * real player client. The server suspends its NPC simulation for this member
 * until takeover ends.
 *
 * locationContext identifies where the member currently is:
 *   - "garden" → walking around or at an unknown location
 *   - "house_{memberId}" → inside their own house (desk or bed)
 *   - "break_{zone}" → at a break zone (coffee_bar | pool_resort)
 *   - "tree_{repoName}" → at a repo tree (dev activity, Phase 5)
 */
import { Schema, type } from "@colyseus/schema"

export class MemberState extends Schema {
  // Identity
  @type("string") userId = ""
  @type("string") name = ""
  @type("string") characterModel = ""
  @type("number") level = 0
  @type("string") levelName = ""

  // Presence (set from dashboard data snapshot)
  @type("string") presence = "active"  // active | on_break | at_home

  // Position (updated by server sim or takeover messages)
  @type("number") x = 0
  @type("number") y = 0
  @type("number") z = 0
  @type("number") yaw = 0
  @type("string") animState = "idle"  // idle | walk | sit | sleep | sprint | jump

  // Activity label (dev_activity)
  @type("string") labelName = ""
  @type("string") labelMessage = ""

  // House tier (1=Hut, 2=Cottage, 3=Mansion)
  @type("number") houseLevel = 1

  // Vehicle (empty = on foot, "horse" = riding)
  @type("string") vehicleId = ""

  // Takeover — when set, this member is player-controlled (server pauses NPC sim)
  @type("string") takeoverSessionId = ""

  // Location context (for interior visibility + picking)
  @type("string") locationContext = "garden"
}
