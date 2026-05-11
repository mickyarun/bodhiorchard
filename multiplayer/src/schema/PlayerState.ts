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
