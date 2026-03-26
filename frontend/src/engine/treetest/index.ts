/**
 * TreeTestEngine — standalone entry point for the Tree3D demo.
 *
 * Boots PlayCanvas with PBR lighting, wires the UI to Tree3DSystem,
 * and runs an auto-orbiting camera.
 */
import * as pc from 'playcanvas'
import { Application } from '../core/Application'
import { InputManager } from '../input/InputManager'
import { MaterialFactory } from '../rendering/MaterialFactory'
import { Tree3DSystem } from './Tree3DSystem'
import { GroundBuilder } from './GroundBuilder'
import { UIOverlay } from './UIOverlay'
import { clamp, lerp } from '../utils/MathUtils'

const CAM = {
  yaw: -30,
  pitch: 22,
  distance: 20,
  lookAtY: 2.0,
  autoOrbitSpeed: 6,
  idleDelay: 2.0,
  sensitivity: 0.3,
  zoomScale: 0.15,
  zoomMin: 1,
  zoomMax: 30,
  smoothing: 0.08,
}

export class TreeTestEngine {
  private application: Application | null = null
  private input: InputManager | null = null
  private materials: MaterialFactory | null = null
  private tree: Tree3DSystem | null = null
  private ground: GroundBuilder | null = null
  private ui: UIOverlay | null = null
  private canvas: HTMLCanvasElement | null = null

  private yaw = CAM.yaw
  private pitch = CAM.pitch
  private distance = CAM.distance
  private targetDistance = CAM.distance
  private lookAtY = CAM.lookAtY
  private lastInputTime = 0

  async init(container: HTMLElement, width: number, height: number): Promise<void> {
    this.canvas = document.createElement('canvas')
    Object.assign(this.canvas.style, { width: '100%', height: '100%', display: 'block' })
    container.appendChild(this.canvas)

    this.application = new Application()
    this.application.init(this.canvas, width, height)

    this.input = new InputManager()
    this.input.init(this.canvas)

    this.materials = new MaterialFactory()

    // Ground
    this.ground = new GroundBuilder(this.application.app)
    const groundRoot = new pc.Entity('GroundRoot')
    this.application.app.root.addChild(groundRoot)
    this.ground.build(groundRoot, 4)

    // Tree system
    this.tree = new Tree3DSystem(this.application.app, this.materials)

    this.computeOrbitPosition()
    this.application.setConfig({ onUpdate: (dt) => this.onUpdate(dt) })

    // UI
    this.ui = new UIOverlay(container)
    this.ui.setStage(0)
    this.ui.setGrowLabel('Grow')
    this.ui.onGrow(() => this.startGrowth())
    this.ui.onReset(() => this.resetTree())

    // Start immediately
    this.startGrowth()
  }

  private startGrowth(): void {
    if (!this.tree) return
    this.tree.startTree()
    this.ui?.setGrowEnabled(false)
    this.ui?.setGrowLabel('Growing...')
  }

  private resetTree(): void {
    if (!this.tree) return
    this.tree.reset()
    this.ui?.setGrowEnabled(true)
    this.ui?.setGrowLabel('Grow')
    this.ui?.setStage(0)
  }

  private onUpdate(dt: number): void {
    if (!this.input || !this.application) return

    // Tree growth
    if (this.tree) {
      const stillGrowing = this.tree.update(dt)
      if (!stillGrowing && !this.tree.isGrowing()) {
        this.ui?.setGrowEnabled(true)
        this.ui?.setGrowLabel('New Tree')
      }
      this.ui?.showProgress(this.tree.isGrowing() ? 0.5 : 0)
    }

    this.handleCamera(dt)
  }

  private handleCamera(dt: number): void {
    if (!this.input) return
    const elapsed = this.application!.clock.elapsed

    const orbit = this.input.getOrbitDelta()
    if (orbit.dx !== 0 || orbit.dy !== 0) {
      this.yaw -= orbit.dx * CAM.sensitivity
      this.pitch = clamp(this.pitch - orbit.dy * CAM.sensitivity, 2, 85)
      this.lastInputTime = elapsed
    }

    const scroll = this.input.getScrollDelta()
    if (scroll !== 0) {
      const factor = Math.max(this.targetDistance * CAM.zoomScale, 0.3)
      this.targetDistance = clamp(this.targetDistance - scroll * factor, CAM.zoomMin, CAM.zoomMax)
      this.lastInputTime = elapsed
    }

    // Drain unused input channels to prevent accumulation
    this.input.getPanDelta()
    this.input.getMovementVector()

    if (elapsed - this.lastInputTime > CAM.idleDelay) {
      this.yaw += CAM.autoOrbitSpeed * dt
    }

    this.distance = lerp(this.distance, this.targetDistance, CAM.smoothing)
    this.computeOrbitPosition()
  }

  private computeOrbitPosition(): void {
    if (!this.application) return
    const pitchRad = this.pitch * (Math.PI / 180)
    const yawRad = this.yaw * (Math.PI / 180)
    const camera = this.application.camera
    camera.setPosition(
      this.distance * Math.cos(pitchRad) * Math.sin(yawRad),
      Math.max(this.lookAtY + this.distance * Math.sin(pitchRad), 0.3),
      this.distance * Math.cos(pitchRad) * Math.cos(yawRad),
    )
    camera.lookAt(new pc.Vec3(0, this.lookAtY, 0))
  }

  resize(width: number, height: number): void {
    this.application?.resize(width, height)
  }

  destroy(): void {
    this.tree?.destroy(); this.tree = null
    this.ground?.destroy(); this.ground = null
    this.ui?.destroy(); this.ui = null
    this.input?.destroy(); this.input = null
    this.materials?.clear(); this.materials = null
    this.application?.destroy(); this.application = null
    if (this.canvas) { this.canvas.remove(); this.canvas = null }
  }
}
