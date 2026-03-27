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

  // Hover tooltip DOM nodes
  private tooltipEl:     HTMLDivElement   | null = null
  private tooltipTitle:  HTMLSpanElement  | null = null
  private tooltipStatus: HTMLSpanElement  | null = null
  private tooltipDot:    HTMLSpanElement  | null = null

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

    // Tree + leaf systems
    this.tree   = new Tree3DSystem(app, this.materials)
    this.leaves = new LeafSystem(app, this.materials)

    // Creature systems — load GLBs in parallel, non-blocking for tree boot
    this.birds = new BirdSystem(app)
    this.bees  = new BeeSystem(app)
    await Promise.all([this.birds.init(), this.bees.init()])

    this.computeOrbitPosition()
    this.application.setConfig({ onUpdate: (dt) => this.onUpdate(dt) })

    // Build tooltip DOM — purely via DOM methods, no innerHTML
    container.style.position = 'relative'
    this.tooltipEl = document.createElement('div')
    Object.assign(this.tooltipEl.style, {
      position:       'absolute',
      pointerEvents:  'none',
      display:        'none',
      background:     'rgba(10, 10, 20, 0.85)',
      color:          '#fff',
      border:         '1px solid rgba(255,255,255,0.15)',
      borderRadius:   '8px',
      padding:        '7px 12px',
      fontSize:       '13px',
      fontFamily:     'system-ui, -apple-system, sans-serif',
      backdropFilter: 'blur(8px)',
      whiteSpace:     'nowrap',
      zIndex:         '20',
      lineHeight:     '1.5',
    })
    this.tooltipTitle = document.createElement('span')
    this.tooltipTitle.style.fontWeight = '700'

    const statusLine = document.createElement('div')
    Object.assign(statusLine.style, { fontSize: '11px', opacity: '0.75' })

    this.tooltipDot    = document.createElement('span')
    this.tooltipStatus = document.createElement('span')
    statusLine.appendChild(this.tooltipDot)
    statusLine.appendChild(this.tooltipStatus)

    this.tooltipEl.appendChild(this.tooltipTitle)
    this.tooltipEl.appendChild(statusLine)
    container.appendChild(this.tooltipEl)

    // Wire hover events on canvas
    this._onMouseMove  = (e) => this.onMouseMove(e)
    this._onMouseLeave = ()  => this.hideTooltip()
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
    this.hideTooltip()
    this.ui?.setGrowEnabled(true)
    this.ui?.setGrowLabel('Grow')
    this.ui?.showProgress(0)
  }

  private onUpdate(dt: number): void {
    if (!this.input || !this.application) return

    if (this.tree) {
      const wasGrowing = this.tree.isGrowing()
      if (wasGrowing) {
        const stillGrowing = this.tree.update(dt)
        this.ui?.showProgress(0.5)
        // Detect the exact frame the tree finishes growing
        if (!stillGrowing && !this.leavesSpawned) {
          const tips = this.tree.getTerminalTips()
          this.leaves?.spawnLeaves(tips, this.tree.getRootColor())
          this.leavesSpawned = true
          this.ui?.setGrowEnabled(true)
          this.ui?.setGrowLabel('New Tree')
          this.ui?.showProgress(0)

          // Build entity → feature map for hover hit-testing
          this.tree.buildFeatureEntityMap()

          // Position creatures at canopy — compute bounding sphere from terminal tips
          if (tips.length > 0) {
            let cx = 0, cy = 0, cz = 0
            let minY = Infinity, maxY = -Infinity
            for (const t of tips) {
              cx += t.position.x; cy += t.position.y; cz += t.position.z
              minY = Math.min(minY, t.position.y)
              maxY = Math.max(maxY, t.position.y)
            }
            cx /= tips.length; cy /= tips.length; cz /= tips.length
            let maxR = 0
            for (const t of tips) {
              const dx = t.position.x - cx, dz = t.position.z - cz
              maxR = Math.max(maxR, Math.sqrt(dx * dx + dz * dz))
            }
            const canopyR      = Math.max(maxR, 1.5)
            const canopyCenter = new pc.Vec3(cx, cy, cz)
            this.birds?.setTreeTarget(canopyCenter, canopyR + 1.5, maxY + 0.5)
            this.bees?.setTreeTarget(canopyCenter,  canopyR,        cy)

            // Auto-fit camera to tree height for large trees
            if (maxY > this.lookAtY + 6) {
              this.lookAtY = maxY * 0.42
              this.lookAtTarget.y = this.lookAtY
              this.targetDistance = clamp(maxY * 1.8, CAM.distance, CAM.zoomMax)
            }
          }
        }
      }
    }

    this.leaves?.update(dt)
    this.birds?.update(dt)
    this.bees?.update(dt)
    this.handleCamera(dt)
  }

  // ─── Hover Tooltip ──────────────────────────────────────────────────────────

  private onMouseMove(e: MouseEvent): void {
    if (!this.tree || !this.application || !this.canvas || !this.tooltipEl) return
    const featureMap = this.tree.getFeatureEntityMap()
    if (featureMap.size === 0) { this.hideTooltip(); return }

    const rect = this.canvas.getBoundingClientRect()
    const mx   = e.clientX - rect.left
    const my   = e.clientY - rect.top

    const cameraComp = this.application.camera.camera
    if (!cameraComp) { this.hideTooltip(); return }

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
      this.showTooltip(best.title, best.status, mx, my)
    } else {
      this.hideTooltip()
    }
  }

  private showTooltip(title: string, status: string, x: number, y: number): void {
    if (!this.tooltipEl || !this.tooltipTitle || !this.tooltipStatus || !this.tooltipDot) return

    this.tooltipTitle.textContent  = title
    this.tooltipStatus.textContent = ' ' + status.replace('_', ' ')
    this.tooltipDot.textContent    = '● '
    this.tooltipDot.style.color    =
      status === 'planned'     ? '#3cc850' :
      status === 'in_progress' ? '#f09628' : '#dc3232'

    this.tooltipEl.style.display = 'block'

    // Clamp so tooltip doesn't overflow canvas edges
    const tw   = this.tooltipEl.offsetWidth  || 160
    const th   = this.tooltipEl.offsetHeight || 48
    const cw   = this.canvas?.clientWidth  ?? 800
    const left = Math.min(x + 14, cw - tw - 8)
    const top  = Math.max(y - th - 14, 8)
    this.tooltipEl.style.left = `${left}px`
    this.tooltipEl.style.top  = `${top}px`
  }

  private hideTooltip(): void {
    if (this.tooltipEl) this.tooltipEl.style.display = 'none'
  }

  // ─── Camera ─────────────────────────────────────────────────────────────────

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
    this.tooltipEl?.remove(); this.tooltipEl = null
    this.tooltipTitle  = null
    this.tooltipStatus = null
    this.tooltipDot    = null
    this.tree?.destroy(); this.tree = null
    this.leaves?.destroy(); this.leaves = null
    this.birds?.destroy(); this.birds = null
    this.bees?.destroy(); this.bees = null
    this.ground?.destroy(); this.ground = null
    this.ui?.destroy(); this.ui = null
    this.input?.destroy(); this.input = null
    this.materials?.clear(); this.materials = null
    this.application?.destroy(); this.application = null
    if (this.canvas) { this.canvas.remove(); this.canvas = null }
  }
}
