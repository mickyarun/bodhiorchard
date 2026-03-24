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
 */
import type {
  EngineData,
  EngineCallbacks,
  EngineEvents,
} from './types'
import { Application } from './core/Application'
import { EventBus } from './core/EventBus'
import { InputManager } from './input/InputManager'
import { CameraController } from './camera/CameraController'
import { MaterialFactory } from './rendering/MaterialFactory'
import { SceneManager } from './core/SceneManager'

export { type EngineData, type EngineCallbacks } from './types'

export class GardenEngine {
  private app: Application | null = null
  private input: InputManager | null = null
  private camera: CameraController | null = null
  private materials: MaterialFactory | null = null
  private sceneManager: SceneManager | null = null
  private events: EventBus<EngineEvents>
  private canvas: HTMLCanvasElement | null = null
  private callbacks: EngineCallbacks = {}

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
    this.camera?.update(dt)
    this.sceneManager?.update(dt)
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

    if (this.canvas) {
      this.canvas.remove()
      this.canvas = null
    }
  }
}
