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
  private doorsEnabled = true

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

  addStaticBox(x: number, y: number, z: number, halfW: number, halfH: number, halfD: number): void {
    const body = this.world.createRigidBody(R.RigidBodyDesc.fixed().setTranslation(x, y, z))
    this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
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
  ): void {
    // Y-axis rotation quaternion: (0, sin(yaw/2), 0, cos(yaw/2))
    const half = yawRad * 0.5
    const body = this.world.createRigidBody(
      R.RigidBodyDesc.fixed()
        .setTranslation(x, y, z)
        .setRotation({ x: 0, y: Math.sin(half), z: 0, w: Math.cos(half) }),
    )
    this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
  }

  // ─── Door Colliders ────────────────────────
  // A door is a thin static box in the door gap.
  // Character bumps into it → we detect the collision.

  addDoor(id: string, x: number, y: number, z: number, halfW: number, halfH: number, halfD: number): void {
    const body = this.world.createRigidBody(R.RigidBodyDesc.fixed().setTranslation(x, y, z))
    const collider = this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
    this.doorHandles.set(collider.handle, id)
  }

  setDoorsEnabled(enabled: boolean): void {
    this.doorsEnabled = enabled
    if (!enabled) this._doorHit = null
  }

  /** Get door collision from last frame. Consumed on read. */
  consumeDoorHit(): DoorCollision | null {
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

  movePlayer(dx: number, dz: number): void {
    if (!this.playerCollider || !this.playerBody) return

    this.cc.computeColliderMovement(this.playerCollider, { x: dx, y: 0, z: dz })

    // Check if any collision was with a door collider
    if (this.doorsEnabled) {
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

  // ─── Cleanup ───────────────────────────────

  destroy(): void {
    this.world.free()
  }
}
