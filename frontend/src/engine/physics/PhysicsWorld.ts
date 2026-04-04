/**
 * PhysicsWorld — Rapier 3D physics wrapper for the garden engine.
 *
 * Provides a simple API for:
 *   - Static boxes (buildings, walls)
 *   - Sensor volumes (door triggers, zone detection)
 *   - Character controller (WASD movement with wall sliding)
 *   - Per-frame stepping + event reading
 *
 * Uses Rapier's built-in KinematicCharacterController for accurate
 * collision response — no manual AABB needed.
 */
import type RAPIER_NS from '@dimforge/rapier3d'

// Rapier WASM must be loaded async via dynamic import.
// Set by PhysicsWorld.create() before any other method is called.
let R: typeof RAPIER_NS

// ─── Sensor Event ────────────────────────────
export interface SensorEvent {
  type: 'enter' | 'exit'
  sensorId: string
}

// ─── Sensor Tracking ─────────────────────────
interface SensorInfo {
  id: string
  colliderHandle: number
}

export class PhysicsWorld {
  private world: RAPIER_NS.World
  private cc: RAPIER_NS.KinematicCharacterController

  // Player physics
  private playerBody: RAPIER_NS.RigidBody | null = null
  private playerCollider: RAPIER_NS.Collider | null = null

  // Sensor tracking
  private sensors: SensorInfo[] = []
  private activeSensors = new Set<string>()  // currently overlapping sensor IDs
  private pendingEvents: SensorEvent[] = []
  private sensorsEnabled = true

  private constructor(world: RAPIER_NS.World) {
    this.world = world

    // Character controller — handles wall sliding, autostep, snap-to-ground
    this.cc = world.createCharacterController(0.02) // 0.02 skin offset
    this.cc.setUp({ x: 0, y: 1, z: 0 })
    this.cc.enableAutostep(0.3, 0.1, true)
    this.cc.enableSnapToGround(0.3)
    this.cc.setMaxSlopeClimbAngle(45 * Math.PI / 180)
  }

  /**
   * Create a new PhysicsWorld. Must be called async (WASM loading).
   * @param gravity - Gravity vector. Use {x:0, y:0, z:0} for top-down games.
   */
  static async create(gravity = { x: 0, y: -9.81, z: 0 }): Promise<PhysicsWorld> {
    R = await import('@dimforge/rapier3d')
    const world = new R.World(gravity)
    return new PhysicsWorld(world)
  }

  // ─── Static Bodies (Buildings, Walls) ──────

  /**
   * Add a static box collider (wall, building, ground).
   * Position is the CENTER of the box.
   */
  addStaticBox(
    x: number, y: number, z: number,
    halfW: number, halfH: number, halfD: number,
  ): RAPIER_NS.Collider {
    const bodyDesc = R.RigidBodyDesc.fixed().setTranslation(x, y, z)
    const body = this.world.createRigidBody(bodyDesc)
    const colliderDesc = R.ColliderDesc.cuboid(halfW, halfH, halfD)
    return this.world.createCollider(colliderDesc, body)
  }

  /**
   * Add a ground plane (large static box).
   */
  addGround(y = -0.05, halfSize = 100): void {
    this.addStaticBox(0, y, 0, halfSize, 0.05, halfSize)
  }

  // ─── Sensor Volumes (Triggers) ─────────────

  /**
   * Add a sensor volume (trigger zone — no physical collision).
   * Fires events when the player enters/exits.
   */
  addSensor(
    id: string,
    x: number, y: number, z: number,
    halfW: number, halfH: number, halfD: number,
  ): void {
    const bodyDesc = R.RigidBodyDesc.fixed().setTranslation(x, y, z)
    const body = this.world.createRigidBody(bodyDesc)
    const colliderDesc = R.ColliderDesc.cuboid(halfW, halfH, halfD)
      .setSensor(true)
    const collider = this.world.createCollider(colliderDesc, body)
    this.sensors.push({ id, colliderHandle: collider.handle })
  }

  /** Enable/disable sensor event detection (disable during transitions). */
  setSensorsEnabled(enabled: boolean): void {
    this.sensorsEnabled = enabled
    if (!enabled) {
      this.activeSensors.clear()
      this.pendingEvents = []
    }
  }

  // ─── Player Character ──────────────────────

  /**
   * Create the player's physics body (kinematic + capsule collider).
   */
  createPlayer(x: number, z: number, radius = 0.2, halfHeight = 0.35): void {
    const bodyDesc = R.RigidBodyDesc.kinematicPositionBased()
      .setTranslation(x, halfHeight + radius, z)
    this.playerBody = this.world.createRigidBody(bodyDesc)
    const colliderDesc = R.ColliderDesc.capsule(halfHeight, radius)
    this.playerCollider = this.world.createCollider(colliderDesc, this.playerBody)
  }

  /**
   * Move the player using the character controller (handles wall sliding).
   * @param dx - desired X movement delta
   * @param dz - desired Z movement delta
   */
  movePlayer(dx: number, dz: number): void {
    if (!this.playerCollider || !this.playerBody) return

    const desired = { x: dx, y: 0, z: dz }
    this.cc.computeColliderMovement(this.playerCollider, desired)
    const corrected = this.cc.computedMovement()

    const pos = this.playerBody.translation()
    this.playerBody.setNextKinematicTranslation({
      x: pos.x + corrected.x,
      y: pos.y,  // keep current Y
      z: pos.z + corrected.z,
    })
  }

  /** Get the player's current world position. */
  getPlayerPosition(): { x: number; y: number; z: number } {
    if (!this.playerBody) return { x: 0, y: 0, z: 0 }
    const t = this.playerBody.translation()
    return { x: t.x, y: t.y, z: t.z }
  }

  /** Teleport the player to a new position (skips collision). */
  teleportPlayer(x: number, z: number): void {
    if (!this.playerBody) return
    const pos = this.playerBody.translation()
    this.playerBody.setTranslation({ x, y: pos.y, z }, true)
  }

  // ─── Simulation Step ───────────────────────

  /** Advance the physics simulation and process sensor events. */
  step(): void {
    this.world.step()
    this.processSensorEvents()
  }

  /** Get and clear pending sensor events since last call. */
  consumeEvents(): SensorEvent[] {
    const events = this.pendingEvents
    this.pendingEvents = []
    return events
  }

  // ─── Cleanup ───────────────────────────────

  destroy(): void {
    this.world.free()
  }

  // ─── Internal ──────────────────────────────

  private processSensorEvents(): void {
    if (!this.sensorsEnabled || !this.playerCollider) return

    const nowActive = new Set<string>()

    for (const sensor of this.sensors) {
      // Check if player intersects this sensor
      if (this.world.intersectionPair(this.playerCollider, this.world.getCollider(sensor.colliderHandle))) {
        nowActive.add(sensor.id)
      }
    }

    // Detect enter/exit events by comparing with previous frame
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
