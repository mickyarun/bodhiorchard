/**
 * HouseTestEngine — standalone house demo with scene transition.
 *
 * Architecture:
 *   app.root
 *   ├── exteriorRoot  (enabled initially)  — ground + house shell
 *   ├── interiorRoot  (disabled initially) — floor + walls + furniture
 *   └── playerWrapper (always enabled)     — Kenney character
 *
 * Scene swap happens during fade-to-black so the entity toggle is invisible.
 * Collision uses manual AABB (no physics engine dependency).
 * Camera is an orbit camera — left-drag to orbit, scroll to zoom, camera-relative WASD.
 */
import * as pc from 'playcanvas'
import { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { MaterialFactory } from '../rendering/MaterialFactory'
import { InputManager } from '../input/InputManager'
import { ExteriorScene } from './ExteriorScene'
import { InteriorScene } from './InteriorScene'
import { PlayerController } from './PlayerController'
import { OrbitCamera } from './OrbitCamera'
import { DoorTrigger } from './DoorTrigger'
import { SceneTransition } from './SceneTransition'
import { HouseTestUI } from './HouseTestUI'
import type { CollisionBox } from './CollisionSystem'
import type { InteractableId } from './SceneConfig'

// ─── Camera presets ──────────────────────────────────────────────────────────

/**
 * Exterior orbit defaults — camera sits behind and above the player.
 * yaw=0 → camera at +Z (directly behind), pitch=35° elevation, dist=8.6 units.
 */
const CAM_EXT_YAW   = 0
const CAM_EXT_PITCH = 35
const CAM_EXT_DIST  = 8.6

/**
 * Interior: fixed elevated south-facing view over the front wall.
 * Orbit is disabled in interior — camera is locked so the small room is fully visible.
 */
const CAM_INT_YAW   = 0
const CAM_INT_PITCH = 60
const CAM_INT_DIST  = 6

// ─── Player start/exit positions ─────────────────────────────────────────────
// IMPORTANT: spawn positions must be > DoorTrigger.TRIGGER_RADIUS (0.7) away
// from trigger centers to prevent the cooldown-expiry → re-trigger loop.
//   EXIT_CENTER  = (1.5, 0, 3.8)  →  PLAYER_ENTER must be Z ≤ 3.1
//   ENTRY_CENTER = (1.5, 0, 4.7)  →  PLAYER_EXIT  must be Z ≥ 5.4
const PLAYER_START_X = 1.5
const PLAYER_START_Z = 7.0   // outside, in front of door
const PLAYER_ENTER_X = 2.0
const PLAYER_ENTER_Z = 1.5   // back-right area, verified clear of all furniture collision
const PLAYER_EXIT_X  = 1.5
const PLAYER_EXIT_Z  = 6.0   // outside, clear of entry trigger (dist=1.3 > 0.7)


export class HouseTestEngine {
  private application: Application | null = null
  private input: InputManager | null = null
  private loader: AssetLoader | null = null
  private factory: BuildingFactory | null = null

  private exteriorRoot: pc.Entity | null = null
  private interiorRoot: pc.Entity | null = null

  private exterior: ExteriorScene | null = null
  private interior: InteriorScene | null = null
  private player: PlayerController | null = null
  private orbit: OrbitCamera | null = null
  private door: DoorTrigger | null = null
  private transition: SceneTransition | null = null
  private ui: HouseTestUI | null = null

  private scene: 'exterior' | 'interior' = 'exterior'
  private canvas: HTMLCanvasElement | null = null
  private extBoxes: CollisionBox[] = []
  private intBoxes: CollisionBox[] = []

  // E-key state — tracks rising edge so interaction fires once per press
  private _ePrev = false
  // Which interactable seat is currently active (used to clean up TV effect on stand-up)
  private _activeSeatId: InteractableId | null = null

  async init(container: HTMLElement, width: number, height: number): Promise<void> {
    // ── 1. Boot PlayCanvas ───────────────────────────────────────────────────
    this.canvas = document.createElement('canvas')
    Object.assign(this.canvas.style, { width: '100%', height: '100%', display: 'block' })
    container.appendChild(this.canvas)

    this.application = new Application()
    this.application.init(this.canvas, width, height)

    const app = this.application.app
    app.scene.ambientLight = new pc.Color(0.6, 0.6, 0.6)

    // ── 2. Shared systems ────────────────────────────────────────────────────
    this.input = new InputManager()
    this.input.init(this.canvas)

    this.loader  = new AssetLoader(app)
    this.factory = new BuildingFactory(this.loader, new MaterialFactory())

    // ── 3. Scene roots ───────────────────────────────────────────────────────
    this.exteriorRoot = new pc.Entity('Exterior')
    this.interiorRoot = new pc.Entity('Interior')
    app.root.addChild(this.exteriorRoot)
    app.root.addChild(this.interiorRoot)
    this.interiorRoot.enabled = false

    // ── 4. Build scenes (loads GLBs in parallel) ─────────────────────────────
    this.exterior = new ExteriorScene(this.factory)
    this.interior = new InteriorScene(this.factory)

    ;[this.extBoxes, this.intBoxes] = await Promise.all([
      this.exterior.build(this.exteriorRoot),
      this.interior.build(this.interiorRoot),
    ])

    // ── 5. Player ────────────────────────────────────────────────────────────
    this.player = new PlayerController(this.loader, this.input)
    await this.player.init(app.root, PLAYER_START_X, PLAYER_START_Z)
    this.player.setCollisionBoxes(this.extBoxes)

    // ── 5b. Orbit camera ─────────────────────────────────────────────────────
    this.orbit = new OrbitCamera()
    this.orbit.init(this.canvas, this.application.camera, CAM_EXT_YAW, CAM_EXT_PITCH, CAM_EXT_DIST)

    // ── 6. Door trigger + transition ─────────────────────────────────────────
    this.door = new DoorTrigger()
    this.door.onEnter(() => this.enterHouse())
    this.door.onExit(() => this.exitHouse())

    this.transition = new SceneTransition()
    this.transition.init(container)

    // ── 7. Interactables — generic action routing ─────────────────────────────
    for (const item of this.interior.items) {
      item.onUse(() => {
        const { seat } = item
        if (item.action === 'sit'   && seat) this.player?.sitAt(seat.x, seat.z, seat.yaw)
        if (item.action === 'sleep' && seat) this.player?.sleepAt(seat.x, seat.z, seat.yaw)
        this.ui?.showInfo(item.infoText)
        // Track active seat — used to turn off TV effect when player stands up
        this._activeSeatId = item.id
        if (item.id === 'tv') this.interior?.tvEffect.turnOn()
      })
    }

    // ── 8. UI ────────────────────────────────────────────────────────────────
    this.ui = new HouseTestUI()
    this.ui.init(container)
    this.ui.setScene('exterior')

    // ── 9. Position camera for exterior ──────────────────────────────────────
    this.positionExteriorCamera()

    // ── 10. Start loop ───────────────────────────────────────────────────────
    this.application.setConfig({ onUpdate: (dt) => this.onUpdate(dt) })
  }

  private onUpdate(dt: number): void {
    if (!this.player || !this.input || !this.application || !this.door) return

    const camYaw = this.orbit?.yaw ?? 0
    this.player.update(dt, camYaw)

    const playerPos = this.player.getPosition()

    // Door proximity check
    this.door.update(playerPos)

    // E-key interaction (interior only)
    const eDown = this.input.isPressed(pc.KEY_E)
    if (this.scene === 'interior' && this.interior) {
      const eJust = eDown && !this._ePrev
      if (eJust) {
        // If already sitting or sleeping, E exits that state immediately.
        if (this.player?.isSitting)  { this.player.standUp(); }
        else if (this.player?.isSleeping) { this.player.wakeUp(); }
        else {
          // Otherwise find nearest interactable and trigger it.
          for (const item of this.interior.items) {
            if (item.isNear(playerPos)) { item.use(); break }
          }
        }
      }
    }
    this._ePrev = eDown

    // Detect when player leaves a seated/sleeping state (via WASD or E)
    // and clean up any active effects tied to that seat.
    if (this._activeSeatId !== null && !this.player?.isSitting && !this.player?.isSleeping) {
      if (this._activeSeatId === 'tv') this.interior?.tvEffect.turnOff()
      this._activeSeatId = null
    }

    // Drive TV flicker from engine dt — keeps it in sync with the frame loop
    if (this.scene === 'interior') this.interior?.tvEffect.update(dt)

    // Orbit camera follows player every frame in both scenes
    this.orbit?.update(playerPos)
  }

  // ─── Scene transitions ───────────────────────────────────────────────────

  private enterHouse(): void {
    if (!this.transition || this.transition.isActive) return
    void this.transition.perform(() => {
      this.scene = 'interior'
      this.exteriorRoot!.enabled = false
      this.interiorRoot!.enabled = true
      this.player!.setCollisionBoxes(this.intBoxes)
      this.player!.teleport(PLAYER_ENTER_X, PLAYER_ENTER_Z, 180) // +Z-native: yaw=180 → faces -Z (into room)
      this.door!.setScene('interior')
      this.ui?.setScene('interior')
      this.positionInteriorCamera()
    })
  }

  private exitHouse(): void {
    if (!this.transition || this.transition.isActive) return
    void this.transition.perform(() => {
      this.scene = 'exterior'
      this.interiorRoot!.enabled = false
      this.exteriorRoot!.enabled = true
      this.player!.setCollisionBoxes(this.extBoxes)
      if (this.player!.isSitting)  this.player!.standUp()
      if (this.player!.isSleeping) this.player!.wakeUp()
      this.interior?.tvEffect.turnOff()
      this._activeSeatId = null
      this.player!.teleport(PLAYER_EXIT_X, PLAYER_EXIT_Z, 0)   // +Z-native: yaw=0 → faces +Z (away from house)
      this.door!.setScene('exterior')
      this.ui?.setScene('exterior')
      this.ui?.hidePrompt()
      this.positionExteriorCamera()
    })
  }

  // ─── Camera helpers ──────────────────────────────────────────────────────

  private positionExteriorCamera(): void {
    if (!this.orbit || !this.player) return
    // Reset orbit yaw to default (behind player) on exterior entry.
    // Pitch and distance are preserved so the user's zoom level persists.
    this.orbit.setView(CAM_EXT_YAW, CAM_EXT_PITCH, CAM_EXT_DIST)
    this.orbit.update(this.player.getPosition())
  }

  private positionInteriorCamera(): void {
    if (!this.orbit || !this.player) return
    // Snap to an elevated overhead angle; user can orbit freely from there.
    this.orbit.setView(CAM_INT_YAW, CAM_INT_PITCH, CAM_INT_DIST)
    this.orbit.update(this.player.getPosition())
  }

  resize(width: number, height: number): void {
    this.application?.resize(width, height)
  }

  destroy(): void {
    this.transition?.destroy()
    this.ui?.destroy()
    this.player?.destroy()
    this.orbit?.destroy()
    this.door?.destroy()
    this.exterior = null
    this.interior = null
    this.door = null
    this.transition = null
    this.ui = null
    this.player = null
    this.orbit = null
    this.input?.destroy()
    this.input = null
    this.loader = null
    this.factory = null
    this.application?.destroy()
    this.application = null
    this.canvas?.remove()
    this.canvas = null
  }
}
