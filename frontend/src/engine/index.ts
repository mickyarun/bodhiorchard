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

export { type EngineData, type EngineCallbacks } from './types'

type SceneState = 'garden' | 'entering' | 'interior' | 'exiting'

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
  }

  /** Helper — wait for a duration (used to let camera fly-to complete). */
  private waitForTransition(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  /** Handle a real-time agent activity event from WebSocket. */
  handleAgentActivity(activity: import('./types').EngineAgentActivity): void {
    this.sceneManager?.agentSystemRef?.handleLiveEvent(activity)
  }

  /** Handle a real-time dev activity event from WebSocket. */
  handleDevActivity(activity: import('./types').EngineDevActivity): void {
    this.sceneManager?.characterSystemRef?.handleDevActivity(activity)
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
