/**
 * PhysicsWorld — Rapier 3D physics wrapper for the garden engine.
 *
 * All collision is handled by Rapier:
 *   - Static cuboids for walls/buildings (character can't pass through)
 *   - Sensor cuboids for door triggers (character passes through, fires events)
 *   - KinematicCharacterController for player movement (auto wall-sliding)
 *
 * Door detection: sensors are real Rapier colliders with `.setSensor(true)`.
 * After each `world.step()`, we use `world.intersectionsWith()` to check
 * which sensors the player currently overlaps. Enter/exit events are derived
 * by comparing with the previous frame.
 */
import type RAPIER_NS from '@dimforge/rapier3d'

// Set by PhysicsWorld.create() before any instance method is called.
let R: typeof RAPIER_NS

// ─── Public Types ────────────────────────────

export interface SensorEvent {
  type: 'enter' | 'exit'
  sensorId: string
}

// ─── Internal ────────────────────────────────

interface SensorRecord {
  id: string
  handle: number  // Rapier collider handle
}

export class PhysicsWorld {
  private world: RAPIER_NS.World
  private cc: RAPIER_NS.KinematicCharacterController

  // Player
  private playerBody: RAPIER_NS.RigidBody | null = null
  private playerCollider: RAPIER_NS.Collider | null = null

  // Sensors
  private sensors: SensorRecord[] = []
  private handleToId = new Map<number, string>()  // fast reverse lookup
  private activeSensors = new Set<string>()
  private pendingEvents: SensorEvent[] = []
  private sensorsEnabled = true

  private constructor(world: RAPIER_NS.World) {
    this.world = world
    this.cc = world.createCharacterController(0.02)
    this.cc.setUp({ x: 0, y: 1, z: 0 })
    this.cc.enableAutostep(0.3, 0.1, true)
    this.cc.enableSnapToGround(0.3)
    this.cc.setMaxSlopeClimbAngle(45 * Math.PI / 180)
  }

  static async create(gravity = { x: 0, y: -9.81, z: 0 }): Promise<PhysicsWorld> {
    R = await import('@dimforge/rapier3d')
    const world = new R.World(gravity)
    return new PhysicsWorld(world)
  }

  // ─── Static Bodies (Walls, Ground) ─────────

  /** Add a static box. Position is the CENTER. */
  addStaticBox(
    x: number, y: number, z: number,
    halfW: number, halfH: number, halfD: number,
  ): void {
    const body = this.world.createRigidBody(
      R.RigidBodyDesc.fixed().setTranslation(x, y, z),
    )
    this.world.createCollider(R.ColliderDesc.cuboid(halfW, halfH, halfD), body)
  }

  /** Add a ground plane. */
  addGround(y = -0.05, halfSize = 100): void {
    this.addStaticBox(0, y, 0, halfSize, 0.05, halfSize)
  }

  // ─── Sensors (Door Triggers, Zones) ────────

  /**
   * Add a Rapier sensor collider (trigger volume — no physical blocking).
   * The player can walk through it; an event fires on enter/exit.
   */
  addSensor(
    id: string,
    x: number, y: number, z: number,
    halfW: number, halfH: number, halfD: number,
  ): void {
    const body = this.world.createRigidBody(
      R.RigidBodyDesc.fixed().setTranslation(x, y, z),
    )
    const collider = this.world.createCollider(
      R.ColliderDesc.cuboid(halfW, halfH, halfD).setSensor(true),
      body,
    )
    this.sensors.push({ id, handle: collider.handle })
    this.handleToId.set(collider.handle, id)
  }

  setSensorsEnabled(enabled: boolean): void {
    this.sensorsEnabled = enabled
    if (!enabled) {
      this.activeSensors.clear()
      this.pendingEvents = []
    }
  }

  // ─── Player ────────────────────────────────

  /** Create kinematic player body with capsule collider. */
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

  /** Move player via character controller (handles wall sliding). */
  movePlayer(dx: number, dz: number): void {
    if (!this.playerCollider || !this.playerBody) return
    this.cc.computeColliderMovement(this.playerCollider, { x: dx, y: 0, z: dz })
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

  // ─── Step + Events ─────────────────────────

  step(): void {
    this.world.step()
    this.detectSensorOverlaps()
  }

  consumeEvents(): SensorEvent[] {
    const e = this.pendingEvents
    this.pendingEvents = []
    return e
  }

  // ─── Cleanup ───────────────────────────────

  destroy(): void {
    this.world.free()
  }

  // ─── Internal: Sensor Detection ────────────

  /**
   * After world.step(), check which sensors the player overlaps.
   * Uses world.intersectionsWith() — Rapier's built-in broadphase query.
   * Compares with previous frame to emit enter/exit events.
   */
  private detectSensorOverlaps(): void {
    if (!this.sensorsEnabled || !this.playerCollider) return

    const nowActive = new Set<string>()

    // Rapier intersectionsWith: iterates all colliders overlapping the given one
    this.world.intersectionsWith(this.playerCollider, (otherCollider) => {
      const id = this.handleToId.get(otherCollider.handle)
      if (id) nowActive.add(id)
      return true  // continue iterating
    })

    // Diff with previous frame → enter/exit events
    for (const id of nowActive) {
      if (!this.activeSensors.has(id)) {
        this.pendingEvents.push({ type: 'enter', sensorId: id })
      }
    }
    for (const id of this.activeSensors) {
      if (!nowActive.has(id)) {
        this.pendingEvents.push({ type: 'exit', sensorId: id })
      }
    }
    this.activeSensors = nowActive
  }
}
