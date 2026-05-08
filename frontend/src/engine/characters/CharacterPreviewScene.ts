// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CharacterPreviewScene — Premium 3D character preview for selection screen.
 *
 * Three-light studio rig (key + spot + rim), dark circular pedestal,
 * turntable camera with smooth transitions on character switch.
 * Standalone PlayCanvas app — no dependency on GardenEngine.
 *
 * Usage:
 *   const scene = new CharacterPreviewScene()
 *   await scene.init(containerElement)
 *   await scene.setCharacter(config)
 *   scene.destroy()
 */
import * as pc from 'playcanvas'
import type { CharacterConfig } from './CharacterConfig'
import { KayKitCharacterFactory, getClonedMaterials } from './KayKitCharacterFactory'
import type { CharacterEntity } from './CharacterTypes'
import { AssetLoader } from '../assets/AssetLoader'
import {
  installContextLossHandlers,
  installVisibilityGate,
  installRenderErrorTrap,
} from '../utils/AppLifecycle'

// ─── Scene Constants ───────────────────────────

const CAMERA_DISTANCE = 2.8
const CAMERA_HEIGHT = 1.2
const CAMERA_TARGET_Y = 0.4
const ROTATION_SPEED = 12          // degrees per second (auto-rotate)
const PEDESTAL_RADIUS = 1.8
const PEDESTAL_HEIGHT = 0.06

// Camera transition timing
const TRANSITION_PULLBACK = 1.4    // distance multiplier during swap
const TRANSITION_OUT_MS = 250      // pull-back duration
const TRANSITION_IN_MS = 400       // ease-in duration

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3
}

export class CharacterPreviewScene {
  private app: pc.Application | null = null
  private canvas: HTMLCanvasElement | null = null
  private camera: pc.Entity | null = null
  private character: CharacterEntity | null = null
  private factory: KayKitCharacterFactory | null = null
  private loader: AssetLoader | null = null
  private cameraAngle = 0
  private isDragging = false
  private lastMouseX = 0

  // Camera transition state
  private cameraDistanceCurrent = CAMERA_DISTANCE
  private cameraDistanceTarget = CAMERA_DISTANCE
  private transitionProgress = 1      // 0→1, 1 = at rest
  private transitionDuration = 0
  private isTransitioning = false

  // Cleanup hooks for context-loss + visibility lifecycle helpers wired
  // in init(). Drained in destroy() so a teardown does not leave dangling
  // canvas-level / document-level listeners pointing at the freed app.
  private lifecycleCleanups: Array<() => void> = []

  /** Initialize the preview scene with premium lighting and pedestal. */
  async init(container: HTMLElement): Promise<void> {
    this.canvas = document.createElement('canvas')
    this.canvas.style.width = '100%'
    this.canvas.style.height = '100%'
    this.canvas.style.display = 'block'
    container.appendChild(this.canvas)

    const w = container.clientWidth || 400
    const h = container.clientHeight || 400

    this.app = new pc.Application(this.canvas, {
      graphicsDeviceOptions: {
        antialias: true,
        alpha: true,
        // Discrete-GPU hint; silent fallback to integrated when none.
        powerPreference: 'high-performance',
      },
    })
    this.app.setCanvasFillMode(pc.FILLMODE_NONE)
    this.app.setCanvasResolution(pc.RESOLUTION_AUTO)
    this.app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio, 2)
    this.app.resizeCanvas(w, h)

    this.lifecycleCleanups.push(
      installContextLossHandlers(this.canvas, this.app as pc.AppBase, 'CharacterPreview'),
      installVisibilityGate(this.app as pc.AppBase),
      installRenderErrorTrap(this.app as pc.AppBase, 'CharacterPreview'),
    )

    // Ambient — bright enough to see face details + slightly cool
    this.app.scene.ambientLight = new pc.Color(0.35, 0.35, 0.4)

    this.setupLighting()
    this.setupCamera()
    this.setupPedestal()

    // Asset loader
    this.loader = new AssetLoader(this.app as pc.AppBase)
    this.factory = new KayKitCharacterFactory(this.loader)

    this.app.on('update', (dt: number) => this.onUpdate(dt))
    this.app.start()

    this.canvas.addEventListener('mousedown', this.onMouseDown)
    this.canvas.addEventListener('mousemove', this.onMouseMove)
    this.canvas.addEventListener('mouseup', this.onMouseUp)
    this.canvas.addEventListener('mouseleave', this.onMouseUp)
  }

  // ─── Three-Light Studio Rig ──────────────────

  private setupLighting(): void {
    if (!this.app) return

    // Key light — warm directional from front-left (illuminates the face)
    const keyLight = new pc.Entity('KeyLight')
    keyLight.addComponent('light', {
      type: 'directional',
      color: new pc.Color(1, 0.95, 0.9),
      intensity: 1.2,
      castShadows: true,
      shadowResolution: 1024,
    })
    keyLight.setEulerAngles(40, -30, 0)
    this.app.root.addChild(keyLight)

    // Spot light — focused pool from above for dramatic effect
    const spotLight = new pc.Entity('SpotLight')
    spotLight.addComponent('light', {
      type: 'spot',
      color: new pc.Color(1, 0.98, 0.95),
      intensity: 3,
      range: 8,
      innerConeAngle: 15,
      outerConeAngle: 35,
      castShadows: true,
      shadowResolution: 512,
    })
    spotLight.setPosition(0.5, 4, 1.5)
    spotLight.setEulerAngles(65, 0, 0)
    this.app.root.addChild(spotLight)

    // Rim light — cool blue from behind for edge highlighting
    const rimLight = new pc.Entity('RimLight')
    rimLight.addComponent('light', {
      type: 'spot',
      color: new pc.Color(0.6, 0.8, 1.0),
      intensity: 2.5,
      range: 6,
      innerConeAngle: 20,
      outerConeAngle: 45,
      castShadows: false,
    })
    rimLight.setPosition(0, 2, -2.5)
    rimLight.setEulerAngles(-30, 180, 0)
    this.app.root.addChild(rimLight)
  }

  // ─── Camera ──────────────────────────────────

  private setupCamera(): void {
    if (!this.app) return

    this.camera = new pc.Entity('Camera')
    this.camera.addComponent('camera', {
      clearColor: new pc.Color(0.08, 0.1, 0.08, 0),
      fov: 32,
    })
    this.updateCameraPosition()
    this.app.root.addChild(this.camera)
  }

  // ─── Dark Circular Pedestal ──────────────────

  private setupPedestal(): void {
    if (!this.app) return

    // Dark slate circular pedestal — ad-hoc material (standalone scene,
    // no MaterialFactory available per CLAUDE.md exception).
    const pedestal = new pc.Entity('Pedestal')
    pedestal.addComponent('render', { type: 'cylinder' })
    pedestal.setLocalScale(PEDESTAL_RADIUS * 2, PEDESTAL_HEIGHT, PEDESTAL_RADIUS * 2)
    pedestal.setPosition(0, -PEDESTAL_HEIGHT / 2, 0)

    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(0.12, 0.14, 0.12)
    mat.metalness = 0.3
    mat.gloss = 0.7
    mat.useMetalness = true
    mat.update()
    pedestal.render!.meshInstances[0].material = mat
    this.app.root.addChild(pedestal)
  }

  // ─── Character Management ────────────────────

  /**
   * Load and display a character with smooth camera transition.
   * Replaces any previously loaded character.
   */
  async setCharacter(config: CharacterConfig): Promise<void> {
    if (!this.app || !this.factory) return

    // Start camera pull-back transition
    if (this.character) {
      this.startTransition(CAMERA_DISTANCE * TRANSITION_PULLBACK, TRANSITION_OUT_MS)

      // Wait for pull-back before swapping model
      await this.waitMs(TRANSITION_OUT_MS)

      // Dispose old character
      const mats = getClonedMaterials(this.character.entity)
      if (mats) {
        for (const mat of mats) mat.destroy()
      }
      this.character.entity.destroy()
      this.character = null
    }

    // Create new character
    this.character = await this.factory.create(
      'preview', '', config,
      0, 0, 0, 0, false,
      true, // skipLabel
    )
    this.app.root.addChild(this.character.entity)

    // Ease camera back in
    this.startTransition(CAMERA_DISTANCE, TRANSITION_IN_MS)
  }

  /** Update color tinting without reloading the character GLB. */
  async updateColors(config: CharacterConfig): Promise<void> {
    await this.setCharacter(config)
  }

  /**
   * Drive the KayKit locomotion state graph's `emote` integer parameter
   * — see `AnimUtils.LOCOMOTION_STATE_GRAPH`. Values:
   *   0 = idle (return to rest)
   *   1 = Wave   (friendly)
   *   2 = Cheer  (winning celebration)
   *
   * No-ops if the current character isn't a KayKit model (legacy blocky
   * characters don't share the state graph).
   */
  setEmote(emote: 0 | 1 | 2 | 3): void {
    const anim = this.character?.entity.anim
    if (!anim) return
    anim.setInteger('emote', emote)
  }

  resize(width: number, height: number): void {
    this.app?.resizeCanvas(width, height)
  }

  destroy(): void {
    this.canvas?.removeEventListener('mousedown', this.onMouseDown)
    this.canvas?.removeEventListener('mousemove', this.onMouseMove)
    this.canvas?.removeEventListener('mouseup', this.onMouseUp)
    this.canvas?.removeEventListener('mouseleave', this.onMouseUp)

    for (const cleanup of this.lifecycleCleanups) cleanup()
    this.lifecycleCleanups = []

    if (this.character) {
      const mats = getClonedMaterials(this.character.entity)
      if (mats) {
        for (const mat of mats) mat.destroy()
      }
      this.character.entity.destroy()
    }
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

  // ─── Camera Transition ───────────────────────

  private startTransition(targetDistance: number, durationMs: number): void {
    this.cameraDistanceTarget = targetDistance
    this.transitionProgress = 0
    this.transitionDuration = durationMs / 1000
    this.isTransitioning = true
  }

  private waitMs(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  // ─── Per-Frame Update ────────────────────────

  private onUpdate(dt: number): void {
    // Auto-rotate (paused during drag)
    if (!this.isDragging) {
      this.cameraAngle += ROTATION_SPEED * dt
    }

    // Camera distance transition
    if (this.isTransitioning && this.transitionDuration > 0) {
      this.transitionProgress = Math.min(1, this.transitionProgress + dt / this.transitionDuration)
      const t = easeOutCubic(this.transitionProgress)
      const startDist = this.cameraDistanceCurrent
      this.cameraDistanceCurrent = startDist + (this.cameraDistanceTarget - startDist) * t

      if (this.transitionProgress >= 1) {
        this.cameraDistanceCurrent = this.cameraDistanceTarget
        this.isTransitioning = false
      }
    }

    this.updateCameraPosition()
  }

  private updateCameraPosition(): void {
    if (!this.camera) return
    const rad = (this.cameraAngle * Math.PI) / 180
    const dist = this.isTransitioning ? this.cameraDistanceCurrent : CAMERA_DISTANCE
    const x = Math.sin(rad) * dist
    const z = Math.cos(rad) * dist
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
