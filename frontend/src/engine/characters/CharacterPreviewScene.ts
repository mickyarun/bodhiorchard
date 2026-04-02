/**
 * CharacterPreviewScene — Lightweight PlayCanvas scene for character selection.
 *
 * Boots a minimal PlayCanvas app with a single character, ground plane,
 * directional light, and turntable camera. Designed for fast startup (~500ms)
 * without loading the full GardenEngine (which takes 3-5s for trees, buildings, etc.).
 *
 * Usage:
 *   const scene = new CharacterPreviewScene()
 *   await scene.init(containerElement)
 *   await scene.setCharacter(config)
 *   scene.destroy()
 */
import * as pc from 'playcanvas'
import type { CharacterConfig } from './CharacterConfig'
import { KayKitCharacterFactory } from './KayKitCharacterFactory'
import type { CharacterEntity } from './CharacterFactory'
import { AssetLoader } from '../assets/AssetLoader'

// ─── Scene Constants ───────────────────────────

const CAMERA_DISTANCE = 3.0
const CAMERA_HEIGHT = 1.5
const CAMERA_TARGET_Y = 0.5
const ROTATION_SPEED = 15     // degrees per second (auto-rotate)
const GROUND_SIZE = 4

export class CharacterPreviewScene {
  private app: pc.Application | null = null
  private canvas: HTMLCanvasElement | null = null
  private camera: pc.Entity | null = null
  private light: pc.Entity | null = null
  private ground: pc.Entity | null = null
  private character: CharacterEntity | null = null
  private factory: KayKitCharacterFactory | null = null
  private loader: AssetLoader | null = null
  private cameraAngle = 0
  private isDragging = false
  private lastMouseX = 0

  /**
   * Initialize the preview scene inside a container element.
   * Creates canvas, boots PlayCanvas, sets up lighting and camera.
   */
  async init(container: HTMLElement): Promise<void> {
    // Create canvas
    this.canvas = document.createElement('canvas')
    this.canvas.style.width = '100%'
    this.canvas.style.height = '100%'
    this.canvas.style.display = 'block'
    container.appendChild(this.canvas)

    const w = container.clientWidth || 400
    const h = container.clientHeight || 400

    // Boot minimal PlayCanvas app
    this.app = new pc.Application(this.canvas, {
      graphicsDeviceOptions: { antialias: true, alpha: true },
    })
    this.app.setCanvasFillMode(pc.FILLMODE_NONE)
    this.app.setCanvasResolution(pc.RESOLUTION_AUTO)
    this.app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio, 2)
    this.app.resizeCanvas(w, h)

    // Ambient light
    this.app.scene.ambientLight = new pc.Color(0.4, 0.4, 0.45)

    // Directional light
    this.light = new pc.Entity('Light')
    this.light.addComponent('light', {
      type: 'directional',
      color: new pc.Color(1, 0.95, 0.9),
      intensity: 1.2,
      castShadows: true,
      shadowResolution: 1024,
    })
    this.light.setEulerAngles(45, 135, 0)
    this.app.root.addChild(this.light)

    // Camera
    this.camera = new pc.Entity('Camera')
    this.camera.addComponent('camera', {
      clearColor: new pc.Color(0.15, 0.15, 0.2, 0),
      fov: 35,
    })
    this.updateCameraPosition()
    this.app.root.addChild(this.camera)

    // Ground plane — ad-hoc material is intentional: this is a standalone mini
    // PlayCanvas app separate from GardenEngine, so MaterialFactory is unavailable.
    this.ground = new pc.Entity('Ground')
    this.ground.addComponent('render', { type: 'plane' })
    this.ground.setLocalScale(GROUND_SIZE, 1, GROUND_SIZE)
    const groundMat = new pc.StandardMaterial()
    groundMat.diffuse = new pc.Color(0.25, 0.3, 0.2)
    groundMat.update()
    this.ground.render!.meshInstances[0].material = groundMat
    this.app.root.addChild(this.ground)

    // Asset loader (uses the raw pc.Application, not the engine wrapper)
    this.loader = new AssetLoader(this.app as pc.AppBase)
    this.factory = new KayKitCharacterFactory(this.loader)

    // Per-frame update
    this.app.on('update', (dt: number) => this.onUpdate(dt))
    this.app.start()

    // Mouse drag for manual rotation
    this.canvas.addEventListener('mousedown', this.onMouseDown)
    this.canvas.addEventListener('mousemove', this.onMouseMove)
    this.canvas.addEventListener('mouseup', this.onMouseUp)
    this.canvas.addEventListener('mouseleave', this.onMouseUp)
  }

  /**
   * Load and display a character with the given config.
   * Replaces any previously loaded character.
   */
  async setCharacter(config: CharacterConfig): Promise<void> {
    if (!this.app || !this.factory) return

    // Remove previous character
    if (this.character) {
      this.character.entity.destroy()
      this.character = null
    }

    this.character = await this.factory.create(
      'preview', '', config,
      0, 0, 0, 0, false,
      true, // skipLabel — preview doesn't need name billboard
    )

    this.app.root.addChild(this.character.entity)
  }

  /** Update color tinting without reloading the character GLB. */
  async updateColors(config: CharacterConfig): Promise<void> {
    // Full reload is fast enough since GLB is cached
    await this.setCharacter(config)
  }

  /** Resize the canvas to match container. */
  resize(width: number, height: number): void {
    this.app?.resizeCanvas(width, height)
  }

  /** Clean up all resources. */
  destroy(): void {
    this.canvas?.removeEventListener('mousedown', this.onMouseDown)
    this.canvas?.removeEventListener('mousemove', this.onMouseMove)
    this.canvas?.removeEventListener('mouseup', this.onMouseUp)
    this.canvas?.removeEventListener('mouseleave', this.onMouseUp)

    this.character?.entity.destroy()
    this.character = null
    this.factory?.clear()
    this.factory = null
    this.loader = null
    this.app?.destroy()
    this.app = null

    if (this.canvas) {
      this.canvas.remove()
      this.canvas = null
    }
  }

  // ─── Private ─────────────────────────────────

  private onUpdate(dt: number): void {
    if (!this.isDragging) {
      this.cameraAngle += ROTATION_SPEED * dt
    }
    this.updateCameraPosition()
  }

  private updateCameraPosition(): void {
    if (!this.camera) return
    const rad = (this.cameraAngle * Math.PI) / 180
    const x = Math.sin(rad) * CAMERA_DISTANCE
    const z = Math.cos(rad) * CAMERA_DISTANCE
    this.camera.setPosition(x, CAMERA_HEIGHT, z)
    this.camera.lookAt(0, CAMERA_TARGET_Y, 0)
  }

  // ─── Mouse handlers (arrow functions for stable `this`) ──

  private onMouseDown = (e: MouseEvent): void => {
    this.isDragging = true
    this.lastMouseX = e.clientX
  }

  private onMouseMove = (e: MouseEvent): void => {
    if (!this.isDragging) return
    const dx = e.clientX - this.lastMouseX
    this.cameraAngle -= dx * 0.5
    this.lastMouseX = e.clientX
  }

  private onMouseUp = (): void => {
    this.isDragging = false
  }
}
