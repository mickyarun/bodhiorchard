/**
 * CameraController — game-like orbit camera.
 *
 * Controls (matches standard 3D game/viewer conventions):
 * - Left/right mouse drag: orbit (rotate view around target)
 * - Middle mouse drag: pan (shift target along ground plane)
 * - Scroll wheel: zoom in/out with smooth interpolation
 * - WASD / arrow keys: move target in camera-facing direction (FPS-style)
 * - Shift: sprint (2.5× speed)
 * - Double-click: fly camera to clicked ground position
 *
 * Starts near ground level for an immersive feel. Zooming out
 * smoothly transitions to bird's-eye overview.
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'
import { clamp, lerp, easeOutCubic } from '../utils/MathUtils'

export type CameraMode = 'overview' | 'play'

/** Snapshot of camera orbit state for save/restore across scene transitions. */
export interface CameraState {
  yaw: number
  pitch: number
  distance: number
  targetDistance: number
  target: pc.Vec3
  mode: CameraMode
}

export class CameraController {
  private cameraEntity!: pc.Entity
  private input!: InputManager
  private enabled = true

  // Orbit state — start near ground, looking across the garden
  private yaw = -20
  private pitch = 18
  private distance = 22
  private targetDistance = 22 // smooth zoom target

  // Limits
  private minDistance = 0.5 // close enough to enter buildings
  private maxDistance = 100
  private minPitch = -15 // allow looking slightly upward (inside buildings)
  private maxPitch = 85

  // World bounds — compact world with TILE_SIZE=1
  private readonly worldBounds = 60

  // Follow target
  private target = new pc.Vec3(0, 2, 0)
  private followTarget: pc.Entity | null = null
  private followLerp = 0.08

  // Smooth transition state
  private transitioning = false
  private transitionProgress = 0
  private transitionFrom = new pc.Vec3()
  private transitionTo = new pc.Vec3()
  private transitionTargetFrom = new pc.Vec3()
  private transitionTargetTo = new pc.Vec3()
  private readonly _scratchPos = new pc.Vec3()
  private readonly _scratchTgt = new pc.Vec3()

  // Orbit momentum — snappy damping for game feel
  private yawVelocity = 0
  private pitchVelocity = 0
  private readonly orbitDamping = 0.85
  private readonly momentumThreshold = 0.01

  mode: CameraMode = 'overview'

  // Input sensitivity — tuned for responsive game-like feel
  private orbitSensitivity = 0.3
  private zoomSensitivity = 1.0
  private panSpeed = 0.3
  private keyMoveSpeed = 15 // base units/sec for WASD
  private zoomLerp = 0.12

  // Scratch vectors for double-click raycasting
  private readonly _rayNear = new pc.Vec3()
  private readonly _rayFar = new pc.Vec3()

  // Controls help overlay
  private helpOverlay: HTMLElement | null = null

  init(cameraEntity: pc.Entity, input: InputManager): void {
    this.cameraEntity = cameraEntity
    this.input = input
    this.computeOrbitPosition()
  }

  /** Switch to play mode, following a target entity. */
  setFollowTarget(entity: pc.Entity): void {
    this.followTarget = entity
    this.mode = 'play'
    this.targetDistance = 12
    this.distance = this.targetDistance
    this.pitch = 20
    this.yaw = 0

    const pos = entity.getPosition()
    this.target.copy(pos)
    this.startTransitionToOrbit()
  }

  /** Return to overview mode — zooms to bird's-eye. */
  setOverviewMode(): void {
    this.followTarget = null
    this.mode = 'overview'
    this.targetDistance = 60
    this.pitch = 45

    const toTarget = new pc.Vec3(0, 0, 0)
    const pitchRad = this.pitch * pc.math.DEG_TO_RAD
    const yawRad = this.yaw * pc.math.DEG_TO_RAD
    const toPos = new pc.Vec3(
      toTarget.x + this.targetDistance * Math.cos(pitchRad) * Math.sin(yawRad),
      toTarget.y + this.targetDistance * Math.sin(pitchRad),
      toTarget.z + this.targetDistance * Math.cos(pitchRad) * Math.cos(yawRad),
    )
    this.startTransition(toPos, toTarget)
  }

  /** Disable camera updates — used when interior camera takes over. */
  disable(): void {
    this.enabled = false
    this.yawVelocity = 0
    this.pitchVelocity = 0
  }

  /** Re-enable camera updates after interior exit. */
  enable(): void {
    this.enabled = true
  }

  get isEnabled(): boolean { return this.enabled }

  /** Save current orbit state for restoration after interior visit. */
  saveState(): CameraState {
    return {
      yaw: this.yaw,
      pitch: this.pitch,
      distance: this.distance,
      targetDistance: this.targetDistance,
      target: this.target.clone(),
      mode: this.mode,
    }
  }

  /** Restore a previously saved state with smooth transition. */
  restoreState(state: CameraState): void {
    this.yaw = state.yaw
    this.pitch = state.pitch
    this.targetDistance = state.targetDistance
    this.distance = state.distance
    this.mode = state.mode
    this.followTarget = null
    // Copy target immediately so interrupted transitions don't leave drift
    this.target.copy(state.target)

    const pitchRad = this.pitch * pc.math.DEG_TO_RAD
    const yawRad = this.yaw * pc.math.DEG_TO_RAD
    const toPos = new pc.Vec3(
      state.target.x + this.distance * Math.cos(pitchRad) * Math.sin(yawRad),
      state.target.y + this.distance * Math.sin(pitchRad),
      state.target.z + this.distance * Math.cos(pitchRad) * Math.cos(yawRad),
    )
    this.startTransition(toPos, state.target)
  }

  /** Per-frame update. */
  update(dt: number): void {
    if (!this.enabled) return

    // Safety: if follow target was destroyed, fall back to overview
    if (this.mode === 'play' && this.followTarget && !this.followTarget.enabled) {
      this.followTarget = null
      this.mode = 'overview'
      this.transitioning = false
    }

    // Check for double-click navigation
    this.handleDoubleClick()

    // Handle smooth transition
    if (this.transitioning) {
      this.transitionProgress = Math.min(1, this.transitionProgress + dt * 1.5)
      const t = easeOutCubic(this.transitionProgress)

      this._scratchPos.lerp(this.transitionFrom, this.transitionTo, t)
      this.cameraEntity.setPosition(this._scratchPos)

      this._scratchTgt.lerp(this.transitionTargetFrom, this.transitionTargetTo, t)
      this.target.copy(this._scratchTgt)
      this.cameraEntity.lookAt(this._scratchTgt)

      if (this.transitionProgress >= 1) {
        this.transitioning = false
      }
      return
    }

    // ─── Orbit (mouse drag) ───
    const orbit = this.input.getOrbitDelta()
    if (orbit.dx !== 0 || orbit.dy !== 0) {
      // Set velocity directly from mouse delta — no dead zone
      this.yawVelocity = -orbit.dx * this.orbitSensitivity
      this.pitchVelocity = -orbit.dy * this.orbitSensitivity
    }

    // Apply orbit with momentum
    if (Math.abs(this.yawVelocity) > this.momentumThreshold ||
        Math.abs(this.pitchVelocity) > this.momentumThreshold) {
      this.yaw += this.yawVelocity
      this.pitch = clamp(this.pitch + this.pitchVelocity, this.minPitch, this.maxPitch)
      this.yawVelocity *= this.orbitDamping
      this.pitchVelocity *= this.orbitDamping
    }

    // ─── Pan (middle mouse drag) ───
    const pan = this.input.getPanDelta()
    if (pan.dx !== 0 || pan.dy !== 0) {
      this.applyPan(pan.dx, pan.dy)
    }

    // ─── WASD movement — works in all modes ───
    const move = this.input.getMovementVector()
    if (move.x !== 0 || move.z !== 0) {
      // Speed scales with zoom — close = slow (precise), far = fast (cover ground)
      const distanceFactor = Math.max(this.distance / 15, 0.3)
      const sprint = this.input.isRunning() ? 2.5 : 1
      const speed = this.keyMoveSpeed * distanceFactor * sprint * dt
      this.applyKeyMove(move.x * speed, move.z * speed)
    }

    // ─── Scroll zoom ───
    const scroll = this.input.getScrollDelta()
    if (scroll !== 0) {
      const zoomFactor = Math.max(this.targetDistance * 0.15, 0.5)
      this.targetDistance = clamp(
        this.targetDistance - scroll * this.zoomSensitivity * zoomFactor,
        this.minDistance,
        this.maxDistance,
      )
    }

    // Smoothly interpolate distance toward target
    this.distance = lerp(this.distance, this.targetDistance, this.zoomLerp)

    // ─── Update camera position ───
    if (this.mode === 'play' && this.followTarget) {
      const targetPos = this.followTarget.getPosition()
      if (!isFinite(targetPos.x)) {
        this.followTarget = null
        this.mode = 'overview'
        return
      }
      this.target.x = lerp(this.target.x, targetPos.x, this.followLerp)
      this.target.y = lerp(this.target.y, targetPos.y, this.followLerp)
      this.target.z = lerp(this.target.z, targetPos.z, this.followLerp)
    }

    this.computeOrbitPosition()
  }

  /** Compute camera position from yaw, pitch, distance around target. */
  private computeOrbitPosition(): void {
    this.clampTarget()

    const pitchRad = this.pitch * pc.math.DEG_TO_RAD
    const yawRad = this.yaw * pc.math.DEG_TO_RAD

    const x = this.target.x + this.distance * Math.cos(pitchRad) * Math.sin(yawRad)
    const y = this.target.y + this.distance * Math.sin(pitchRad)
    const z = this.target.z + this.distance * Math.cos(pitchRad) * Math.cos(yawRad)

    this.cameraEntity.setPosition(x, Math.max(y, 0.1), z)
    this.cameraEntity.lookAt(this.target)
  }

  /** Keep the look-at target within the world bounds. */
  private clampTarget(): void {
    this.target.x = clamp(this.target.x, -this.worldBounds, this.worldBounds)
    this.target.z = clamp(this.target.z, -this.worldBounds, this.worldBounds)
  }

  /** Apply mouse pan — move target along camera's ground-plane axes. */
  private applyPan(dx: number, dy: number): void {
    const yawRad = this.yaw * pc.math.DEG_TO_RAD
    const scale = this.panSpeed * this.distance * 0.003

    const rightX = Math.cos(yawRad)
    const rightZ = -Math.sin(yawRad)
    const fwdX = Math.sin(yawRad)
    const fwdZ = Math.cos(yawRad)

    this.target.x += (rightX * dx + fwdX * dy) * scale
    this.target.z += (rightZ * dx + fwdZ * dy) * scale
  }

  /**
   * Apply WASD movement — move target relative to camera facing direction.
   *
   * Camera looks from orbit position toward target. Ground-projected forward
   * is (-sin(yaw), -cos(yaw)). W moves target forward (toward where camera looks),
   * A/D strafe perpendicular.
   */
  private applyKeyMove(moveX: number, moveZ: number): void {
    const yawRad = this.yaw * pc.math.DEG_TO_RAD

    // Camera right axis (perpendicular to forward on ground plane)
    const rightX = Math.cos(yawRad)
    const rightZ = -Math.sin(yawRad)

    // Camera forward axis (direction camera looks, projected to ground)
    const fwdX = -Math.sin(yawRad)
    const fwdZ = -Math.cos(yawRad)

    // moveX = strafe (A/D), moveZ = forward/back (W/S)
    // W → z=-1 from getMovementVector → multiply by fwd → moves forward
    this.target.x += rightX * moveX + fwdX * moveZ
    this.target.z += rightZ * moveX + fwdZ * moveZ
  }

  /**
   * Handle double-click: raycast to ground plane (Y=0) and fly camera there.
   */
  private handleDoubleClick(): void {
    const dblClick = this.input.consumeDoubleClick()
    if (!dblClick) return

    const camera = this.cameraEntity.camera
    if (!camera) return

    camera.screenToWorld(dblClick.x, dblClick.y, camera.nearClip, this._rayNear)
    camera.screenToWorld(dblClick.x, dblClick.y, camera.farClip, this._rayFar)

    const dirX = this._rayFar.x - this._rayNear.x
    const dirY = this._rayFar.y - this._rayNear.y
    const dirZ = this._rayFar.z - this._rayNear.z

    if (Math.abs(dirY) < 0.0001) return
    const t = -this._rayNear.y / dirY
    if (t < 0) return

    const hitX = this._rayNear.x + dirX * t
    const hitZ = this._rayNear.z + dirZ * t

    this.focusOnPosition(new pc.Vec3(hitX, 0, hitZ), 5)
  }

  /** Start a smooth transition from current position. */
  private startTransition(toPos: pc.Vec3, toTarget: pc.Vec3): void {
    this.transitionFrom.copy(this.cameraEntity.getPosition())
    this.transitionTargetFrom.copy(this.target)
    this.transitionTo.copy(toPos)
    this.transitionTargetTo.copy(toTarget)
    this.transitionProgress = 0
    this.transitioning = true
  }

  /** Start transition to orbit position around follow target. */
  private startTransitionToOrbit(): void {
    const pitchRad = this.pitch * pc.math.DEG_TO_RAD
    const yawRad = this.yaw * pc.math.DEG_TO_RAD
    const targetPos = this.followTarget!.getPosition()

    const orbitPos = new pc.Vec3(
      targetPos.x + this.distance * Math.cos(pitchRad) * Math.sin(yawRad),
      targetPos.y + this.distance * Math.sin(pitchRad),
      targetPos.z + this.distance * Math.cos(pitchRad) * Math.cos(yawRad),
    )
    this.startTransition(orbitPos, targetPos)
  }

  /** Smoothly focus the camera on a world position. */
  focusOnPosition(target: pc.Vec3, distance: number = 18): void {
    this.followTarget = null
    this.mode = 'overview'
    this.pitch = 25
    this.targetDistance = distance
    this.distance = distance

    const pitchRad = this.pitch * pc.math.DEG_TO_RAD
    const yawRad = this.yaw * pc.math.DEG_TO_RAD
    const focusPos = new pc.Vec3(
      target.x + distance * Math.cos(pitchRad) * Math.sin(yawRad),
      target.y + distance * Math.sin(pitchRad),
      target.z + distance * Math.cos(pitchRad) * Math.cos(yawRad),
    )
    this.startTransition(focusPos, target)
  }

  /**
   * Create a controls help overlay in the container.
   * Shows semi-transparent controls reference that auto-fades.
   */
  showControlsHelp(container: HTMLElement): void {
    if (this.helpOverlay) return

    const overlay = document.createElement('div')

    // Build content using safe DOM methods (no innerHTML)
    const lines = [
      { bold: true, text: 'Controls' },
      { bold: false, text: 'WASD / Arrows \u2014 Move' },
      { bold: false, text: 'Mouse Drag \u2014 Rotate' },
      { bold: false, text: 'Scroll \u2014 Zoom' },
      { bold: false, text: 'Shift \u2014 Sprint' },
      { bold: false, text: 'Double-click \u2014 Go to' },
    ]

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      if (i > 0) overlay.appendChild(document.createElement('br'))
      const span = document.createElement('span')
      span.textContent = line.text
      if (line.bold) span.style.fontWeight = 'bold'
      overlay.appendChild(span)
    }

    Object.assign(overlay.style, {
      position: 'absolute',
      bottom: '16px',
      left: '16px',
      background: 'rgba(0, 0, 0, 0.6)',
      color: '#fff',
      fontSize: '12px',
      lineHeight: '1.6',
      padding: '10px 14px',
      borderRadius: '8px',
      pointerEvents: 'none',
      zIndex: '5',
      fontFamily: 'system-ui, sans-serif',
      transition: 'opacity 1s ease',
      opacity: '1',
    })

    container.style.position = 'relative'
    container.appendChild(overlay)
    this.helpOverlay = overlay

    // Fade out after 6 seconds
    setTimeout(() => {
      if (overlay.parentNode) {
        overlay.style.opacity = '0'
        setTimeout(() => overlay.remove(), 1000)
      }
    }, 6000)
  }

  /** Clean up help overlay if still present. */
  destroyHelp(): void {
    this.helpOverlay?.remove()
    this.helpOverlay = null
  }
}
