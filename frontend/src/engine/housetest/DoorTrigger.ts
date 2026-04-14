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

/** Default door positions for 4×4 room. */
const DEFAULT_ENTRY = new pc.Vec3(1.5, 0, 4.7)
const DEFAULT_EXIT  = new pc.Vec3(1.5, 0, 3.8)
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
