/**
 * GardenEngine — Public API for the 3D garden visualization engine.
 *
 * This is the ONLY entry point the Vue layer uses.
 * Zero imports from @/stores, @/types, @/views.
 *
 * API:
 *   init(container, width, height, callbacks?) — boots PlayCanvas app
 *   setData(data)                              — receives engine data, builds scene
 *   resize(width, height)                      — handles viewport resize
 *   destroy()                                  — full cleanup
 *   toggleArcs()                               — toggle relationship arc visibility
 *   focusOnRepo(repoName)                      — focus camera on a tree
 *   clearFocus()                               — show all trees
 *   enterHouse(memberId)                       — enter a house interior
 *   exitHouse()                                — exit back to garden
 */
import * as pc from 'playcanvas'
import type {
  EngineData,
  EngineCallbacks,
  EngineEvents,
} from './types'
import { Application } from './core/Application'
import { EventBus } from './core/EventBus'
import { InputManager } from './input/InputManager'
import { CameraController, type CameraState } from './camera/CameraController'
import { MaterialFactory } from './rendering/MaterialFactory'
import { SceneManager } from './core/SceneManager'
import { TreePickerSystem } from './interaction/TreePickerSystem'
import { InteriorManager } from './interior'
import {
  TakeoverController,
  TakeoverCamera,
  TakeoverUI,
  ProximitySystem,
  loadTakeoverAnimations,
  restoreLocomotionAnimations,
  type HouseDoor,
} from './takeover'

export { type EngineData, type EngineCallbacks } from './types'

type SceneState = 'garden' | 'entering' | 'interior' | 'exiting' | 'takeover'

export class GardenEngine {
  private app: Application | null = null
  private input: InputManager | null = null
  private camera: CameraController | null = null
  private materials: MaterialFactory | null = null
  private sceneManager: SceneManager | null = null
  private events: EventBus<EngineEvents>
  private canvas: HTMLCanvasElement | null = null
  private callbacks: EngineCallbacks = {}
  private picker: TreePickerSystem | null = null

  // Interior exploration
  private interior: InteriorManager | null = null
  private sceneState: SceneState = 'garden'
  private savedCameraState: CameraState | null = null
  private _interiorMemberId: string | null = null

  // Garden takeover (player controls their character)
  private takeoverCtrl: TakeoverController | null = null
  private takeoverCam: TakeoverCamera | null = null
  private takeoverUI: TakeoverUI | null = null
  private takeoverProximity: ProximitySystem | null = null
  private takeoverUserId: string | null = null

  constructor() {
    this.events = new EventBus<EngineEvents>()
  }

  /**
   * Initialize the PlayCanvas application.
   * Creates canvas, boots the app with proper PBR lighting, sets up input + camera.
   */
  async init(
    container: HTMLElement,
    width: number,
    height: number,
    callbacks?: EngineCallbacks,
  ): Promise<void> {
    this.callbacks = callbacks ?? {}

    // Create canvas
    this.canvas = document.createElement('canvas')
    this.canvas.style.width = '100%'
    this.canvas.style.height = '100%'
    this.canvas.style.display = 'block'
    container.appendChild(this.canvas)

    // Boot core app with proper PBR lighting pipeline
    this.app = new Application()
    this.app.init(this.canvas, width, height)

    // Input manager
    this.input = new InputManager()
    this.input.init(this.canvas)

    // Camera controller
    this.camera = new CameraController()
    this.camera.init(this.app.camera, this.input)

    // Material factory
    this.materials = new MaterialFactory()

    // Scene manager — orchestrates all Phase 2+ subsystems
    this.sceneManager = new SceneManager(this.app, this.materials)

    // Picking system — hover tooltips + click for repo/feature entities
    this.picker = new TreePickerSystem()

    // Interior manager — house exploration mode
    this.interior = new InteriorManager(
      this.app, this.input, this.materials, this.canvas, container,
    )
    this.interior.onExit = () => this.exitHouse()

    // Wire up frame update
    this.app.setConfig({
      onUpdate: (dt) => this.onUpdate(dt),
    })

    // Show controls help overlay (auto-fades after 6s)
    this.camera.showControlsHelp(container)

    this.callbacks.onSceneReady?.()
  }

  /**
   * Receive engine data and build/rebuild the scene.
   * SceneManager handles the full build pipeline.
   */
  async setData(data: EngineData): Promise<void> {
    if (!this.app || !this.sceneManager) return
    this.events.emit('data:set', data)
    await this.sceneManager.rebuild(data)
  }

  /** Per-frame update — called by core app. */
  private onUpdate(dt: number): void {
    switch (this.sceneState) {
      case 'garden':
        this.camera?.update(dt)
        this.sceneManager?.update(dt)
        if (this.picker && this.app && this.input) {
          const pickables = this.sceneManager?.getPickableEntities() ?? []
          this.picker.update(this.app.camera, this.input, pickables, this.callbacks)
        }
        break

      case 'interior':
        this.interior?.update(dt)
        // Skip sceneManager.update() — garden animations (birds, clouds, trees)
        // are invisible during interior mode and waste CPU cycles.
        break

      case 'takeover':
        // Garden stays alive — birds, clouds, agent robots, other characters
        this.sceneManager?.update(dt)
        if (this.takeoverCtrl && this.takeoverCam) {
          this.takeoverCtrl.update(dt, this.takeoverCam.yaw)
          this.takeoverCam.update(this.takeoverCtrl.getPosition())

          // Proximity detection
          if (this.takeoverProximity && this.takeoverUI && this.takeoverUserId) {
            const chars = this.sceneManager?.characterSystemRef?.getCharacters() ?? []
            this.takeoverProximity.update(
              this.takeoverCtrl.getPosition(),
              this.takeoverUserId,
              chars,
              this.takeoverUI,
            )
          }

          // Inactivity warning / auto-exit
          if (this.takeoverCtrl.showWarning) {
            this.takeoverUI?.showWarning(this.takeoverCtrl.warningSecondsLeft)
          } else {
            this.takeoverUI?.hideWarning()
          }

          // Exit triggers — guard with 'exiting' to prevent re-entrant async calls
          if (this.takeoverCtrl.isInactive) {
            this.sceneState = 'exiting'
            this.exitTakeover().catch(e => console.error('[GardenEngine] auto-exit failed:', e))
          } else {
            const door = this.takeoverCtrl.consumeTriggeredDoor()
            if (door) {
              this.sceneState = 'exiting'
              this.exitTakeover()
                .then(() => this.enterHouse(door.memberId))
                .catch(e => console.error('[GardenEngine] door entry failed:', e))
            } else if (this.input?.wasPressed(pc.KEY_ESCAPE)) {
              this.sceneState = 'exiting'
              this.exitTakeover().catch(e => console.error('[GardenEngine] ESC exit failed:', e))
            }
          }
        }
        break

      case 'entering':
      case 'exiting':
        // Transitions in progress — let camera complete any fly-to, skip input
        this.camera?.update(dt)
        break
    }
  }

  // ─── Interior exploration ─────────────────────────────

  /** Enter a house interior by member ID. */
  async enterHouse(memberId: string): Promise<void> {
    if (this.sceneState !== 'garden' || !this.camera || !this.interior || !this.sceneManager) return
    const house = this.sceneManager.memberHouseMap.get(memberId)
    if (!house) return

    this.sceneState = 'entering'
    this._interiorMemberId = memberId
    this.savedCameraState = this.camera.saveState()

    // Fly camera to house position
    const housePos = house.entity.getPosition()
    this.camera.focusOnPosition(housePos, 8)

    // Wait for fly-to transition, then fade to interior
    await this.waitForTransition(800)

    try {
      await this.interior.sceneTransition.perform(async () => {
        // Hide garden world — grass, rocks, trees, buildings all disappear
        const gardenRoot = this.sceneManager?.gardenRootEntity
        if (gardenRoot) gardenRoot.enabled = false

        this.camera!.disable()
        await this.interior!.enter(house)
        this.sceneState = 'interior'
        this.events.emit('interior:enter', { memberId, memberName: house.memberName })
      })
    } catch (err) {
      // Recover from failed transition — don't leave sceneState stuck
      console.error('[GardenEngine] Failed to enter house:', err)
      this.sceneState = 'garden'
      this._interiorMemberId = null
      this.camera.enable()
      const gardenRoot = this.sceneManager?.gardenRootEntity
      if (gardenRoot) gardenRoot.enabled = true
      if (this.savedCameraState) {
        this.camera.restoreState(this.savedCameraState)
        this.savedCameraState = null
      }
    }
  }

  /** Exit the house interior back to garden. */
  async exitHouse(): Promise<void> {
    if (this.sceneState !== 'interior' || !this.camera || !this.interior) return

    // Remember which house we're exiting (for takeover spawn position)
    const exitMemberId = this._interiorMemberId

    this.sceneState = 'exiting'

    await this.interior.sceneTransition.perform(() => {
      this.interior!.exit()

      // Restore garden world visibility
      const gardenRoot = this.sceneManager?.gardenRootEntity
      if (gardenRoot) gardenRoot.enabled = true

      this.camera!.enable()
      if (this.savedCameraState) {
        this.camera!.restoreState(this.savedCameraState)
        this.savedCameraState = null
      }
      this.sceneState = 'garden'
      this.events.emit('interior:exit')
    })

    // After exiting house, enter takeover mode with character at the door
    this._interiorMemberId = null
    if (exitMemberId) {
      // Spawn at the housing village gate (edge of zone, facing orchard center)
      // This avoids getting trapped between tightly packed houses
      const character = this.sceneManager?.characterSystemRef?.getCharacter(exitMemberId)
      if (character) {
        const zones = this.sceneManager!.worldLayout.getAllZones()
        const housingZone = zones.find(z => z.name === 'housing')
        if (housingZone) {
          // Gate position: edge of housing zone, toward orchard (0,0)
          const toCenter = Math.atan2(-housingZone.x, -housingZone.z)
          const gateX = housingZone.x + Math.sin(toCenter) * (housingZone.radius + 2)
          const gateZ = housingZone.z + Math.cos(toCenter) * (housingZone.radius + 2)
          character.entity.setPosition(gateX, 0, gateZ)
          character.entity.setEulerAngles(0, toCenter * (180 / Math.PI), 0)
        }
        character.entity.anim?.setBoolean('sitting', false)
        character.entity.anim?.setInteger('speed', 0)
      }
      await this.takeoverCharacter(exitMemberId)
    }
  }

  /** Helper — wait for a duration (used to let camera fly-to complete). */
  private waitForTransition(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  // ─── Garden takeover ─────────────────────────────

  /**
   * Take control of a character in the garden.
   * Camera follows the character, WASD drives movement.
   * @param userId - The member's user_id (must match a character in the scene)
   */
  async takeoverCharacter(userId: string): Promise<void> {
    if (this.sceneState !== 'garden' || !this.camera || !this.input || !this.sceneManager || !this.app) return

    const charSystem = this.sceneManager.characterSystemRef
    if (!charSystem) return

    const character = charSystem.getCharacter(userId)
    if (!character) {
      console.warn('[GardenEngine] takeoverCharacter: character not found for', userId)
      return
    }

    // If character is sitting at their desk, go straight to house interior mode
    const isSitting = character.entity.anim?.getBoolean('sitting') ?? false
    if (isSitting && this.sceneManager.memberHouseMap.has(userId)) {
      console.debug('[GardenEngine] Character sitting at desk → entering interior mode')
      this.enterHouse(userId)
      return
    }

    this.takeoverUserId = userId

    // Save camera state for restoration
    this.savedCameraState = this.camera.saveState()
    this.camera.disable()

    // Block NPC AI for this character
    charSystem.setTakeoverUser(userId)

    // Load extended animations (Sprint, Jump)
    try {
      await loadTakeoverAnimations(character.entity, this.sceneManager.assetLoader)
    } catch (err) {
      console.warn('[GardenEngine] Failed to load takeover animations:', err)
      // Continue anyway — walk/idle will still work from the extended state graph
    }

    // Initialize takeover systems
    this.takeoverCtrl = new TakeoverController(this.input)
    this.takeoverCtrl.setWorldRadius(this.sceneManager.worldLayout.getWorldRadius() + 6)

    // Build per-house collision zones (small circles) instead of the huge
    // village-wide exclusion zone which blocks walking between houses.
    // Also build per-building zones from layout exclusions, but skip
    // the housing zone (its radius covers the entire village).
    const houseCollisions: { x: number; z: number; radius: number }[] = []
    const houseDoors: HouseDoor[] = []
    for (const [memberId, house] of this.sceneManager.memberHouseMap) {
      const pos = house.entity.getPosition()
      // Each house is ~4×4 units, radius 2.5 covers footprint + small buffer
      houseCollisions.push({ x: pos.x, z: pos.z, radius: 2.5 })

      // Door trigger for ALL houses — walk up to any door to enter interior
      const toCenter = Math.atan2(-pos.x, -pos.z)
      houseDoors.push({
        memberId,
        name: house.memberName,
        x: pos.x + Math.sin(toCenter) * 3.0,
        z: pos.z + Math.cos(toCenter) * 3.0,
      })
    }

    // Build AABB collision boxes from house circle approximations
    // (will be replaced by Rapier physics after housetest prototype)
    const collisionBoxes = houseCollisions.map(h => ({
      minX: h.x - h.radius, maxX: h.x + h.radius,
      minZ: h.z - h.radius, maxZ: h.z + h.radius,
    }))
    this.takeoverCtrl.setCollisionBoxes(collisionBoxes)
    this.takeoverCtrl.setHouseDoors(houseDoors)
    this.takeoverCtrl.enter(character.entity)

    this.takeoverCam = new TakeoverCamera()
    this.takeoverCam.enable(this.app.camera, this.canvas!)

    this.takeoverUI = new TakeoverUI()
    this.takeoverUI.init(this.canvas!.parentElement!)
    this.takeoverUI.onExitClick = () => this.exitTakeover()
    this.takeoverUI.show()

    this.takeoverProximity = new ProximitySystem()

    this.sceneState = 'takeover'
    console.debug('[GardenEngine] Entered takeover mode for', userId)
  }

  /** Exit takeover mode — restore camera and resume NPC behavior. */
  async exitTakeover(): Promise<void> {
    if (this.sceneState !== 'takeover') return

    const character = this.takeoverUserId
      ? this.sceneManager?.characterSystemRef?.getCharacter(this.takeoverUserId)
      : null

    // Exit controller (restores entity position/anim)
    this.takeoverCtrl?.exit()
    this.takeoverCtrl = null

    // Restore locomotion animations
    if (character && this.sceneManager) {
      try {
        await restoreLocomotionAnimations(character.entity, this.sceneManager.assetLoader)
      } catch (err) {
        console.warn('[GardenEngine] Failed to restore locomotion animations:', err)
      }
    }

    // Disable takeover camera and UI
    this.takeoverCam?.disable()
    this.takeoverCam = null
    this.takeoverUI?.hide()
    this.takeoverUI?.destroy()
    this.takeoverUI = null
    this.takeoverProximity?.reset()
    this.takeoverProximity = null

    // Resume NPC AI
    this.sceneManager?.characterSystemRef?.setTakeoverUser(null)

    // Restore garden camera
    if (this.camera) {
      this.camera.enable()
      if (this.savedCameraState) {
        this.camera.restoreState(this.savedCameraState)
        this.savedCameraState = null
      }
    }

    this.sceneState = 'garden'
    this.takeoverUserId = null
    console.debug('[GardenEngine] Exited takeover mode')
  }

  /** Whether the engine is currently in takeover mode. */
  get isTakeover(): boolean { return this.sceneState === 'takeover' }

  /** Handle a real-time agent activity event from WebSocket. */
  handleAgentActivity(activity: import('./types').EngineAgentActivity): void {
    this.sceneManager?.agentSystemRef?.handleLiveEvent(activity)
  }

  /** Handle a real-time dev activity event from WebSocket. */
  handleDevActivity(activity: import('./types').EngineDevActivity): void {
    console.debug('[GardenEngine] handleDevActivity',
      activity.event_type, activity.user_id, activity.repo_name)
    if (!this.sceneManager?.characterSystemRef) {
      console.debug('[GardenEngine] characterSystemRef not available (scene not built yet?)')
      return
    }
    this.sceneManager.characterSystemRef.handleDevActivity(activity)
  }

  /** Toggle relationship arc visibility. Returns new visible state. */
  toggleArcs(): boolean {
    return this.sceneManager?.toggleArcs() ?? false
  }

  /** Focus camera on a specific tree. */
  focusOnRepo(repoName: string): void {
    if (!this.sceneManager || !this.camera) return
    const pos = this.sceneManager.getTreePosition(repoName)
    if (pos) {
      this.camera.focusOnPosition(pos, 15)
    }
  }

  /** Clear tree focus — return to overview. */
  clearFocus(): void {
    this.camera?.setOverviewMode()
  }

  /** Get internal references for Phase 3+ integration. */
  get scene(): SceneManager | null { return this.sceneManager }
  get cameraController(): CameraController | null { return this.camera }
  get inputManager(): InputManager | null { return this.input }
  get application(): Application | null { return this.app }
  get materialFactory(): MaterialFactory | null { return this.materials }

  resize(width: number, height: number): void {
    this.app?.resize(width, height)
  }

  destroy(): void {
    // Clean up takeover if active
    this.takeoverCtrl?.exit()
    this.takeoverCtrl = null
    this.takeoverCam?.destroy()
    this.takeoverCam = null
    this.takeoverUI?.destroy()
    this.takeoverUI = null
    this.takeoverProximity = null
    this.takeoverUserId = null

    this.interior?.destroy()
    this.interior = null
    this.picker = null
    this.sceneManager?.destroy()
    this.sceneManager = null
    this.events.clear()
    this.materials?.clear()
    this.materials = null
    this.input?.destroy()
    this.input = null
    this.camera?.destroyHelp()
    this.camera = null
    this.app?.destroy()
    this.app = null
    this.sceneState = 'garden'
    this.savedCameraState = null

    if (this.canvas) {
      this.canvas.remove()
      this.canvas = null
    }
  }
}
