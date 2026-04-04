/**
 * TakeoverController — WASD movement controller for garden takeover mode.
 *
 * Drives an EXISTING character entity from CharacterSystem (not a new entity).
 * Uses the proven AABB slide-collision from CollisionSystem (same as interior).
 *
 * Features:
 *   - Walk (WASD/arrows), Sprint (Shift), Jump (Space)
 *   - AABB slide collision (buildings) + world boundary clamp
 *   - E-key door entry (shows prompt when near, enters on press)
 *   - Inactivity auto-revert to NPC mode
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'
import { tryMove, type CollisionBox } from '../housetest/CollisionSystem'

// ─── Movement ────────────────────────────────
const WALK_SPEED    = 3.0
const SPRINT_SPEED  = 6.0
const JUMP_HEIGHT   = 0.6
const JUMP_DURATION = 0.5

// ─── Door interaction ────────────────────────
const DOOR_PROMPT_DIST_SQ = 3.0 * 3.0  // show "Press E" prompt at this range
const DOOR_ENTER_DIST_SQ  = 2.0 * 2.0  // E-key activates at this range

// ─── Inactivity ──────────────────────────────
const INACTIVITY_TIMEOUT = 120
const INACTIVITY_WARNING = 90

/** House door for E-key interior entry. */
export interface HouseDoor {
  memberId: string
  x: number
  z: number
  name: string
}

export class TakeoverController {
  private input: InputManager
  private entity: pc.Entity | null = null

  // Saved state for restoration
  private originalPosition = new pc.Vec3()
  private originalYaw = 0
  private wasSitting = false

  // Jump
  private jumpProgress = -1

  // Inactivity
  private _inactivityTimer = 0

  // World boundary
  private worldRadius = 60

  // AABB collision boxes (buildings, houses)
  private collisionBoxes: CollisionBox[] = []

  // House doors (E-key entry)
  private houseDoors: HouseDoor[] = []
  private _triggeredDoor: HouseDoor | null = null
  private _nearDoor: HouseDoor | null = null  // for UI prompt

  // Scratch vectors (avoid per-frame allocation)
  private readonly _dir  = new pc.Vec3()
  private readonly _next = new pc.Vec3()

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

  /** Door triggered by E-key this frame. Consumed on read. */
  consumeTriggeredDoor(): HouseDoor | null {
    const door = this._triggeredDoor
    this._triggeredDoor = null
    return door
  }

  /** Door the player is near (for UI prompt). */
  get nearDoor(): HouseDoor | null { return this._nearDoor }

  /** Current world position (for camera follow). */
  getPosition(): pc.Vec3 {
    return this.entity?.getPosition() ?? pc.Vec3.ZERO
  }

  // ─── Configuration ─────────────────────────

  setWorldRadius(radius: number): void { this.worldRadius = radius }
  setCollisionBoxes(boxes: CollisionBox[]): void { this.collisionBoxes = boxes }
  setHouseDoors(doors: HouseDoor[]): void { this.houseDoors = doors }

  // ─── Lifecycle ─────────────────────────────

  /** Enter takeover — save entity state, stand up. */
  enter(entity: pc.Entity): void {
    this.entity = entity
    const pos = entity.getPosition()
    this.originalPosition.copy(pos)
    this.originalYaw = entity.getEulerAngles().y
    this.wasSitting = entity.anim?.getBoolean('sitting') ?? false

    if (this.wasSitting) entity.anim?.setBoolean('sitting', false)
    entity.anim?.setInteger('speed', 0)

    this.jumpProgress = -1
    this._inactivityTimer = 0
    this._triggeredDoor = null
    this._nearDoor = null
  }

  /** Per-frame update. */
  update(dt: number, camYaw: number): void {
    if (!this.entity) return

    // Read one-shot inputs ONCE at top of frame (prevents consumption issues)
    const ePressed = this.input.wasPressed(pc.KEY_E)
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
    if (moving || spacePressed || ePressed || sprinting) {
      this._inactivityTimer = 0
    } else {
      this._inactivityTimer += dt
    }

    // ─── Jump ──────────────────────────────
    if (spacePressed && this.jumpProgress < 0) {
      this.jumpProgress = 0
      anim?.setBoolean('jumping', true)
    }

    if (this.jumpProgress >= 0) {
      this.jumpProgress += dt / JUMP_DURATION
      if (this.jumpProgress >= 1) {
        this.jumpProgress = -1
        anim?.setBoolean('jumping', false)
        const p = this.entity.getPosition()
        this.entity.setPosition(p.x, 0, p.z)
      } else {
        const jumpY = Math.sin(this.jumpProgress * Math.PI) * JUMP_HEIGHT
        const p = this.entity.getPosition()
        this.entity.setPosition(p.x, jumpY, p.z)
      }
    }

    // ─── Movement with AABB collision ──────
    if (moving) {
      dir.normalize()
      const sinA = Math.sin(camYaw * pc.math.DEG_TO_RAD)
      const cosA = Math.cos(camYaw * pc.math.DEG_TO_RAD)
      const wx = dir.z * sinA + dir.x * cosA
      const wz = dir.z * cosA - dir.x * sinA

      const speed = sprinting ? SPRINT_SPEED : WALK_SPEED
      const dx = wx * speed * dt
      const dz = wz * speed * dt

      const pos = this.entity.getPosition()

      // AABB slide collision (same proven algorithm as interior PlayerController)
      const next = tryMove(pos, dx, dz, this.collisionBoxes, this._next)

      // World boundary clamp
      const distSq = next.x * next.x + next.z * next.z
      if (distSq > this.worldRadius * this.worldRadius && distSq > 0.001) {
        const dist = Math.sqrt(distSq)
        next.x = next.x / dist * this.worldRadius
        next.z = next.z / dist * this.worldRadius
      }

      // Preserve Y for jump arc
      const y = this.jumpProgress >= 0 ? this.entity.getPosition().y : 0
      this.entity.setPosition(next.x, y, next.z)

      // Face movement direction
      this.entity.setEulerAngles(0, Math.atan2(wx, wz) * pc.math.RAD_TO_DEG, 0)
    }

    // ─── Animation ────────────────────────
    if (anim) {
      anim.setInteger('speed', moving ? (sprinting ? 2 : 1) : 0)
    }

    // ─── Door interaction (E-key) ─────────
    this._nearDoor = null
    if (this.houseDoors.length > 0) {
      const pos = this.entity.getPosition()
      let closestDoor: HouseDoor | null = null
      let closestDistSq = DOOR_PROMPT_DIST_SQ

      for (const door of this.houseDoors) {
        const ddx = pos.x - door.x
        const ddz = pos.z - door.z
        const dsq = ddx * ddx + ddz * ddz
        if (dsq < closestDistSq) {
          closestDistSq = dsq
          closestDoor = door
        }
      }

      if (closestDoor) {
        this._nearDoor = closestDoor
        // E-key pressed while close enough → trigger entry
        if (ePressed && closestDistSq < DOOR_ENTER_DIST_SQ) {
          this._triggeredDoor = closestDoor
        }
      }
    }
  }

  /** Exit takeover — restore entity to original state. */
  exit(): void {
    if (!this.entity) return
    this.jumpProgress = -1

    this.entity.setPosition(this.originalPosition.x, 0, this.originalPosition.z)
    this.entity.setEulerAngles(0, this.originalYaw, 0)

    const anim = this.entity.anim
    if (anim) {
      anim.setInteger('speed', 0)
      anim.setBoolean('jumping', false)
      if (this.wasSitting) anim.setBoolean('sitting', true)
    }

    this.entity = null
    this._inactivityTimer = 0
    this._triggeredDoor = null
    this._nearDoor = null
  }
}
