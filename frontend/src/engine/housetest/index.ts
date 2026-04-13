/**
 * HouseTestEngine — Multi-house demo with Rapier physics.
 *
 * Architecture:
 *   app.root
 *   ├── exteriorRoot  (enabled initially)  — ground + 4 house shells
 *   ├── interiorRoot  (disabled initially) — shared interior room
 *   └── playerWrapper (always enabled)     — character entity
 *
 * Exterior uses Rapier physics (wall collision + door colliders).
 * Interior uses manual AABB collision (furniture boxes).
 * Scene swap happens during fade-to-black so the entity toggle is invisible.
 */
import * as pc from 'playcanvas'
import { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { MaterialFactory } from '../rendering/MaterialFactory'
import { InputManager } from '../input/InputManager'
import { ExteriorScene } from './ExteriorScene'
import { InteriorScene } from './InteriorScene'
import { PoolScene } from './PoolScene'
import { PlayerController } from './PlayerController'
import { OrbitCamera } from './OrbitCamera'
import { SceneTransition } from './SceneTransition'
import { HouseTestUI } from './HouseTestUI'
import { PhysicsWorld } from '../physics'
import {
  EXTERIOR_HOUSES,
  HOUSE_EXIT_LOCAL,
  ROOM_SIZE_BY_TIER,
  type InteractableId,
} from './SceneConfig'
import type { CollisionBox } from './CollisionSystem'

// ─── Camera presets ─────────────────────────────────────────────────────────
const CAM_EXT_YAW   = 0
const CAM_EXT_PITCH = 35
const CAM_EXT_DIST  = 12   // wider view for multi-house village

const CAM_INT_YAW   = 0
const CAM_INT_PITCH = 60
const CAM_INT_DIST  = 6

const CAM_POOL_YAW   = 0
const CAM_POOL_PITCH = 45
const CAM_POOL_DIST  = 16

// ─── Player spawn ───────────────────────────────────────────────────────────
const PLAYER_START_X = 3.0   // center of the 2×2 house grid
const PLAYER_START_Z = -2.0  // south of houses, facing them

// Interior spawn (back-right, clear of furniture collision)
const PLAYER_ENTER_X = 2.0
const PLAYER_ENTER_Z = 1.5

export class HouseTestEngine {
  private application: Application | null = null
  private input: InputManager | null = null
  private loader: AssetLoader | null = null
  private factory: BuildingFactory | null = null

  private exteriorRoot: pc.Entity | null = null
  private interiorRoot: pc.Entity | null = null
  private poolRoot: pc.Entity | null = null

  private exterior: ExteriorScene | null = null
  private interior: InteriorScene | null = null
  private pool: PoolScene | null = null
  private player: PlayerController | null = null
  private orbit: OrbitCamera | null = null
  private transition: SceneTransition | null = null
  private ui: HouseTestUI | null = null
  private physics: PhysicsWorld | null = null

  private scene: 'exterior' | 'entering' | 'interior' | 'exiting' | 'pool' = 'exterior'
  private canvas: HTMLCanvasElement | null = null
  private intBoxes: CollisionBox[] = []

  // Multi-house state
  private currentHouseId: string | null = null
  private currentHouseTier = 0
  private doorReEnableTimer: ReturnType<typeof setTimeout> | null = null

  // E-key interaction state
  private _ePrev = false
  private _activeSeatId: InteractableId | null = null

  async init(container: HTMLElement, width: number, height: number): Promise<void> {
    // ── 1. Boot PlayCanvas ──────────────────────────────────────────────────
    this.canvas = document.createElement('canvas')
    Object.assign(this.canvas.style, { width: '100%', height: '100%', display: 'block' })
    container.appendChild(this.canvas)

    this.application = new Application()
    this.application.init(this.canvas, width, height)

    const app = this.application.app
    app.scene.ambientLight = new pc.Color(0.6, 0.6, 0.6)

    // ── 2. Shared systems ───────────────────────────────────────────────────
    this.input = new InputManager()
    this.input.init(this.canvas)

    this.loader  = new AssetLoader(app)
    this.factory = new BuildingFactory(this.loader, new MaterialFactory())

    // ── 3. Initialize Rapier physics (async WASM load) ──────────────────────
    // Zero gravity — top-down movement, no falling
    this.physics = await PhysicsWorld.create({ x: 0, y: 0, z: 0 })

    // ── 4. Scene roots ──────────────────────────────────────────────────────
    this.exteriorRoot = new pc.Entity('Exterior')
    this.interiorRoot = new pc.Entity('Interior')
    this.poolRoot = new pc.Entity('Pool')
    app.root.addChild(this.exteriorRoot)
    app.root.addChild(this.interiorRoot)
    app.root.addChild(this.poolRoot)
    this.interiorRoot.enabled = false
    this.poolRoot.enabled = false

    // ── 5. Build scenes ─────────────────────────────────────────────────────
    this.exterior = new ExteriorScene(this.loader, this.factory.materialFactory ?? undefined)
    // Exterior: builds houses + registers physics (walls + door colliders)
    await this.exterior.build(this.exteriorRoot, this.physics)

    // Interior is built on-demand in enterHouse() with the correct tier

    // Pool: builds umbrella+chair sets with SeatProber detection
    this.pool = new PoolScene(this.loader, new MaterialFactory())
    await this.pool.build(this.poolRoot)

    // ── 6. Player ───────────────────────────────────────────────────────────
    this.player = new PlayerController(this.loader, this.input)
    // Use KayKit character (same as main dashboard) instead of legacy Kenney Blocky
    await this.player.init(app.root, PLAYER_START_X, PLAYER_START_Z, 'kaykit:barbarian:FF6B35:2E4057:F4C28F')

    // Create player physics body (capsule collider)
    this.physics.createPlayer(PLAYER_START_X, PLAYER_START_Z)
    this.player.setPhysics(this.physics)

    // ── 7. Orbit camera ─────────────────────────────────────────────────────
    this.orbit = new OrbitCamera()
    this.orbit.init(this.canvas, this.application.camera, CAM_EXT_YAW, CAM_EXT_PITCH, CAM_EXT_DIST)

    // ── 8. Scene transition ─────────────────────────────────────────────────
    this.transition = new SceneTransition()
    this.transition.init(container)

    // ── 9. Interior interactables — wired on each enterHouse() ──────────────

    // ── 9b. Pool interactables ───────────────────────────────────────────
    for (const item of this.pool.items) {
      item.onUse(() => {
        const { seat } = item
        if (item.action === 'sit' && seat) this.player?.sitAt(seat.x, seat.z, seat.yaw, seat.y)
        this.ui?.showInfo(item.infoText)
        this._activeSeatId = item.id
      })
    }

    // ── 10. UI ──────────────────────────────────────────────────────────────
    this.ui = new HouseTestUI()
    this.ui.init(container)
    this.ui.setScene('exterior')

    // Animation picker — show all available animations for testing
    if (this.player) {
      const states = this.player.getAnimationStates()
      this.ui.showAnimPicker(states)
      this.ui.onAnimSelect = (name) => {
        this.player?.playAnimation(name)
      }
    }

    // ── 11. Camera + loop ───────────────────────────────────────────────────
    this.positionExteriorCamera()
    this.application.setConfig({ onUpdate: (dt) => this.onUpdate(dt) })
  }

  private onUpdate(dt: number): void {
    if (!this.player || !this.input || !this.application || !this.physics) return

    const camYaw = this.orbit?.yaw ?? 0
    this.player.update(dt, camYaw)

    // Billboard labels: rotate to face camera
    const cam = this.application.app.root.findByName('Camera') as pc.Entity | null
    if (cam) {
      const camPos = cam.getPosition()
      const billboards = this.application.app.root.findByTag('billboard') as pc.Entity[]
      for (const b of billboards) {
        const pos = b.getPosition()
        const dx = camPos.x - pos.x
        const dz = camPos.z - pos.z
        const yaw = Math.atan2(dx, dz) * (180 / Math.PI) + 180
        b.setEulerAngles(90, yaw, 0)
      }
    }

    if (this.scene === 'exterior') {
      // Step Rapier AFTER movePlayer (applies kinematic translation + updates narrow phase)
      this.physics.step()
    }

    const playerPos = this.player.getPosition()

    if (this.scene === 'exterior') {
      // Check if player bumped into a door collider
      const doorHit = this.physics.consumeDoorHit()
      if (doorHit) {
        console.log('[HouseTest] Door hit:', doorHit.doorId)
        this.enterHouse(doorHit.doorId)
      }

      // P key → switch to pool scene
      if (this.input.wasPressed(pc.KEY_P)) {
        this.enterPool()
      }
    }

    if (this.scene === 'interior' && this.interior) {
      // E-key interaction
      const eDown = this.input.isPressed(pc.KEY_E)
      const eJust = eDown && !this._ePrev
      if (eJust) {
        if (this.player?.isSitting) { this.player.standUp() }
        else if (this.player?.isSleeping) { this.player.wakeUp() }
        else {
          if (this.interior) {
            for (const item of this.interior.items) {
              if (item.isNear(playerPos)) { item.use(); break }
            }
          }
        }
      }
      this._ePrev = eDown

      // Clean up seated effects on stand-up
      if (this._activeSeatId !== null && !this.player?.isSitting && !this.player?.isSleeping) {
        if (this._activeSeatId === 'tv') this.interior?.tvEffect.turnOff()
        this._activeSeatId = null
      }

      // Proximity prompts for interactable items
      if (this.player?.isSitting || this.player?.isSleeping) {
        this.ui?.hidePrompt()
      } else {
        let nearItem = false
        for (const item of this.interior.items) {
          if (item.isNear(playerPos)) {
            this.ui?.showPrompt(item.promptText)
            nearItem = true
            break
          }
        }
        if (!nearItem) this.ui?.hidePrompt()
      }

      // TV flicker
      this.interior?.tvEffect.update(dt)

      // ESC or door exit — manual AABB DoorTrigger for interior exit
      if (this.input.wasPressed(pc.KEY_ESCAPE)) {
        this.exitHouse()
      }
      // Interior door exit: tier-aware door position from room config
      const roomCfg = ROOM_SIZE_BY_TIER[this.currentHouseTier] ?? ROOM_SIZE_BY_TIER[0]
      const doorZ = roomCfg.depth - 0.2
      const doorX = (roomCfg.doorIndex + 0.5)
      if (playerPos.z > doorZ && Math.abs(playerPos.x - doorX) < 0.7) {
        this.exitHouse()
      }
    }

    if (this.scene === 'pool' && this.pool) {
      // E-key interaction with pool chairs
      const eDown = this.input.isPressed(pc.KEY_E)
      const eJust = eDown && !this._ePrev
      if (eJust) {
        if (this.player?.isSitting) { this.player.standUp() }
        else {
          for (const item of this.pool.items) {
            if (item.isNear(playerPos)) { item.use(); break }
          }
        }
      }
      this._ePrev = eDown

      // Clean up seated state on stand-up
      if (this._activeSeatId !== null && !this.player?.isSitting) {
        this._activeSeatId = null
      }

      // Show/hide prompts for nearby pool chairs
      let nearItem = false
      if (!this.player?.isSitting) {
        for (const item of this.pool.items) {
          if (item.isNear(playerPos)) {
            this.ui?.showPrompt(item.promptText)
            nearItem = true
            break
          }
        }
      }
      if (!nearItem) this.ui?.hidePrompt()

      // ESC → back to exterior
      if (this.input.wasPressed(pc.KEY_ESCAPE)) {
        this.exitPool()
      }
    }

    // Camera follows player
    this.orbit?.update(playerPos)
  }

  // ─── Scene transitions ───────────────────────────────────────────────────

  private enterHouse(houseId: string): void {
    if (!this.transition || this.transition.isActive || this.scene !== 'exterior' || !this.factory) return

    this.currentHouseId = houseId
    this.physics?.setDoorsEnabled(false) // disable door detection during transition

    // Resolve house tier for interior layout
    const house = EXTERIOR_HOUSES.find(h => h.id === houseId)
    const tier = house?.tier ?? 0
    this.currentHouseTier = tier

    this.scene = 'entering'  // prevent re-entrant door collision triggers

    void this.transition.perform(async () => {
      this._activeSeatId = null

      // Destroy all old interior children (snapshot to avoid mutation during iteration)
      if (this.interiorRoot) {
        const oldChildren = [...this.interiorRoot.children] as pc.Entity[]
        for (const child of oldChildren) child.destroy()
      }
      this.interior = new InteriorScene(this.factory)
      this.intBoxes = await this.interior.build(this.interiorRoot!, tier)

      // Wire interactables for this interior
      for (const item of this.interior.items) {
        item.onUse(() => {
          const { seat } = item
          if (item.action === 'sit' && seat) this.player?.sitAt(seat.x, seat.z, seat.yaw, seat.y)
          if (item.action === 'sleep' && seat) this.player?.sleepAt(seat.x, seat.z, seat.yaw, seat.y)
          this.ui?.showInfo(item.infoText)
          this._activeSeatId = item.id
          if (item.id === 'tv') this.interior?.tvEffect.turnOn()
        })
      }

      this.scene = 'interior'
      this.exteriorRoot!.enabled = false
      this.interiorRoot!.enabled = true

      // Switch to manual AABB collision for interior
      this.player!.setCollisionBoxes(this.intBoxes)
      this.player!.teleport(PLAYER_ENTER_X, PLAYER_ENTER_Z, 180)

      this._ePrev = true  // suppress false E-key edge on first interior frame
      this.ui?.setScene('interior')
      this.positionInteriorCamera()
    })
  }

  private exitHouse(): void {
    if (!this.transition || this.transition.isActive || this.scene !== 'interior') return

    this.scene = 'exiting'  // prevent re-entrant calls from door proximity check

    // Find the house we entered to compute exit position
    const house = EXTERIOR_HOUSES.find(h => h.id === this.currentHouseId)
    const exitX = (house?.x ?? 0) + HOUSE_EXIT_LOCAL.x
    const exitZ = (house?.z ?? 0) + HOUSE_EXIT_LOCAL.z

    void this.transition.perform(() => {
      this.scene = 'exterior'
      this.interiorRoot!.enabled = false
      this.exteriorRoot!.enabled = true

      // Clean up interior state
      if (this.player!.isSitting)  this.player!.standUp()
      if (this.player!.isSleeping) this.player!.wakeUp()
      this.interior?.tvEffect.turnOff()
      this._activeSeatId = null

      // Switch back to Rapier physics + teleport outside the correct house
      this.player!.setPhysics(this.physics)
      this.player!.teleport(exitX, exitZ, 0)
      this.physics?.teleportPlayer(exitX, exitZ)

      // Re-enable door detection after a delay to prevent re-trigger
      this.doorReEnableTimer = setTimeout(() => {
        this.physics?.setDoorsEnabled(true)
        this.doorReEnableTimer = null
      }, 500)

      this.ui?.setScene('exterior')
      this.ui?.hidePrompt()
      this.positionExteriorCamera()
      this.currentHouseId = null
    })
  }

  // ─── Pool scene transitions ──────────────────────────────────────────

  private enterPool(): void {
    if (!this.transition || this.transition.isActive || this.scene !== 'exterior') return

    this.physics?.setDoorsEnabled(false)
    this.scene = 'entering'

    void this.transition.perform(() => {
      this.scene = 'pool'
      this.exteriorRoot!.enabled = false
      this.interiorRoot!.enabled = false
      this.poolRoot!.enabled = true

      // No collision boxes for pool — open area
      this.player!.setCollisionBoxes([])
      this.player!.teleport(0, -3, 0) // south of pool, facing chairs

      this._ePrev = true
      this.ui?.setScene('pool')
      this.positionPoolCamera()
    })
  }

  private exitPool(): void {
    if (!this.transition || this.transition.isActive || this.scene !== 'pool') return

    this.scene = 'exiting'

    void this.transition.perform(() => {
      this.scene = 'exterior'
      this.poolRoot!.enabled = false
      this.exteriorRoot!.enabled = true

      if (this.player!.isSitting) this.player!.standUp()
      this._activeSeatId = null

      this.player!.setPhysics(this.physics)
      this.player!.teleport(PLAYER_START_X, PLAYER_START_Z, 0)
      this.physics?.teleportPlayer(PLAYER_START_X, PLAYER_START_Z)

      this.doorReEnableTimer = setTimeout(() => {
        this.physics?.setDoorsEnabled(true)
        this.doorReEnableTimer = null
      }, 500)

      this.ui?.setScene('exterior')
      this.ui?.hidePrompt()
      this.positionExteriorCamera()
    })
  }

  // ─── Camera helpers ──────────────────────────────────────────────────────

  private positionExteriorCamera(): void {
    if (!this.orbit || !this.player) return
    this.orbit.setView(CAM_EXT_YAW, CAM_EXT_PITCH, CAM_EXT_DIST)
    this.orbit.update(this.player.getPosition())
  }

  private positionInteriorCamera(): void {
    if (!this.orbit || !this.player) return
    this.orbit.setView(CAM_INT_YAW, CAM_INT_PITCH, CAM_INT_DIST)
    this.orbit.update(this.player.getPosition())
  }

  private positionPoolCamera(): void {
    if (!this.orbit || !this.player) return
    this.orbit.setView(CAM_POOL_YAW, CAM_POOL_PITCH, CAM_POOL_DIST)
    this.orbit.update(this.player.getPosition())
  }

  resize(width: number, height: number): void {
    this.application?.resize(width, height)
  }

  destroy(): void {
    if (this.doorReEnableTimer !== null) {
      clearTimeout(this.doorReEnableTimer)
      this.doorReEnableTimer = null
    }
    this.transition?.destroy()
    this.ui?.destroy()
    this.player?.destroy()
    this.orbit?.destroy()
    this.physics?.destroy()
    this.exterior = null
    this.interior = null
    this.transition = null
    this.ui = null
    this.player = null
    this.orbit = null
    this.physics = null
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
