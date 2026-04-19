// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
import { LeafSystem } from './LeafSystem'
import { BirdSystem } from './BirdSystem'
import { BeeSystem } from './BeeSystem'
import { WindSystem } from './WindSystem'
import { GroundBuilder } from './GroundBuilder'
import { UIOverlay } from './UIOverlay'
import { generateFeatures, STATUS_COLOR } from './DemoFeatures'
import type { DemoFeature } from './DemoFeatures'
import { clamp, lerp } from '../utils/MathUtils'

const CAM = {
  yaw: -30,
  pitch: 22,
  distance: 28,
  lookAtY: 2.5,
  autoOrbitSpeed: 6,
  idleDelay: 2.0,
  sensitivity: 0.3,
  zoomScale: 0.15,
  zoomMin: 1,
  zoomMax: 200,
  smoothing: 0.08,
}

// Canopy bounding constants — controls creature placement and camera auto-fit
const CANOPY = {
  minRadius:      1.5,   // minimum canopy radius (world units)
  birdsClearance: 1.5,   // extra clearance added to canopy radius for birds
  birdsAbove:     0.5,   // height above maxY for birds flight ceiling
  camLookFactor:  0.42,  // lookAtY = maxY × this factor for tall trees
  camDistFactor:  1.8,   // targetDistance = maxY × this factor for tall trees
  camFitThreshold: 6,    // only auto-fit camera when tree is this much taller than current lookAtY
}

// Pixel radius within which a hover registers on a projected branch position
const HOVER_PX = 18

export class TreeTestEngine {
  private application: Application | null = null
  private input: InputManager | null = null
  private materials: MaterialFactory | null = null
  private tree: Tree3DSystem | null = null
  private leaves: LeafSystem | null = null
  private birds: BirdSystem | null = null
  private bees: BeeSystem | null = null
  private wind: WindSystem | null = null
  private ground: GroundBuilder | null = null
  private ui: UIOverlay | null = null
  private canvas: HTMLCanvasElement | null = null

  private yaw = CAM.yaw
  private pitch = CAM.pitch
  private distance = CAM.distance
  private targetDistance = CAM.distance
  private lookAtY = CAM.lookAtY
  private lastInputTime = 0
  // Cached lookAt target — avoids new pc.Vec3 every frame
  private lookAtTarget = new pc.Vec3(0, CAM.lookAtY, 0)
  // Tracks whether leaves have been spawned for the current tree
  private leavesSpawned = false

  private _onMouseMove:  ((e: MouseEvent) => void) | null = null
  private _onMouseLeave: (() => void) | null = null

  // Scratch Vec3 for worldToScreen projection — zero GC on mousemove
  private static _screenPos = new pc.Vec3()

  async init(container: HTMLElement, width: number, height: number): Promise<void> {
    this.canvas = document.createElement('canvas')
    Object.assign(this.canvas.style, { width: '100%', height: '100%', display: 'block' })
    container.appendChild(this.canvas)

    this.application = new Application()
    this.application.init(this.canvas, width, height)

    // Glow mode: near-black scene so emissive branches stand out
    const app = this.application.app
    const cam = this.application.camera.camera!
    cam.clearColor = new pc.Color(0.02, 0.02, 0.04)
    app.scene.ambientLight = new pc.Color(0.05, 0.05, 0.08)
    // pc.Scene.fog is not fully typed in v2.17 — single cast with version note
    ;(app.scene as unknown as { fog: { type: string } }).fog.type = pc.FOG_NONE

    this.input = new InputManager()
    this.input.init(this.canvas)

    this.materials = new MaterialFactory()

    // Ground
    this.ground = new GroundBuilder(app)
    const groundRoot = new pc.Entity('GroundRoot')
    app.root.addChild(groundRoot)
    this.ground.build(groundRoot, 4)

    // Tree + leaf + wind systems
    this.wind   = new WindSystem({ strength: 0.4 })
    this.tree   = new Tree3DSystem(app)
    this.tree.setWindSystem(this.wind)
    this.leaves = new LeafSystem(app, this.materials, this.tree.getRoot())
    this.leaves.setWindSystem(this.wind)

    // Creature systems — load GLBs in parallel, non-blocking for tree boot
    this.birds = new BirdSystem(app)
    this.bees  = new BeeSystem(app)
    await Promise.all([this.birds.init(), this.bees.init()])

    this.computeOrbitPosition()
    this.application.setConfig({ onUpdate: (dt) => this.onUpdate(dt) })

    // Wire hover events on canvas
    this._onMouseMove  = (e) => this.onMouseMove(e)
    this._onMouseLeave = ()  => this.ui?.hideFeatureTooltip()
    this.canvas.addEventListener('mousemove',  this._onMouseMove)
    this.canvas.addEventListener('mouseleave', this._onMouseLeave)

    // UI
    this.ui = new UIOverlay(container)
    this.ui.setGrowLabel('Grow')
    this.ui.onGrow(() => this.startGrowth())
    this.ui.onReset(() => this.resetTree())
    this.ui.onToggleBirds(enabled => this.birds?.setEnabled(enabled))
    this.ui.onToggleBees(enabled  => this.bees?.setEnabled(enabled))
    this.ui.onLoadFeatures(count  => this.loadFeatures(count))
    this.ui.onWindStrength(strength => this.wind?.setStrength(strength))

    // Start immediately
    this.startGrowth()
  }

  private startGrowth(): void {
    if (!this.tree) return
    this.leavesSpawned = false
    this.leaves?.clear()
    this.tree.startTree(this.ui?.getSelectedColor())
    this.ui?.setGrowEnabled(false)
    this.ui?.setGrowLabel('Growing...')
    this.ui?.showProgress(0.5)
    // Reset camera to default — auto-fit will re-adjust once growth completes
    this.lookAtY = CAM.lookAtY
    this.lookAtTarget.y = this.lookAtY
    this.targetDistance = CAM.distance
  }

  private loadFeatures(count: number): void {
    if (!this.tree) return
    const features = generateFeatures(count)
    this.tree.setFeatures(
      features.map((f: DemoFeature) => ({ color: STATUS_COLOR[f.status], title: f.title, status: f.status }))
    )
    this.startGrowth()
  }

  private resetTree(): void {
    if (!this.tree) return
    this.tree.setFeatures([])
    this.tree.reset()
    this.leaves?.clear()
    this.birds?.clear()
    this.bees?.clear()
    this.leavesSpawned = false
    this.ui?.hideFeatureTooltip()
    this.ui?.setGrowEnabled(true)
    this.ui?.setGrowLabel('Grow')
    this.ui?.showProgress(0)
  }

  private onUpdate(dt: number): void {
    if (!this.input || !this.application) return

    if (this.tree?.isGrowing()) {
      const stillGrowing = this.tree.update(dt)
      if (!stillGrowing && !this.leavesSpawned) {
        this.onGrowthComplete(this.tree.getTerminalTips())
      }
    }

    // Wind: tick global time, then apply sway to branches + leaves
    this.wind?.update(dt)
    this.tree?.applyWind()

    this.leaves?.update(dt)
    this.birds?.update(dt)
    this.bees?.update(dt)
    this.handleCamera(dt)
  }

  /** Called once on the frame growth finishes — spawns leaves, positions creatures, fits camera. */
  private onGrowthComplete(tips: Array<{ position: pc.Vec3; size: number }>): void {
    this.leaves?.spawnLeaves(tips, this.tree!.getRootColor())
    this.leavesSpawned = true
    this.ui?.setGrowEnabled(true)
    this.ui?.setGrowLabel('New Tree')
    this.ui?.showProgress(0)

    // Build entity → feature map for hover hit-testing
    this.tree!.buildFeatureEntityMap()
    // Build wind sway entries for branch animation
    this.tree!.buildWindEntries()

    if (tips.length === 0) return

    // Compute canopy bounding sphere from terminal tips
    let cx = 0, cy = 0, cz = 0
    let maxY = -Infinity
    for (const t of tips) {
      cx += t.position.x; cy += t.position.y; cz += t.position.z
      maxY = Math.max(maxY, t.position.y)
    }
    cx /= tips.length; cy /= tips.length; cz /= tips.length
    let maxR = 0
    for (const t of tips) {
      const dx = t.position.x - cx, dz = t.position.z - cz
      maxR = Math.max(maxR, Math.sqrt(dx * dx + dz * dz))
    }
    const canopyR      = Math.max(maxR, CANOPY.minRadius)
    const canopyCenter = new pc.Vec3(cx, cy, cz)
    this.birds?.setTreeTarget(canopyCenter, canopyR + CANOPY.birdsClearance, maxY + CANOPY.birdsAbove)
    this.bees?.setTreeTarget(canopyCenter,  canopyR, cy)

    // Auto-fit camera to tree height for large trees
    if (maxY > this.lookAtY + CANOPY.camFitThreshold) {
      this.lookAtY = maxY * CANOPY.camLookFactor
      this.lookAtTarget.y = this.lookAtY
      this.targetDistance = clamp(maxY * CANOPY.camDistFactor, CAM.distance, CAM.zoomMax)
    }
  }

  // ─── Hover Tooltip ──────────────────────────────────────────────────────────

  private onMouseMove(e: MouseEvent): void {
    if (!this.tree || !this.application || !this.canvas || !this.ui) return
    const featureMap = this.tree.getFeatureEntityMap()
    if (featureMap.size === 0) { this.ui.hideFeatureTooltip(); return }

    const rect = this.canvas.getBoundingClientRect()
    const mx   = e.clientX - rect.left
    const my   = e.clientY - rect.top

    const cameraComp = this.application.camera.camera
    if (!cameraComp) { this.ui.hideFeatureTooltip(); return }

    const screenPos = TreeTestEngine._screenPos
    let best: { title: string; status: string } | null = null
    let bestDist = HOVER_PX * HOVER_PX

    for (const [entity, feat] of featureMap) {
      const worldPos = entity.getPosition()
      cameraComp.worldToScreen(worldPos, screenPos)
      // screenPos.z < 0 means behind the camera — skip
      if (screenPos.z < 0) continue
      const dx = screenPos.x - mx
      const dy = screenPos.y - my
      const d2 = dx * dx + dy * dy
      if (d2 < bestDist) { bestDist = d2; best = feat }
    }

    if (best) {
      this.ui.showFeatureTooltip(best.title, best.status, mx, my)
    } else {
      this.ui.hideFeatureTooltip()
    }
  }

  // ─── Camera ─────────────────────────────────────────────────────────────────

  private handleCamera(dt: number): void {
    if (!this.input || !this.application) return
    const elapsed = this.application.clock.elapsed

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
    camera.lookAt(this.lookAtTarget)
  }

  resize(width: number, height: number): void {
    this.application?.resize(width, height)
  }

  destroy(): void {
    if (this.canvas && this._onMouseMove)  this.canvas.removeEventListener('mousemove',  this._onMouseMove)
    if (this.canvas && this._onMouseLeave) this.canvas.removeEventListener('mouseleave', this._onMouseLeave)
    this._onMouseMove  = null
    this._onMouseLeave = null
    this.tree?.destroy()
    this.tree = null
    this.leaves?.destroy()
    this.leaves = null
    this.birds?.destroy()
    this.birds = null
    this.bees?.destroy()
    this.bees = null
    this.wind = null
    this.ground?.destroy()
    this.ground = null
    this.ui?.destroy()
    this.ui = null
    this.input?.destroy()
    this.input = null
    this.materials?.clear()
    this.materials = null
    this.application?.destroy()
    this.application = null
    this.canvas?.remove()
    this.canvas = null
  }
}
