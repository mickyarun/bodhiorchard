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
 * DoorTrigger — proximity-based door zone detection.
 *
 * Two separate trigger circles: one on the exterior side of the door
 * (fires onEnter) and one on the interior side (fires onExit).
 * A 1.5s cooldown prevents re-triggering during the fade animation.
 *
 * Note: If this demo is integrated with Ammo.js physics in the future,
 * replace with PlayCanvas CollisionComponent trigger volumes for cleaner
 * event-driven detection.
 */
import * as pc from 'playcanvas'
import { getHouseTierGeometry } from '@shared/world/HouseTiers'

/**
 * Default door trigger centres derived from tier 1's authoritative geometry.
 * `setDoorPosition` is the live path; these defaults are used only before
 * the first `setDoorPosition` call (scene boot), so deriving them avoids a
 * hardcoded 4×4 assumption rotting if tier 1 changes.
 */
const TIER1 = getHouseTierGeometry(1)
const DEFAULT_DOOR_X = TIER1.doorIndex + 0.5
const DEFAULT_FRONT_Z = TIER1.depth
const DEFAULT_ENTRY = new pc.Vec3(DEFAULT_DOOR_X, 0, DEFAULT_FRONT_Z + 0.7)
const DEFAULT_EXIT  = new pc.Vec3(DEFAULT_DOOR_X, 0, DEFAULT_FRONT_Z - 0.2)
const TRIGGER_RADIUS = 0.7
const COOLDOWN_MS = 1500

function dist2D(a: pc.Vec3, b: pc.Vec3): number {
  const dx = a.x - b.x
  const dz = a.z - b.z
  return Math.sqrt(dx * dx + dz * dz)
}

export class DoorTrigger {
  private onEnterCb:    (() => void) | null = null
  private onExitCb:     (() => void) | null = null
  private cooldown      = false
  private cooldownTimer: ReturnType<typeof setTimeout> | null = null
  private scene: 'exterior' | 'interior' = 'exterior'
  private entryCenter = DEFAULT_ENTRY.clone()
  private exitCenter  = DEFAULT_EXIT.clone()

  onEnter(fn: () => void): void { this.onEnterCb = fn }
  onExit(fn: () => void):  void { this.onExitCb  = fn }

  setScene(s: 'exterior' | 'interior'): void { this.scene = s }

  /** Update door position for tier-specific room sizes. */
  setDoorPosition(doorX: number, frontZ: number): void {
    this.entryCenter.set(doorX, 0, frontZ + 0.7)
    this.exitCenter.set(doorX, 0, frontZ - 0.2)
  }

  destroy(): void {
    if (this.cooldownTimer !== null) clearTimeout(this.cooldownTimer)
  }

  /** Call each frame with the player's world position. */
  update(playerPos: pc.Vec3): void {
    if (this.cooldown) return

    if (this.scene === 'exterior') {
      const d = dist2D(playerPos, this.entryCenter)
      if (d < TRIGGER_RADIUS) {
        this.fireCooldown()
        this.onEnterCb?.()
      }
    } else {
      const d = dist2D(playerPos, this.exitCenter)
      if (d < TRIGGER_RADIUS) {
        this.fireCooldown()
        this.onExitCb?.()
      }
    }
  }

  private fireCooldown(): void {
    this.cooldown = true
    this.cooldownTimer = setTimeout(() => { this.cooldown = false }, COOLDOWN_MS)
  }
}
