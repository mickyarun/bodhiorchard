/**
 * InputManager — keyboard/mouse/touch input manager.
 *
 * Follows the official PlayCanvas input pattern:
 * - Check mouse.isPressed() inside mousemove for immediate response
 * - No dead zone — orbit starts the instant you drag
 * - Click vs drag discrimination via displacement threshold (not orbit delay)
 *
 * Controls:
 * - Left-drag or right-drag: orbit (rotate view)
 * - Middle-drag: pan (move look-at target)
 * - Scroll: zoom in/out
 * - WASD/arrows: move relative to camera direction
 * - Shift: sprint
 * - Double-click: navigate to clicked ground position
 */
import * as pc from 'playcanvas'

export interface MovementVector {
  x: number
  z: number
}

export interface OrbitDelta {
  dx: number
  dy: number
}

export class InputManager {
  private keyboard!: pc.Keyboard
  private mouse!: pc.Mouse
  private touch: pc.TouchDevice | null = null

  // Accumulated deltas (consumed on read each frame)
  private orbitDx = 0
  private orbitDy = 0
  private panDx = 0
  private panDy = 0
  private scrollDelta = 0

  // Click detection — discriminates click from drag
  private mouseDownPos: { x: number; y: number } | null = null
  private mouseDownTime = 0
  private hasDragged = false // true once displacement exceeds threshold
  private pendingClick: { x: number; y: number } | null = null
  private currentMousePos: { x: number; y: number } = { x: 0, y: 0 }
  private static readonly DRAG_THRESHOLD = 4 // px — only affects click suppression
  private static readonly CLICK_MAX_MS = 300

  // Double-click detection
  private lastClickTime = 0
  private lastClickPos: { x: number; y: number } | null = null
  private pendingDoubleClick: { x: number; y: number } | null = null
  private static readonly DOUBLE_CLICK_MS = 400
  private static readonly DOUBLE_CLICK_DIST = 10

  // Touch joystick state
  private touchMoveId: number | null = null
  private touchMoveStart = { x: 0, y: 0 }
  private touchMoveCurrent = { x: 0, y: 0 }
  private touchOrbitId: number | null = null
  private touchOrbitPrev = { x: 0, y: 0 }
  private touchOrbitDx = 0
  private touchOrbitDy = 0

  private canvas: HTMLCanvasElement | null = null
  private nativeWheelHandler: ((e: WheelEvent) => void) | null = null

  init(canvas: HTMLCanvasElement): void {
    this.canvas = canvas
    this.keyboard = new pc.Keyboard(window)

    this.mouse = new pc.Mouse(canvas)
    this.mouse.disableContextMenu()
    this.mouse.on(pc.EVENT_MOUSEDOWN, this.onMouseDown, this)
    this.mouse.on(pc.EVENT_MOUSEUP, this.onMouseUp, this)
    this.mouse.on(pc.EVENT_MOUSEMOVE, this.onMouseMove, this)
    this.mouse.on(pc.EVENT_MOUSEWHEEL, this.onMouseWheel, this)

    // Prevent page scroll when wheeling over the canvas (but not UI overlays)
    this.nativeWheelHandler = (e: WheelEvent) => {
      if (e.target instanceof HTMLElement &&
          e.target.closest('.v-overlay, .v-menu, .v-list, .graph-detail-panel, .graph-toolbar')) {
        return
      }
      e.preventDefault()
    }
    canvas.addEventListener('wheel', this.nativeWheelHandler, { passive: false })

    // Touch support (optional)
    if ('ontouchstart' in window) {
      this.touch = new pc.TouchDevice(canvas)
      this.touch.on(pc.EVENT_TOUCHSTART, this.onTouchStart, this)
      this.touch.on(pc.EVENT_TOUCHMOVE, this.onTouchMove, this)
      this.touch.on(pc.EVENT_TOUCHEND, this.onTouchEnd, this)
      this.touch.on(pc.EVENT_TOUCHCANCEL, this.onTouchEnd, this)
    }
  }

  /** WASD/arrow movement vector (normalized if non-zero). */
  getMovementVector(): MovementVector {
    let x = 0
    let z = 0

    if (this.keyboard.isPressed(pc.KEY_W) || this.keyboard.isPressed(pc.KEY_UP)) z += 1
    if (this.keyboard.isPressed(pc.KEY_S) || this.keyboard.isPressed(pc.KEY_DOWN)) z -= 1
    if (this.keyboard.isPressed(pc.KEY_A) || this.keyboard.isPressed(pc.KEY_LEFT)) x -= 1
    if (this.keyboard.isPressed(pc.KEY_D) || this.keyboard.isPressed(pc.KEY_RIGHT)) x += 1

    // Touch joystick
    if (this.touchMoveId !== null) {
      const dx = this.touchMoveCurrent.x - this.touchMoveStart.x
      const dy = this.touchMoveCurrent.y - this.touchMoveStart.y
      const maxRadius = 60
      x += Math.max(-1, Math.min(1, dx / maxRadius))
      z += Math.max(-1, Math.min(1, dy / maxRadius))
    }

    const len = Math.sqrt(x * x + z * z)
    if (len > 1) {
      x /= len
      z /= len
    }

    return { x, z }
  }

  isPressed(key: number): boolean {
    return this.keyboard.isPressed(key)
  }

  wasPressed(key: number): boolean {
    return this.keyboard.wasPressed(key)
  }

  isRunning(): boolean {
    return this.keyboard.isPressed(pc.KEY_SHIFT)
  }

  isInteract(): boolean {
    return this.keyboard.wasPressed(pc.KEY_E)
  }

  /** Get orbit delta this frame (left/right-drag, consumed on read). */
  getOrbitDelta(): OrbitDelta {
    const dx = this.orbitDx + this.touchOrbitDx
    const dy = this.orbitDy + this.touchOrbitDy
    this.orbitDx = 0
    this.orbitDy = 0
    this.touchOrbitDx = 0
    this.touchOrbitDy = 0
    return { dx, dy }
  }

  /** Get pan delta this frame (middle-drag, consumed on read). */
  getPanDelta(): { dx: number; dy: number } {
    const dx = this.panDx
    const dy = this.panDy
    this.panDx = 0
    this.panDy = 0
    return { dx, dy }
  }

  /** Get scroll wheel delta this frame (consumed on read). */
  getScrollDelta(): number {
    const d = this.scrollDelta
    this.scrollDelta = 0
    return d
  }

  // ─── Mouse Handlers ─────────────────────────────────

  private onMouseDown(event: pc.MouseEvent): void {
    this.mouseDownPos = { x: event.x, y: event.y }
    this.mouseDownTime = performance.now()
    this.hasDragged = false
  }

  private onMouseUp(event: pc.MouseEvent): void {
    if (this.mouseDownPos && !this.hasDragged) {
      const elapsed = performance.now() - this.mouseDownTime
      if (elapsed < InputManager.CLICK_MAX_MS && event.button === pc.MOUSEBUTTON_LEFT) {
        const now = performance.now()
        const clickPos = { x: event.x, y: event.y }

        // Check for double-click
        if (this.lastClickPos) {
          const dt = now - this.lastClickTime
          const dx = clickPos.x - this.lastClickPos.x
          const dy = clickPos.y - this.lastClickPos.y
          const dist = Math.sqrt(dx * dx + dy * dy)

          if (dt < InputManager.DOUBLE_CLICK_MS && dist < InputManager.DOUBLE_CLICK_DIST) {
            this.pendingDoubleClick = clickPos
            this.pendingClick = null
            this.lastClickTime = 0
            this.lastClickPos = null
          } else {
            this.pendingClick = clickPos
            this.lastClickTime = now
            this.lastClickPos = clickPos
          }
        } else {
          this.pendingClick = clickPos
          this.lastClickTime = now
          this.lastClickPos = clickPos
        }
      }
    }
    this.mouseDownPos = null
    this.hasDragged = false
  }

  private onMouseMove(event: pc.MouseEvent): void {
    this.currentMousePos = { x: event.x, y: event.y }

    // Track drag threshold for click suppression only
    if (this.mouseDownPos && !this.hasDragged) {
      const dx = event.x - this.mouseDownPos.x
      const dy = event.y - this.mouseDownPos.y
      if (Math.sqrt(dx * dx + dy * dy) > InputManager.DRAG_THRESHOLD) {
        this.hasDragged = true
      }
    }

    // PlayCanvas pattern: check isPressed() in mousemove — no dead zone
    // Left or right drag → orbit (rotate view)
    if (this.mouse.isPressed(pc.MOUSEBUTTON_LEFT) || this.mouse.isPressed(pc.MOUSEBUTTON_RIGHT)) {
      this.orbitDx += event.dx
      this.orbitDy += event.dy
    }
    // Middle drag → pan (move target)
    if (this.mouse.isPressed(pc.MOUSEBUTTON_MIDDLE)) {
      this.panDx += event.dx
      this.panDy += event.dy
    }
  }

  private onMouseWheel(event: pc.MouseEvent): void {
    // Ignore scroll when mouse is over a UI overlay (dropdown menus, panels)
    const native = (event as unknown as { event?: Event }).event
    if (native?.target instanceof HTMLElement) {
      if (native.target.closest('.v-overlay, .v-menu, .v-list, .graph-detail-panel, .graph-toolbar')) {
        return
      }
    }
    this.scrollDelta += event.wheelDelta
  }

  /** Consume and return the pending click, if any. */
  consumeClick(): { x: number; y: number } | null {
    const click = this.pendingClick
    this.pendingClick = null
    return click
  }

  /** Consume and return the pending double-click, if any. */
  consumeDoubleClick(): { x: number; y: number } | null {
    const dbl = this.pendingDoubleClick
    this.pendingDoubleClick = null
    return dbl
  }

  /** Current mouse screen position (for hover raycasting). */
  getHoverPos(): { x: number; y: number } {
    return this.currentMousePos
  }

  /** Get canvas dimensions for screen-to-world raycasting. */
  getCanvasSize(): { width: number; height: number } {
    return {
      width: this.canvas?.clientWidth ?? window.innerWidth,
      height: this.canvas?.clientHeight ?? window.innerHeight,
    }
  }

  // ─── Touch Handlers ─────────────────────────────────

  private onTouchStart(event: pc.TouchEvent): void {
    const canvasWidth = event.element?.clientWidth ?? window.innerWidth

    for (const touch of event.changedTouches) {
      if (touch.x < canvasWidth / 2 && this.touchMoveId === null) {
        this.touchMoveId = touch.id
        this.touchMoveStart = { x: touch.x, y: touch.y }
        this.touchMoveCurrent = { x: touch.x, y: touch.y }
      } else if (touch.x >= canvasWidth / 2 && this.touchOrbitId === null) {
        this.touchOrbitId = touch.id
        this.touchOrbitPrev = { x: touch.x, y: touch.y }
      }
    }
  }

  private onTouchMove(event: pc.TouchEvent): void {
    for (const touch of event.changedTouches) {
      if (touch.id === this.touchMoveId) {
        this.touchMoveCurrent = { x: touch.x, y: touch.y }
      } else if (touch.id === this.touchOrbitId) {
        this.touchOrbitDx += touch.x - this.touchOrbitPrev.x
        this.touchOrbitDy += touch.y - this.touchOrbitPrev.y
        this.touchOrbitPrev = { x: touch.x, y: touch.y }
      }
    }
  }

  private onTouchEnd(event: pc.TouchEvent): void {
    for (const touch of event.changedTouches) {
      if (touch.id === this.touchMoveId) {
        this.touchMoveId = null
      } else if (touch.id === this.touchOrbitId) {
        this.touchOrbitId = null
      }
    }
  }

  // ─── Cleanup ─────────────────────────────────────────

  destroy(): void {
    this.mouse.off(pc.EVENT_MOUSEDOWN, this.onMouseDown, this)
    this.mouse.off(pc.EVENT_MOUSEUP, this.onMouseUp, this)
    this.mouse.off(pc.EVENT_MOUSEMOVE, this.onMouseMove, this)
    this.mouse.off(pc.EVENT_MOUSEWHEEL, this.onMouseWheel, this)

    if (this.canvas && this.nativeWheelHandler) {
      this.canvas.removeEventListener('wheel', this.nativeWheelHandler)
      this.nativeWheelHandler = null
    }

    if (this.touch) {
      this.touch.off(pc.EVENT_TOUCHSTART, this.onTouchStart, this)
      this.touch.off(pc.EVENT_TOUCHMOVE, this.onTouchMove, this)
      this.touch.off(pc.EVENT_TOUCHEND, this.onTouchEnd, this)
      this.touch.off(pc.EVENT_TOUCHCANCEL, this.onTouchEnd, this)
    }
  }
}
