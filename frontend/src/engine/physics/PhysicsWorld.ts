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
 * PhysicsWorld — Rapier 3D physics wrapper.
 *
 * Collision approach:
 *   - Walls: static cuboids → character can't pass through
 *   - Doors: static cuboids (thin) → character bumps into them,
 *     we detect the collision and trigger scene transition
 *   - Character: kinematic + capsule + character controller
 *
 * Door detection: after computeColliderMovement(), check
 * numComputedCollisions() — if any collision is with a door
 * collider, fire a door event.
 */
import type RAPIER_NS from '@dimforge/rapier3d'

let R: typeof RAPIER_NS

// ─── Public Types ────────────────────────────

export interface DoorCollision {
  doorId: string
}

export class PhysicsWorld {
  private world: RAPIER_NS.World
  private cc: RAPIER_NS.KinematicCharacterController

  // Player
  private playerBody: RAPIER_NS.RigidBody | null = null
  private playerCollider: RAPIER_NS.Collider | null = null

  // Door colliders: handle → doorId
  private doorHandles = new Map<number, string>()

  // Door collision detected this frame
  private _doorHit: DoorCollision | null = null

  // Hard gate: when false, door detection is completely disabled.
  // Used by takeover/interior transitions to stop consuming hits during fades.
  private doorsEnabled = true

  // Cooldown gate: a future ms timestamp before which door hits are ignored.
  // Independent from `doorsEnabled` — `consumeDoorHit` checks both. See
  // `disableDoorsUntil` for the compose-without-coordination contract.
  private _doorsDisabledUntil = 0

  private constructor(world: RAPIER_NS.World) {
    this.world = world
    this.cc = world.createCharacterController(0.01)
    this.cc.setUp({ x: 0, y: 1, z: 0 })
    this.cc.setMaxSlopeClimbAngle(45 * Math.PI / 180)
  }

  static async create(gravity = { x: 0, y: -9.81, z: 0 }): Promise<PhysicsWorld> {
    R = await import('@dimforge/rapier3d')
    return new PhysicsWorld(new R.World(gravity))
  }

  // ─── Static Bodies (Walls, Ground) ─────────

  addStaticBox(x: number, y: number, z: number, halfW: number, halfH: number, halfD: number): RAPIER_NS.RigidBody {
    const body = this.world.createRigidBody(R.RigidBodyDesc.fixed().setTranslation(x, y, z))
    this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
    return body
  }

  addGround(y = -0.05, halfSize = 100): void {
    this.addStaticBox(0, y, 0, halfSize, 0.05, halfSize)
  }

  /**
   * Add a static box rotated around the Y axis.
   * Used for walls not axis-aligned with world XZ (e.g., rotated buildings, perimeter rings).
   */
  addStaticBoxRotated(
    x: number, y: number, z: number,
    halfW: number, halfH: number, halfD: number,
    yawRad: number,
  ): RAPIER_NS.RigidBody {
    // Y-axis rotation quaternion: (0, sin(yaw/2), 0, cos(yaw/2))
    const half = yawRad * 0.5
    const body = this.world.createRigidBody(
      R.RigidBodyDesc.fixed()
        .setTranslation(x, y, z)
        .setRotation({ x: 0, y: Math.sin(half), z: 0, w: Math.cos(half) }),
    )
    this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
    return body
  }

  /**
   * Remove a previously-added static body and its colliders.
   * Also clears any door-handle registrations for this body's colliders so
   * stale entries don't leak into `consumeDoorHit` after a rebuild.
   */
  removeBody(body: RAPIER_NS.RigidBody): void {
    const count = body.numColliders()
    for (let i = 0; i < count; i++) {
      const collider = body.collider(i)
      this.doorHandles.delete(collider.handle)
    }
    this.world.removeRigidBody(body)
  }

  // ─── Door Colliders ────────────────────────
  // A door is a thin static box in the door gap.
  // Character bumps into it → we detect the collision.

  addDoor(id: string, x: number, y: number, z: number, halfW: number, halfH: number, halfD: number): RAPIER_NS.RigidBody {
    const body = this.world.createRigidBody(R.RigidBodyDesc.fixed().setTranslation(x, y, z))
    const collider = this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
    this.doorHandles.set(collider.handle, id)
    return body
  }

  /**
   * Add a door collider rotated around the Y axis. Same shape as `addDoor`
   * but the cuboid is oriented so its thin face is parallel to the rotated
   * front wall — required for non-axis-aligned villages where an axis-
   * aligned door AABB would overlap an adjacent wall panel.
   */
  addDoorRotated(
    id: string,
    x: number, y: number, z: number,
    halfW: number, halfH: number, halfD: number,
    yawRad: number,
  ): RAPIER_NS.RigidBody {
    const half = yawRad * 0.5
    const body = this.world.createRigidBody(
      R.RigidBodyDesc.fixed()
        .setTranslation(x, y, z)
        .setRotation({ x: 0, y: Math.sin(half), z: 0, w: Math.cos(half) }),
    )
    const collider = this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
    this.doorHandles.set(collider.handle, id)
    return body
  }

  /**
   * Hard gate for door detection. `false` disables all door hits until
   * set back to `true`; also clears any pending hit. Use for long-lived
   * states (takeover setup, interior mode) where you control both edges
   * of the window. For short-lived cooldowns after a scene transition,
   * prefer `disableDoorsUntil` which is time-bounded and composes with
   * other callers.
   */
  setDoorsEnabled(enabled: boolean): void {
    this.doorsEnabled = enabled
    if (!enabled) this._doorHit = null
  }

  /**
   * Suppress door hit detection until the given absolute ms timestamp
   * (`Date.now() + N`). Forward-only — a later call with an earlier
   * timestamp never shrinks the window — so multiple scene-transition
   * callers can request their own cooldowns without coordinating.
   *
   * Composes cleanly with `setDoorsEnabled`: `consumeDoorHit` returns
   * `null` if EITHER the hard gate is false OR the cooldown is active.
   * Also clears any pending hit so the very next frame doesn't fire on
   * a stale collision detected before the cooldown was installed.
   */
  disableDoorsUntil(timestamp: number): void {
    this._doorsDisabledUntil = Math.max(this._doorsDisabledUntil, timestamp)
    this._doorHit = null
  }

  /**
   * Get door collision from last frame. Consumed on read.
   * Returns `null` if either the hard gate is false or the cooldown
   * window has not yet elapsed.
   */
  consumeDoorHit(): DoorCollision | null {
    if (!this.doorsEnabled) return null
    if (Date.now() < this._doorsDisabledUntil) return null
    const hit = this._doorHit
    this._doorHit = null
    return hit
  }

  // ─── Player ────────────────────────────────

  createPlayer(x: number, z: number, radius = 0.2, halfHeight = 0.35): void {
    const yCenter = halfHeight + radius
    this.playerBody = this.world.createRigidBody(
      R.RigidBodyDesc.kinematicPositionBased().setTranslation(x, yCenter, z),
    )
    this.playerCollider = this.world.createCollider(
      R.ColliderDesc.capsule(halfHeight, radius),
      this.playerBody,
    )
  }

  /**
   * Whether door-hit detection is currently active. False if either the
   * hard gate is off or a cooldown window is still in effect. Used by
   * `movePlayer` to skip populating `_doorHit` during suppression, so
   * stale hits never survive into the next active frame.
   */
  private get doorsActive(): boolean {
    return this.doorsEnabled && Date.now() >= this._doorsDisabledUntil
  }

  movePlayer(dx: number, dz: number): void {
    if (!this.playerCollider || !this.playerBody) return

    this.cc.computeColliderMovement(this.playerCollider, { x: dx, y: 0, z: dz })

    // Check if any collision was with a door collider
    if (this.doorsActive) {
      for (let i = 0; i < this.cc.numComputedCollisions(); i++) {
        const collision = this.cc.computedCollision(i)
        if (collision?.collider) {
          const doorId = this.doorHandles.get(collision.collider.handle)
          if (doorId) {
            this._doorHit = { doorId }
            break
          }
        }
      }
    }

    const m = this.cc.computedMovement()
    const pos = this.playerBody.translation()
    this.playerBody.setNextKinematicTranslation({
      x: pos.x + m.x, y: pos.y, z: pos.z + m.z,
    })
  }

  getPlayerPosition(): { x: number; y: number; z: number } {
    if (!this.playerBody) return { x: 0, y: 0, z: 0 }
    const t = this.playerBody.translation()
    return { x: t.x, y: t.y, z: t.z }
  }

  teleportPlayer(x: number, z: number): void {
    if (!this.playerBody) return
    const y = this.playerBody.translation().y
    this.playerBody.setTranslation({ x, y, z }, true)
  }

  /** Remove the player body + collider from the world (e.g., when exiting takeover). */
  destroyPlayer(): void {
    if (this.playerBody) {
      this.world.removeRigidBody(this.playerBody)
      this.playerBody = null
      this.playerCollider = null
    }
  }

  // ─── Step ──────────────────────────────────

  step(): void {
    this.world.step()
  }

  // ─── Debug Introspection ───────────────────

  /**
   * Return every rigid body currently in the world along with its primary
   * collider's half-extents, translation, and rotation. Used by debug overlays
   * to draw wireframe boxes matching the Rapier collision state.
   *
   * Only cuboid colliders are inspected (everything we add is a cuboid). Non-
   * cuboid shapes would return null halfExtents and callers should skip them.
   */
  forEachColliderBox(
    cb: (b: { x: number; y: number; z: number; halfW: number; halfH: number; halfD: number; yawRad: number; isDoor: boolean; isPlayer: boolean }) => void,
  ): void {
    this.world.forEachRigidBody((body) => {
      const count = body.numColliders()
      for (let i = 0; i < count; i++) {
        const collider = body.collider(i)
        const shape = collider.shape
        // Only cuboids (and capsules for player) — skip anything else
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const he = (shape as any).halfExtents as { x: number; y: number; z: number } | undefined
        if (!he) continue
        const t = body.translation()
        const r = body.rotation()
        // Extract yaw from quaternion (Y-axis only rotation)
        const yawRad = 2 * Math.atan2(r.y, r.w)
        cb({
          x: t.x, y: t.y, z: t.z,
          halfW: he.x, halfH: he.y, halfD: he.z,
          yawRad,
          isDoor: this.doorHandles.has(collider.handle),
          isPlayer: body === this.playerBody,
        })
      }
    })
  }

  // ─── Cleanup ───────────────────────────────

  destroy(): void {
    this.world.free()
  }
}
