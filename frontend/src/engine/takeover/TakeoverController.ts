// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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

  // Saved sitting flag — used in `enter` to un-set the anim boolean so the
  // character stands up when takeover starts. No longer need originalPosition
  // or originalYaw; the server walks the character home on exit, so there's
  // nothing to locally "restore."
  private wasSitting = false

  // Seat interaction — E-key sit at nearby chairs
  private _sitting = false

  // Vehicle mount — when true, movement is delegated to VehicleController
  private _mounted = false

  // Jump
  private jumpProgress = -1

  // Inactivity
  private _inactivityTimer = 0

  // Door re-enable delay (prevents false trigger on spawn overlap)
  private doorEnableTimer: ReturnType<typeof setTimeout> | null = null

  // Emote — plays for EMOTE_DURATION then returns to idle
  private _emoteId: 0 | 1 | 2 = 0  // 0=none, 1=wave, 2=cheer
  private _emoteTimer = 0
  private static readonly EMOTE_DURATION = 2.0  // seconds

  // Scratch vector
  private readonly _dir = new pc.Vec3()

  // Internally-tracked yaw in degrees [-180, 180]. We CANNOT read yaw back
  // from the entity via `entity.getEulerAngles().y`: for rotations near ±180°
  // PlayCanvas's quat→euler decomposition returns the gimbal-flipped form
  // `(180, 0, 180)` for a pure 180° Y rotation, so `.y` reads as 0 even
  // though the character is visually rotated half around. Broadcasting that 0
  // made remote observers see position updates without rotation.
  private _yaw = 0

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

  /** Whether the player is currently sitting at a chair. */
  get isSitting(): boolean { return this._sitting }

  /** Whether the player is currently riding a vehicle. */
  get isMounted(): boolean { return this._mounted }
  set mounted(value: boolean) { this._mounted = value }

  /**
   * Teleport the character to a seat and play the sit animation.
   * Freezes movement and door detection while seated. Called from
   * GardenEngine when the player presses E near a chair.
   */
  sitAt(x: number, y: number, z: number, yaw: number): void {
    if (!this.entity) return
    this._sitting = true
    this.jumpProgress = -1
    this.entity.setPosition(x, y, z)
    this.entity.setEulerAngles(0, yaw, 0)
    this._yaw = yaw
    this.entity.anim?.setBoolean('jumping', false)
    this.entity.anim?.setBoolean('sitting', true)
    this.entity.anim?.setInteger('speed', 0)
    this.physics?.setDoorsEnabled(false)
    this._inactivityTimer = 0
  }

  /**
   * Stand up from a chair and resume movement. Clears the sit animation
   * and re-enables door detection. Called from GardenEngine on E-key
   * or WASD while sitting.
   */
  standUp(): void {
    if (!this.entity || !this._sitting) return
    this._sitting = false
    this.entity.anim?.setBoolean('sitting', false)
    this.physics?.setDoorsEnabled(true)
    // Sync physics capsule to the seated position so movement resumes
    // from the chair, not from the last walked-to position.
    const pos = this.entity.getPosition()
    this.physics?.teleportPlayer(pos.x, pos.z)
  }

  /**
   * Play an emote animation (wave or cheer). Freezes movement for the
   * duration. Ignored if already sitting, mounted, or mid-emote.
   */
  playEmote(emoteId: 1 | 2): void {
    if (!this.entity || this._sitting || this._mounted || this._emoteId !== 0) return
    this._emoteId = emoteId
    this._emoteTimer = TakeoverController.EMOTE_DURATION
    this.entity.anim?.setInteger('emote', emoteId)
    this.entity.anim?.setInteger('speed', 0)
    this._inactivityTimer = 0
  }

  /** Whether an emote is currently playing. */
  get isEmoting(): boolean { return this._emoteId !== 0 }

  /** Door collision from last physics step. Consumed on read. */
  consumeDoorHit(): DoorCollision | null {
    return this.physics?.consumeDoorHit() ?? null
  }

  /** Current world position (for camera follow). */
  getPosition(): pc.Vec3 {
    return this.entity?.getPosition() ?? pc.Vec3.ZERO
  }

  /** Current yaw in degrees (for multiplayer broadcast). Returns the
   *  controller's own tracked value, NOT `entity.getEulerAngles().y` —
   *  that path gimbal-flips at ±180° yaw and silently broadcasts 0. */
  getYaw(): number {
    return this._yaw
  }

  /**
   * Current animation state as a server-recognized string.
   * Maps the anim component's `speed` (0/1/2) + `jumping` into one of
   * OrgRoom's VALID_ANIMS: idle | walk | sprint | jump.
   */
  getAnimState(): string {
    if (this._sitting) return "sit"
    if (this._emoteId === 1) return "wave"
    if (this._emoteId === 2) return "cheer"
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
    this.wasSitting = entity.anim?.getBoolean('sitting') ?? false
    // Seed _yaw from the entity's current world rotation using the
    // quaternion directly — not getEulerAngles().y, which gimbal-flips.
    // For a pure Y rotation, yaw = 2 * atan2(q.y, q.w).
    const q = entity.getRotation()
    this._yaw = 2 * Math.atan2(q.y, q.w) * pc.math.RAD_TO_DEG

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

    // ─── Mounted: movement delegated to VehicleController ────────
    if (this._mounted) {
      // VehicleController.update() is called by GardenEngine directly.
      // We only track inactivity here.
      const anyInput =
        this.input.isPressed(pc.KEY_W) || this.input.isPressed(pc.KEY_S) ||
        this.input.isPressed(pc.KEY_A) || this.input.isPressed(pc.KEY_D)
      if (anyInput) this._inactivityTimer = 0
      else this._inactivityTimer += dt
      return
    }

    // ─── Emote: freeze movement while animation plays ─────────────
    if (this._emoteId !== 0) {
      this._emoteTimer -= dt
      if (this._emoteTimer <= 0) {
        this._emoteId = 0
        this._emoteTimer = 0
        this.entity.anim?.setInteger('emote', 0)
      }
      this._inactivityTimer = 0
      return  // skip physics + movement while emoting
    }

    // ─── Sitting: freeze all movement, WASD auto-stands ──────────
    if (this._sitting) {
      const anyMove =
        this.input.isPressed(pc.KEY_W) || this.input.isPressed(pc.KEY_UP) ||
        this.input.isPressed(pc.KEY_S) || this.input.isPressed(pc.KEY_DOWN) ||
        this.input.isPressed(pc.KEY_A) || this.input.isPressed(pc.KEY_LEFT) ||
        this.input.isPressed(pc.KEY_D) || this.input.isPressed(pc.KEY_RIGHT)
      if (anyMove) this.standUp()
      else this._inactivityTimer += dt
      return  // skip physics + movement while seated
    }

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

      // Face movement direction. Track yaw internally — the entity's
      // euler is only ever WRITTEN by us here; reading it back via
      // getEulerAngles().y can gimbal-flip at ±180° and broadcast 0.
      this._yaw = Math.atan2(wx, wz) * pc.math.RAD_TO_DEG
      this.entity.setEulerAngles(0, this._yaw, 0)
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

  /**
   * Exit takeover — clean up controller state only. Does NOT restore the
   * entity's position/yaw/anim locally because the server-driven snapshot
   * stream is now authoritative and will take over within a tick. Snapping
   * back to `originalPosition` here would create a visible teleport followed
   * by another teleport when the first snapshot update arrives — and during
   * the brief gap, the entity's animState/position would be stale.
   *
   * The server's `handleTakeoverEnd` starts a walkHome on its side; each
   * subsequent snapshot update advances `character.entity` naturally.
   */
  exit(): void {
    if (!this.entity) return

    if (this.doorEnableTimer !== null) {
      clearTimeout(this.doorEnableTimer)
      this.doorEnableTimer = null
    }

    this.jumpProgress = -1
    this._sitting = false
    this._mounted = false

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
