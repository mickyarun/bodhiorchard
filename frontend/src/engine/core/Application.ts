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
   * Billboard registry — O(1) add/remove, avoids O(n) findByTag every frame.
   * Subsystems call registerBillboard/unregisterBillboard when creating/destroying labels.
   */
  private billboards = new Set<pc.Entity>()

  // Scratch vectors reused every frame by updateBillboards to avoid GC pressure.
  private readonly _bbCamPos = new pc.Vec3()
  private readonly _bbLabelPos = new pc.Vec3()
  private readonly _bbBasisX = new pc.Vec3()
  private readonly _bbBasisY = new pc.Vec3()
  private readonly _bbBasisZ = new pc.Vec3()
  private readonly _bbMat = new pc.Mat4()
  private readonly _bbRot = new pc.Quat()
  private static readonly BB_WORLD_UP = new pc.Vec3(0, 1, 0)

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
      },
    })

    this.app.setCanvasFillMode(pc.FILLMODE_NONE)
    this.app.setCanvasResolution(pc.RESOLUTION_AUTO)
    this.app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio, 2)
    this.app.resizeCanvas(width, height)

    // ─── Scene lighting: THE fix for black models ─────────────
    this.app.scene.ambientLight = new pc.Color(0.4, 0.4, 0.45)

    const scene = this.app.scene as unknown as Record<string, unknown>
    scene.exposure = 1.2

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

    // Sun — primary directional light
    this.sun = new pc.Entity('Sun')
    this.sun.addComponent('light', {
      type: 'directional',
      color: new pc.Color(1, 0.97, 0.9),
      intensity: 1.8,
      castShadows: true,
      shadowBias: 0.05,
      normalOffsetBias: 0.05,
      shadowResolution: 2048,
      shadowDistance: 500,
    })
    this.sun.setEulerAngles(50, -30, 0)
    this.root.addChild(this.sun)

    // Fill light from opposite side (sky bounce)
    const fillSky = new pc.Entity('FillSky')
    fillSky.addComponent('light', {
      type: 'directional',
      color: new pc.Color(0.6, 0.7, 0.9),
      intensity: 0.6,
      castShadows: false,
    })
    fillSky.setEulerAngles(-60, 45, 0)
    this.root.addChild(fillSky)

    // Frame update loop
    this.app.on('update', (dt: number) => {
      this.clock.update(dt)
      this.config.onUpdate?.(dt, this.clock)

      // Billboard labels: orient each plane so its front face (+Y normal)
      // points at the camera, local +X aligns with screen-right, and
      // local +Z aligns with screen-up. Texture U increases in local +X,
      // so canvas text drawn left-to-right renders left-to-right in
      // screen space — no mirror-scale trick needed. setRotation takes a
      // world-space quaternion and is parent-aware, so this works
      // regardless of where in the scene graph the label is parented.
      this.updateBillboards()
    })

    this.app.start()
  }

  // ─── Billboard Registry ──────────────────────────────

  registerBillboard(entity: pc.Entity): void {
    this.billboards.add(entity)
  }

  unregisterBillboard(entity: pc.Entity): void {
    this.billboards.delete(entity)
  }

  /**
   * Orient every registered label plane so its front face points at the
   * camera. Builds a right-handed basis per label:
   *   +Y (plane normal) → from label toward camera
   *   +X               → screen-right (perpendicular to world-up and +Y)
   *   +Z               → screen-up (cross of +X and +Y)
   *
   * Text drawn left-to-right on the label's canvas (U=0 on left) renders
   * left-to-right in screen space because +X aligns with screen-right —
   * no geometry mirror-scale, no CULLFACE_NONE back-face fallback.
   *
   * Near-singular case (camera directly above a label) uses world +X as
   * the fallback right vector; the text stays readable from any azimuth.
   */
  private updateBillboards(): void {
    if (this.billboards.size === 0) return

    this._bbCamPos.copy(this.camera.getPosition())
    const EPSILON = 1e-4

    for (const label of this.billboards) {
      if (!label.enabled) continue

      this._bbLabelPos.copy(label.getPosition())
      // basisY = direction from label to camera (plane normal)
      this._bbBasisY.sub2(this._bbCamPos, this._bbLabelPos)
      const len = this._bbBasisY.length()
      if (len < EPSILON) continue
      this._bbBasisY.mulScalar(1 / len)

      // basisX = cross(worldUp, basisY), normalised. Falls back to world +X
      // if the camera is exactly above the label (cross product degenerate).
      this._bbBasisX.cross(Application.BB_WORLD_UP, this._bbBasisY)
      if (this._bbBasisX.lengthSq() < EPSILON) {
        this._bbBasisX.set(1, 0, 0)
      } else {
        this._bbBasisX.normalize()
      }

      // basisZ completes the right-handed frame.
      this._bbBasisZ.cross(this._bbBasisX, this._bbBasisY)

      // Build a rotation matrix directly from the three basis vectors.
      // pc.Mat4.data is column-major: columns are [X | Y | Z | translation].
      const d = this._bbMat.data
      d[0]  = this._bbBasisX.x; d[1]  = this._bbBasisX.y; d[2]  = this._bbBasisX.z; d[3]  = 0
      d[4]  = this._bbBasisY.x; d[5]  = this._bbBasisY.y; d[6]  = this._bbBasisY.z; d[7]  = 0
      d[8]  = this._bbBasisZ.x; d[9]  = this._bbBasisZ.y; d[10] = this._bbBasisZ.z; d[11] = 0
      d[12] = 0;                d[13] = 0;                d[14] = 0;                d[15] = 1

      this._bbRot.setFromMat4(this._bbMat)
      label.setRotation(this._bbRot)
    }
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

  resize(width: number, height: number): void {
    this.app.resizeCanvas(width, height)
    this.events.emit('scene:resize', { width, height })
  }

  destroy(): void {
    this.events.emit('scene:destroy')
    this.events.clear()
    this.billboards.clear()
    this.app.destroy()
  }
}

/** Lerp between two 0-255 byte values */
function lerp8(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t)
}
