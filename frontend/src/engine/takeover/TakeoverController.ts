/**
 * TakeoverController — WASD movement controller for garden takeover mode.
 *
 * Drives an EXISTING character entity from CharacterSystem (not a new entity).
 * Uses Rapier physics via PhysicsWorld — collision, door detection, and
 * character controller wall-sliding are all handled by Rapier.
 *
 * Features:
 *   - Walk (WASD/arrows), Sprint (Shift), Jump (Space)
 *   - Door collision detection (bump into door → fire DoorCollision event)
 *   - Inactivity auto-revert to NPC mode
 *
 * This controller knows ONLY about PhysicsWorld and its character entity.
 * All scene/building knowledge lives in TakeoverPhysicsBuilder.
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'
import type { PhysicsWorld, DoorCollision } from '../physics'

// ─── Movement ────────────────────────────────
const WALK_SPEED    = 3.0
const SPRINT_SPEED  = 6.0
const JUMP_HEIGHT   = 0.6
const JUMP_DURATION = 0.5

// ─── Inactivity ──────────────────────────────
const INACTIVITY_TIMEOUT = 120
const INACTIVITY_WARNING = 90

export class TakeoverController {
  private input: InputManager
  private entity: pc.Entity | null = null
  private physics: PhysicsWorld | null = null

  // Saved state for restoration
  private originalPosition = new pc.Vec3()
  private originalYaw = 0
  private wasSitting = false

  // Jump
  private jumpProgress = -1

  // Inactivity
  private _inactivityTimer = 0

  // Door re-enable delay (prevents false trigger on spawn overlap)
  private doorEnableTimer: ReturnType<typeof setTimeout> | null = null

  // Scratch vector
  private readonly _dir = new pc.Vec3()

  constructor(input: InputManager) {
    this.input = input
  }

  // ─── Public getters ────────────────────────

  get inactivityTimer(): number { return this._inactivityTimer }
  get isInactive(): boolean { return this._inactivityTimer >= INACTIVITY_TIMEOUT }
  get showWarning(): boolean { return this._inactivityTimer >= INACTIVITY_WARNING }
  get warningSecondsLeft(): number {
    return Math.max(0, INACTIVITY_TIMEOUT - this._inactivityTimer)
  }

  /** Door collision from last physics step. Consumed on read. */
  consumeDoorHit(): DoorCollision | null {
    return this.physics?.consumeDoorHit() ?? null
  }

  /** Current world position (for camera follow). */
  getPosition(): pc.Vec3 {
    return this.entity?.getPosition() ?? pc.Vec3.ZERO
  }

  /** Current yaw in degrees (for multiplayer broadcast). */
  getYaw(): number {
    return this.entity?.getEulerAngles().y ?? 0
  }

  /**
   * Current animation state as a server-recognized string.
   * Maps the anim component's `speed` (0/1/2) + `jumping` into one of
   * OrgRoom's VALID_ANIMS: idle | walk | sprint | jump.
   */
  getAnimState(): string {
    const anim = this.entity?.anim
    if (!anim) return "idle"
    if (this.jumpProgress >= 0) return "jump"
    const speed = anim.getInteger("speed") ?? 0
    if (speed >= 2) return "sprint"
    if (speed >= 1) return "walk"
    return "idle"
  }

  // ─── Lifecycle ─────────────────────────────

  /**
   * Enter takeover — save entity state, create physics player, enable door detection.
   * @param entity - Existing character entity from CharacterSystem
   * @param physics - PhysicsWorld from SceneManager (must have walls/doors registered)
   */
  enter(entity: pc.Entity, physics: PhysicsWorld): void {
    this.entity = entity
    this.physics = physics

    const pos = entity.getPosition()
    this.originalPosition.copy(pos)
    this.originalYaw = entity.getEulerAngles().y
    this.wasSitting = entity.anim?.getBoolean('sitting') ?? false

    if (this.wasSitting) entity.anim?.setBoolean('sitting', false)
    entity.anim?.setInteger('speed', 0)

    // Create physics player at the character's current position
    physics.createPlayer(pos.x, pos.z)

    // Enable doors after a short delay — prevents false trigger if the
    // spawn position happens to overlap a door collider.
    physics.setDoorsEnabled(false)
    this.doorEnableTimer = setTimeout(() => {
      physics.setDoorsEnabled(true)
      this.doorEnableTimer = null
    }, 300)

    this.jumpProgress = -1
    this._inactivityTimer = 0
  }

  /** Per-frame update. */
  update(dt: number, camYaw: number): void {
    if (!this.entity || !this.physics) return

    const spacePressed = this.input.wasPressed(pc.KEY_SPACE)

    const anim = this.entity.anim
    const dir = this._dir
    dir.set(0, 0, 0)
    if (this.input.isPressed(pc.KEY_W) || this.input.isPressed(pc.KEY_UP))    dir.z -= 1
    if (this.input.isPressed(pc.KEY_S) || this.input.isPressed(pc.KEY_DOWN))  dir.z += 1
    if (this.input.isPressed(pc.KEY_A) || this.input.isPressed(pc.KEY_LEFT))  dir.x -= 1
    if (this.input.isPressed(pc.KEY_D) || this.input.isPressed(pc.KEY_RIGHT)) dir.x += 1

    const sprinting = this.input.isPressed(pc.KEY_SHIFT)
    const moving = dir.length() > 0

    // Inactivity tracking
    if (moving || spacePressed || sprinting) {
      this._inactivityTimer = 0
    } else {
      this._inactivityTimer += dt
    }

    // ─── Jump (visual arc, Y-only) ─────────
    if (spacePressed && this.jumpProgress < 0) {
      this.jumpProgress = 0
      anim?.setBoolean('jumping', true)
    }

    if (this.jumpProgress >= 0) {
      this.jumpProgress += dt / JUMP_DURATION
      if (this.jumpProgress >= 1) {
        this.jumpProgress = -1
        anim?.setBoolean('jumping', false)
      }
    }

    // ─── Movement via Rapier character controller ──
    if (moving) {
      dir.normalize()
      const sinA = Math.sin(camYaw * pc.math.DEG_TO_RAD)
      const cosA = Math.cos(camYaw * pc.math.DEG_TO_RAD)
      const wx = dir.z * sinA + dir.x * cosA
      const wz = dir.z * cosA - dir.x * sinA

      const speed = sprinting ? SPRINT_SPEED : WALK_SPEED
      this.physics.movePlayer(wx * speed * dt, wz * speed * dt)

      // Face movement direction
      this.entity.setEulerAngles(0, Math.atan2(wx, wz) * pc.math.RAD_TO_DEG, 0)
    }

    // Step physics + sync entity position
    this.physics.step()
    const p = this.physics.getPlayerPosition()
    const jumpY = this.jumpProgress >= 0 ? Math.sin(this.jumpProgress * Math.PI) * JUMP_HEIGHT : 0
    this.entity.setPosition(p.x, jumpY, p.z)

    // ─── Animation ────────────────────────
    if (anim) {
      anim.setInteger('speed', moving ? (sprinting ? 2 : 1) : 0)
    }
  }

  /** Exit takeover — restore entity, destroy physics player. */
  exit(): void {
    if (!this.entity) return

    if (this.doorEnableTimer !== null) {
      clearTimeout(this.doorEnableTimer)
      this.doorEnableTimer = null
    }

    this.jumpProgress = -1

    // Restore original position and yaw
    this.entity.setPosition(this.originalPosition.x, 0, this.originalPosition.z)
    this.entity.setEulerAngles(0, this.originalYaw, 0)

    // Restore animation state
    const anim = this.entity.anim
    if (anim) {
      anim.setInteger('speed', 0)
      anim.setBoolean('jumping', false)
      if (this.wasSitting) anim.setBoolean('sitting', true)
    }

    // Clean up physics player + disable door detection
    if (this.physics) {
      this.physics.setDoorsEnabled(false)
      this.physics.destroyPlayer()
    }

    this.entity = null
    this.physics = null
    this._inactivityTimer = 0
  }
}
