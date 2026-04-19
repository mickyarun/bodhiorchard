// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * PlayerState — synchronized player data within a room.
 *
 * Position (x, z), facing direction (yaw), and animation state
 * are synced to all clients in the same room at ~20Hz.
 */
import { Schema, type } from "@colyseus/schema"

export class PlayerState extends Schema {
  @type("string") userId: string = ""
  @type("string") name: string = ""
  @type("string") characterModel: string = ""  // e.g. "kaykit:barbarian:FF6B35:2E4057:F4C28F"
  @type("number") x: number = 0
  @type("number") z: number = 0
  @type("number") yaw: number = 0
  @type("string") animState: string = "idle"  // idle | walk | sit | sleep
  @type("boolean") connected: boolean = true
}
