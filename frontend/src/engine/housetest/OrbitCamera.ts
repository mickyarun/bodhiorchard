/**
 * OrbitCamera — mouse-driven third-person orbit camera.
 *
 * Left-click drag : orbit (yaw / pitch)
 * Scroll wheel    : zoom (distance)
 *
 * Positions the camera on a sphere centred on the target each frame.
 * Yaw is measured from world +Z CCW when viewed from above:
 *   yaw=0   → camera at +Z (default: directly behind the player)
 *   yaw=90  → camera to the player's right (+X)
 *   yaw=180 → camera at -Z (facing the player's front)
 *
 * The `yaw` getter is exposed so PlayerController can rotate WASD input
 * into camera-relative world directions.
 */
import * as pc from 'playcanvas'

const SENSITIVITY = 0.4   // degrees per pixel dragged
const MIN_PITCH   = 5     // degrees — prevents clipping the ground
const MAX_PITCH   = 80    // degrees — prevents flipping overhead
const MIN_DIST    = 2     // world units
const MAX_DIST    = 80    // world units — allows zooming out to see full village

export class OrbitCamera {
  private camera: pc.Entity | null = null
  private canvas: HTMLCanvasElement | null = null

  private _yaw      = 0
  private _pitch    = 35
  private _distance = 8.6

  private dragging = false
  private lastX    = 0
  private lastY    = 0

  // Scratch — no allocation in the update loop
  private readonly _pos  = new pc.Vec3()
  private readonly _look = new pc.Vec3()

  /** Camera yaw in degrees — consumed by PlayerController for camera-relative WASD. */
  get yaw(): number { return this._yaw }

  // ─── Event handlers (bound once, removed on destroy) ─────────────────────

  private readonly _onMouseDown = (e: MouseEvent): void => {
    this.dragging = true
    this.lastX = e.clientX
    this.lastY = e.clientY
  }

  private readonly _onMouseMove = (e: MouseEvent): void => {
    if (!this.dragging) return
    this._yaw  -= (e.clientX - this.lastX) * SENSITIVITY
    this._pitch  = Math.max(MIN_PITCH, Math.min(MAX_PITCH,
      this._pitch + (e.clientY - this.lastY) * SENSITIVITY))
    this.lastX = e.clientX
    this.lastY = e.clientY
  }

  private readonly _onMouseUp = (): void => { this.dragging = false }

  private readonly _onWheel = (e: WheelEvent): void => {
    e.preventDefault()
    this._distance = Math.max(MIN_DIST, Math.min(MAX_DIST,
      this._distance + e.deltaY * 0.01))
  }

  // ─── Public API ──────────────────────────────────────────────────────────

  init(
    canvas: HTMLCanvasElement,
    camera: pc.Entity,
    yaw: number,
    pitch: number,
    distance: number,
  ): void {
    this.canvas = canvas
    this.camera = camera
    this._yaw      = yaw
    this._pitch    = pitch
    this._distance = distance

    canvas.addEventListener('mousedown', this._onMouseDown)
    canvas.addEventListener('mousemove', this._onMouseMove)
    window.addEventListener('mouseup',   this._onMouseUp)
    canvas.addEventListener('wheel',     this._onWheel, { passive: false })
  }

  /** Instantly reposition the camera — call during scene transitions (black frame). */
  setView(yaw: number, pitch: number, distance: number): void {
    this._yaw      = yaw
    this._pitch    = pitch
    this._distance = distance
  }

  /** Call every frame — spherical → Cartesian, then lookAt target. */
  update(target: pc.Vec3): void {
    if (!this.camera) return
    const yRad = this._yaw   * pc.math.DEG_TO_RAD
    const pRad = this._pitch * pc.math.DEG_TO_RAD
    const cosP = Math.cos(pRad)
    this._pos.set(
      target.x + this._distance * cosP * Math.sin(yRad),
      target.y + this._distance * Math.sin(pRad),
      target.z + this._distance * cosP * Math.cos(yRad),
    )
    this.camera.setPosition(this._pos.x, this._pos.y, this._pos.z)
    this._look.set(target.x, target.y + 0.5, target.z)
    this.camera.lookAt(this._look)
  }

  destroy(): void {
    this.canvas?.removeEventListener('mousedown', this._onMouseDown)
    this.canvas?.removeEventListener('mousemove', this._onMouseMove)
    window.removeEventListener('mouseup',         this._onMouseUp)
    this.canvas?.removeEventListener('wheel',     this._onWheel)
    this.camera = null
    this.canvas = null
  }
}
