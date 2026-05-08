// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Application — PlayCanvas bootstrap with proper PBR lighting.
 *
 * Key differences from old App.ts:
 * - ACES tone mapping + sRGB gamma → correct GLTF colors (no more black characters)
 * - Procedural cubemap (128x128) for IBL → proper reflections/shading
 * - Exposure control (1.2) for brighter outdoor scene
 * - Billboard registry (O(1) add/remove) instead of O(n) findByTag per frame
 * - Drives per-frame update via callback
 */
import * as pc from 'playcanvas'
import { Clock } from './Clock'
import { EventBus } from './EventBus'
import type { EngineEvents } from '../types'
import {
  installContextLossHandlers,
  installVisibilityGate,
  installRenderErrorTrap,
} from '../utils/AppLifecycle'

export interface ApplicationConfig {
  onUpdate?: (dt: number, clock: Clock) => void
}

export class Application {
  app!: pc.AppBase
  camera!: pc.Entity
  sun!: pc.Entity
  root!: pc.Entity
  clock: Clock
  events: EventBus<EngineEvents>

  private config: ApplicationConfig = {}

  /**
   * Bound update handler held as a private ref so `stopUpdates()` can
   * remove exactly this listener via `app.off('update', ref)` instead of
   * the arg-less `app.off('update')` that strips every listener registered
   * against the event name. Lets future subsystems register their own
   * update listeners without our teardown sweeping them away.
   */
  private updateHandler: ((dt: number) => void) | null = null

  /**
   * Cleanup hooks for the lifecycle hardening helpers wired in `init()`.
   * Called from `destroy()` so a teardown does not leave dangling
   * canvas-level / document-level listeners pointing at a freed
   * pc.Application.
   */
  private lifecycleCleanups: Array<() => void> = []

  /**
   * Billboard registry — O(1) add/remove, avoids O(n) findByTag every frame.
   * Subsystems call registerBillboard/unregisterBillboard when creating/destroying labels.
   */
  private billboards = new Set<pc.Entity>()
  // Cached camera position from the previous frame's billboard pass. When the
  // camera hasn't moved (within epsilon) the entire billboard loop is a no-op
  // — the labels already face the camera correctly. With 150–300 billboards
  // in a typical scene this is the single largest per-frame win in steady state.
  private lastBillboardCamPos = new pc.Vec3(Infinity, Infinity, Infinity)

  constructor() {
    this.clock = new Clock()
    this.events = new EventBus<EngineEvents>()
  }

  init(canvas: HTMLCanvasElement, width: number, height: number): void {
    this.app = new pc.Application(canvas, {
      graphicsDeviceOptions: {
        antialias: true,
        alpha: false,
        preserveDrawingBuffer: false,
        // Ask the browser for the discrete GPU on systems that have one.
        // Silent fallback to integrated when no dGPU exists, so this is
        // zero-risk on every machine the app might be opened on.
        powerPreference: 'high-performance',
      },
    })

    this.app.setCanvasFillMode(pc.FILLMODE_NONE)
    this.app.setCanvasResolution(pc.RESOLUTION_AUTO)
    this.app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio, 2)
    this.app.resizeCanvas(width, height)

    this.lifecycleCleanups.push(
      installContextLossHandlers(canvas, this.app, 'Application'),
      installVisibilityGate(this.app),
      installRenderErrorTrap(this.app, 'Application'),
    )

    // ─── Scene lighting: THE fix for black models ─────────────
    // Slightly warm ambient tint for golden-hour feel (was cool 0.4/0.4/0.45).
    this.app.scene.ambientLight = new pc.Color(0.48, 0.45, 0.40)

    const scene = this.app.scene as unknown as Record<string, unknown>
    // Bumped exposure for more punch — scene read as muddy at 1.2.
    scene.exposure = 1.35

    // Fog (v2.17+: scene.fog is a read-only getter, set properties on it)
    const fog = (this.app.scene as unknown as { fog: Record<string, unknown> }).fog
    fog.type = pc.FOG_LINEAR
    fog.color = new pc.Color(0.75, 0.85, 0.95)
    fog.start = 150
    fog.end = 500

    this.app.scene.skyboxIntensity = 0.6

    // Generate procedural environment cubemap for IBL
    this.setupIBL()

    // Root entity
    this.root = new pc.Entity('EngineRoot')
    this.app.root.addChild(this.root)

    // Camera
    this.camera = new pc.Entity('Camera')
    this.camera.addComponent('camera', {
      clearColor: new pc.Color(0.53, 0.68, 0.85),
      projection: pc.PROJECTION_PERSPECTIVE,
      fov: 55,
      nearClip: 0.1,
      farClip: 1500,
      frustumCulling: true,
    })
    // v2.17+: toneMapping & gammaCorrection moved from Scene to CameraComponent
    const cam = this.camera.camera!
    ;(cam as unknown as Record<string, unknown>).toneMapping = pc.TONEMAP_ACES
    ;(cam as unknown as Record<string, unknown>).gammaCorrection = pc.GAMMA_SRGB
    // Initial position set by CameraController.init() via computeOrbitPosition()
    this.camera.setPosition(0, 100, 100)
    this.camera.lookAt(0, 0, 0)
    this.root.addChild(this.camera)

    // Sun — primary directional light. Warmer color + higher intensity
    // for golden-afternoon tone. Pairs with cool fill for temperature split.
    this.sun = new pc.Entity('Sun')
    this.sun.addComponent('light', {
      type: 'directional',
      color: new pc.Color(1.0, 0.90, 0.74),
      intensity: 2.1,
      castShadows: true,
      shadowBias: 0.05,
      normalOffsetBias: 0.05,
      // 1024 depth-map is 4× cheaper than 2048; orchard radius ~70u so a
      // 200u shadow frustum covers everything not already lost in fog (end=500u).
      shadowResolution: 1024,
      shadowDistance: 200,
      shadowType: pc.SHADOW_PCF3_32F,
    })
    this.sun.setEulerAngles(50, -30, 0)
    this.root.addChild(this.sun)

    // Cool fill light from opposite side (sky bounce). Slightly cooler +
    // brighter than before so shadow sides read as "sky-lit" rather than
    // "dark" — this is what gives pro scenes depth without flat shadows.
    const fillSky = new pc.Entity('FillSky')
    fillSky.addComponent('light', {
      type: 'directional',
      color: new pc.Color(0.55, 0.68, 0.92),
      intensity: 0.75,
      castShadows: false,
    })
    fillSky.setEulerAngles(-60, 45, 0)
    this.root.addChild(fillSky)

    // Frame update loop. Stored as `this.updateHandler` so `stopUpdates()`
    // can detach exactly this listener at teardown without sweeping every
    // other update listener registered against the PlayCanvas app.
    this.updateHandler = (dt: number) => {
      this.clock.update(dt)
      this.config.onUpdate?.(dt, this.clock)

      // Billboard labels: face camera (O(n) on registered set, not full scene).
      // The lookAt + rotateLocal pairing orients the Plane primitive so its
      // -Y normal faces the camera; the texture mirror-X scale on each label
      // compensates so text reads left-to-right in screen space. See
      // NameLabel / LevelBadge / LabelRenderer for the scale convention.
      // Dirty-flag: skip the loop entirely when the camera hasn't moved.
      // We deliberately orient disabled labels too — `lookAt` on a disabled
      // entity is pure transform math (PlayCanvas defers world-matrix calc
      // until render), and orienting them keeps the dirty-flag consistent
      // when a parent re-enables a label between camera moves.
      const camPos = this.camera.getPosition()
      if (!camPos.equalsApprox(this.lastBillboardCamPos, 1e-4)) {
        for (const label of this.billboards) {
          label.lookAt(camPos)
          label.rotateLocal(90, 0, 0)
        }
        this.lastBillboardCamPos.copy(camPos)
      }
    }
    this.app.on('update', this.updateHandler)

    this.app.start()
  }

  // ─── Billboard Registry ──────────────────────────────

  registerBillboard(entity: pc.Entity): void {
    this.billboards.add(entity)
    // Force the next frame's billboard pass to run so the new label gets
    // oriented even if the camera is sitting still (takeover seat, paused view).
    // Without this, freshly-spawned NPC nameplates appear edge-on until the
    // camera moves — the dirty-flag would otherwise skip the loop.
    this.lastBillboardCamPos.set(Infinity, Infinity, Infinity)
  }

  unregisterBillboard(entity: pc.Entity): void {
    this.billboards.delete(entity)
  }

  // ─── IBL Setup ───────────────────────────────────────

  /**
   * Generate a 128x128 procedural cubemap for Image-Based Lighting.
   *
   * This gives GLTF models an environment to reflect/shade against.
   * Without it, metallic/glossy materials appear black.
   *
   * Design: this cubemap serves as IBL only (for reflections + ambient shading).
   * The visible sky is rendered by SkySystem (Phase 2) using a shader on a dome,
   * which renders at full screen resolution and supports day/night transitions.
   */
  private setupIBL(): void {
    const size = 128
    const device = this.app.graphicsDevice

    const faces: Uint8Array[] = []
    for (let face = 0; face < 6; face++) {
      const data = new Uint8Array(size * size * 4)
      for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
          const idx = (y * size + x) * 4
          const dir = this.cubemapTexelDir(face, x, y, size)
          const height = dir[1]
          let r: number, g: number, b: number

          if (height >= 0) {
            const t = height
            r = lerp8(210, 102, t)
            g = lerp8(224, 153, t)
            b = lerp8(245, 235, t)
          } else {
            const t = Math.min(-height * 3, 1)
            r = lerp8(210, 90, t)
            g = lerp8(224, 140, t)
            b = lerp8(245, 72, t)
          }

          data[idx] = r
          data[idx + 1] = g
          data[idx + 2] = b
          data[idx + 3] = 255
        }
      }
      faces.push(data)
    }

    const cubemap = new pc.Texture(device, {
      width: size,
      height: size,
      format: pc.PIXELFORMAT_RGBA8,
      cubemap: true,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      levels: [faces],
    })

    // Set as scene skybox directly — don't use setSkybox(cubemap.impl) which is incorrect
    this.app.scene.skybox = cubemap
    this.app.scene.skyboxIntensity = 0.6
  }

  /**
   * Regenerate the IBL cubemap with new sky colors.
   * Called by SkySystem when time-of-day changes significantly.
   * Accepts a color function that maps a direction to RGB (0-255).
   */
  updateIBL(colorFn: (dir: [number, number, number]) => [number, number, number]): void {
    const size = 128
    const device = this.app.graphicsDevice

    const faces: Uint8Array[] = []
    for (let face = 0; face < 6; face++) {
      const data = new Uint8Array(size * size * 4)
      for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
          const idx = (y * size + x) * 4
          const dir = this.cubemapTexelDir(face, x, y, size)
          const [r, g, b] = colorFn(dir)
          data[idx] = r
          data[idx + 1] = g
          data[idx + 2] = b
          data[idx + 3] = 255
        }
      }
      faces.push(data)
    }

    const cubemap = new pc.Texture(device, {
      width: size,
      height: size,
      format: pc.PIXELFORMAT_RGBA8,
      cubemap: true,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      levels: [faces],
    })

    // Destroy old skybox texture before replacing
    const oldSkybox = this.app.scene.skybox
    this.app.scene.skybox = cubemap
    if (oldSkybox) oldSkybox.destroy()
  }

  /** Compute world-space direction for a cubemap face texel. */
  private cubemapTexelDir(face: number, x: number, y: number, size: number): [number, number, number] {
    const u = (2 * (x + 0.5)) / size - 1
    const v = (2 * (y + 0.5)) / size - 1
    let dx = 0, dy = 0, dz = 0

    switch (face) {
      case 0: dx = 1; dy = -v; dz = -u; break   // +X
      case 1: dx = -1; dy = -v; dz = u; break    // -X
      case 2: dx = u; dy = 1; dz = v; break      // +Y
      case 3: dx = u; dy = -1; dz = -v; break    // -Y
      case 4: dx = u; dy = -v; dz = 1; break     // +Z
      case 5: dx = -u; dy = -v; dz = -1; break   // -Z
    }

    const len = Math.sqrt(dx * dx + dy * dy + dz * dz)
    return [dx / len, dy / len, dz / len]
  }

  setConfig(config: ApplicationConfig): void {
    this.config = config
  }

  /**
   * Detach the per-frame update listener installed in `init()`. Idempotent.
   *
   * Used by `GardenEngine.destroy()` to halt our update logic *before* the
   * full PlayCanvas teardown — the destroy sequence frees graphics buffers
   * that the update path would otherwise touch on the next queued RAF tick,
   * producing the recurring `device` undefined console spam.
   *
   * Removes ONLY this Application's listener. Any other update listeners a
   * subsystem may have registered against `pc.Application` survive — the
   * earlier `app.off('update')` form removed everything by event name.
   */
  stopUpdates(): void {
    if (this.updateHandler) {
      this.app.off('update', this.updateHandler)
      this.updateHandler = null
    }
  }

  resize(width: number, height: number): void {
    this.app.resizeCanvas(width, height)
    this.events.emit('scene:resize', { width, height })
  }

  destroy(): void {
    this.events.emit('scene:destroy')
    this.events.clear()
    this.billboards.clear()
    this.stopUpdates()
    for (const cleanup of this.lifecycleCleanups) cleanup()
    this.lifecycleCleanups = []
    this.app.destroy()
  }
}

/** Lerp between two 0-255 byte values */
function lerp8(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t)
}
