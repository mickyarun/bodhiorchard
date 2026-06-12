// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * WaterSurface — Pool water with procedural caustic texture and edge walls.
 *
 * Creates a sunken pool effect: blue box walls form the pool basin,
 * and a translucent plane with an animated caustic-patterned texture
 * sits on top as the water surface. Gentle Y-bobbing simulates waves.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { Theme, toCss } from '../rendering/Theme'

/** Pool dimensions for water surface placement. */
export interface PoolBounds {
  x: number
  z: number
  width: number
  depth: number
}

const POOL_WALL_DEPTH = 1.5
const CAUSTIC_SIZE = 256

export class WaterSurface {
  private root: pc.Entity | null = null
  private surface: pc.Entity | null = null
  private time = 0
  private baseY = 0.15
  private causticTexture: pc.Texture | null = null
  private waterMaterial: pc.StandardMaterial | null = null
  private rimTexture: pc.Texture | null = null
  private rimMaterial: pc.StandardMaterial | null = null

  build(
    app: Application,
    _materials: MaterialFactory,
    pool: PoolBounds,
  ): pc.Entity {
    this.root = new pc.Entity('WaterSurface')
    this.root.setPosition(pool.x, 0, pool.z)

    // ─── Pool basin (sunken walls + floor) ───
    this.buildPoolBasin(pool)

    // ─── Water surface plane ───
    this.surface = new pc.Entity('WaterPlane')
    this.surface.addComponent('render', { type: 'plane' })
    this.surface.setLocalScale(pool.width, 1, pool.depth)
    this.surface.setLocalPosition(0, this.baseY, 0)

    // Generate caustic texture for shimmer
    this.causticTexture = this.createCausticTexture(app.app.graphicsDevice)

    this.waterMaterial = new pc.StandardMaterial()
    const [wr, wg, wb] = Theme.POOL.water
    const [er, eg, eb] = Theme.POOL.waterEmissive
    this.waterMaterial.diffuse = new pc.Color(wr, wg, wb)
    this.waterMaterial.emissive = new pc.Color(er, eg, eb)
    this.waterMaterial.opacity = Theme.POOL.waterOpacity
    this.waterMaterial.blendType = pc.BLEND_NORMAL
    this.waterMaterial.metalness = 0.15
    this.waterMaterial.gloss = 0.9
    this.waterMaterial.diffuseMap = this.causticTexture
    this.waterMaterial.diffuseMapTiling = new pc.Vec2(3, 3)
    this.waterMaterial.update()

    this.surface.render!.meshInstances[0].material = this.waterMaterial

    // Pale shallow band ringing the water's edge — the classic stylized
    // pool read (deep center, light rim). Child of the surface so it bobs
    // with the waves and inherits the pool footprint scale.
    this.rimTexture = this.createRimTexture(app.app.graphicsDevice)
    this.rimMaterial = new pc.StandardMaterial()
    this.rimMaterial.diffuse = new pc.Color(1, 1, 1)
    this.rimMaterial.diffuseMap = this.rimTexture
    this.rimMaterial.emissiveMap = this.rimTexture
    this.rimMaterial.emissive = new pc.Color(0.35, 0.35, 0.35)
    this.rimMaterial.opacityMap = this.rimTexture
    this.rimMaterial.blendType = pc.BLEND_NORMAL
    this.rimMaterial.depthWrite = false
    this.rimMaterial.cull = pc.CULLFACE_NONE
    this.rimMaterial.update()

    const rim = new pc.Entity('WaterRim')
    rim.addComponent('render', { type: 'plane' })
    rim.setLocalPosition(0, 0.004, 0)
    rim.render!.meshInstances[0].material = this.rimMaterial
    rim.render!.castShadows = false
    this.surface.addChild(rim)

    this.root.addChild(this.surface)
    app.root.addChild(this.root)
    return this.root
  }

  /** Rect ring: light aqua at the border fading to transparent inward. */
  private createRimTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = 256
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, S, S)

    const [rr, rg, rb] = Theme.POOL.rim
    const band = S * 0.16
    const img = ctx.createImageData(S, S)
    const d = img.data
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const edge = Math.min(x, y, S - 1 - x, S - 1 - y)
        // 1.0 at the border → 0 once `band` pixels in (smoothstep).
        const t = Math.min(edge / band, 1)
        const alpha = (1 - t * t * (3 - 2 * t)) * 0.75
        const idx = (y * S + x) * 4
        d[idx] = rr
        d[idx + 1] = rg
        d[idx + 2] = rb
        d[idx + 3] = Math.round(alpha * 255)
      }
    }
    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      mipmaps: true,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })
    const pixels = texture.lock()
    pixels.set(img.data)
    texture.unlock()
    return texture
  }

  /** Build pool walls and floor to create the sunken basin. */
  private buildPoolBasin(pool: PoolBounds): void {
    if (!this.root) return

    const hw = pool.width / 2
    const hd = pool.depth / 2
    const wallThickness = 0.3

    // Pool floor — light aqua tile so the basin reads "pool", not "void"
    const floorMat = new pc.StandardMaterial()
    const [fr, fg, fb] = Theme.POOL.basinFloor
    floorMat.diffuse = new pc.Color(fr, fg, fb)
    floorMat.metalness = 0
    floorMat.gloss = 0.3
    floorMat.update()

    const floor = new pc.Entity('PoolFloor')
    floor.addComponent('render', { type: 'box' })
    floor.setLocalScale(pool.width, 0.1, pool.depth)
    floor.setLocalPosition(0, -POOL_WALL_DEPTH, 0)
    floor.render!.meshInstances[0].material = floorMat
    this.root.addChild(floor)

    // Pool walls (light tile, a step brighter than the floor)
    const wallMat = new pc.StandardMaterial()
    const [lr, lg, lb] = Theme.POOL.basinWall
    wallMat.diffuse = new pc.Color(lr, lg, lb)
    wallMat.metalness = 0
    wallMat.gloss = 0.4
    wallMat.update()

    const wallDefs: Array<{ x: number; z: number; sx: number; sz: number }> = [
      { x: 0, z: -hd - wallThickness / 2, sx: pool.width + wallThickness * 2, sz: wallThickness },
      { x: 0, z: hd + wallThickness / 2, sx: pool.width + wallThickness * 2, sz: wallThickness },
      { x: -hw - wallThickness / 2, z: 0, sx: wallThickness, sz: pool.depth },
      { x: hw + wallThickness / 2, z: 0, sx: wallThickness, sz: pool.depth },
    ]

    for (const wd of wallDefs) {
      const wall = new pc.Entity('PoolWall')
      wall.addComponent('render', { type: 'box' })
      wall.setLocalScale(wd.sx, POOL_WALL_DEPTH + 0.3, wd.sz)
      wall.setLocalPosition(wd.x, -POOL_WALL_DEPTH / 2, wd.z)
      wall.render!.meshInstances[0].material = wallMat
      this.root.addChild(wall)
    }
  }

  /** Generate a caustic-like shimmer texture using Canvas2D. */
  private createCausticTexture(device: pc.GraphicsDevice): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = CAUSTIC_SIZE
    canvas.height = CAUSTIC_SIZE
    const ctx = canvas.getContext('2d')!

    // Bright tropical aqua base (Theme.POOL.causticBase)
    ctx.fillStyle = toCss(Theme.POOL.causticBase)
    ctx.fillRect(0, 0, CAUSTIC_SIZE, CAUSTIC_SIZE)

    // Caustic light lines (overlapping bright streaks)
    for (let i = 0; i < 120; i++) {
      const x1 = Math.random() * CAUSTIC_SIZE
      const y1 = Math.random() * CAUSTIC_SIZE
      const len = 15 + Math.random() * 40
      const angle = Math.random() * Math.PI * 2
      const x2 = x1 + Math.cos(angle) * len
      const y2 = y1 + Math.sin(angle) * len

      ctx.strokeStyle = `rgba(${120 + Math.random() * 80}, ${180 + Math.random() * 60}, ${200 + Math.random() * 55}, ${0.08 + Math.random() * 0.12})`
      ctx.lineWidth = 1 + Math.random() * 3
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.quadraticCurveTo(
        (x1 + x2) / 2 + (Math.random() - 0.5) * 20,
        (y1 + y2) / 2 + (Math.random() - 0.5) * 20,
        x2, y2,
      )
      ctx.stroke()
    }

    // Soft bright spots
    for (let i = 0; i < 60; i++) {
      const x = Math.random() * CAUSTIC_SIZE
      const y = Math.random() * CAUSTIC_SIZE
      const r = 5 + Math.random() * 15
      const grad = ctx.createRadialGradient(x, y, 0, x, y, r)
      grad.addColorStop(0, `rgba(160, 220, 240, ${0.1 + Math.random() * 0.1})`)
      grad.addColorStop(1, 'rgba(160, 220, 240, 0)')
      ctx.fillStyle = grad
      ctx.fillRect(x - r, y - r, r * 2, r * 2)
    }

    const texture = new pc.Texture(device, {
      width: CAUSTIC_SIZE,
      height: CAUSTIC_SIZE,
      format: pc.PIXELFORMAT_RGBA8,
      addressU: pc.ADDRESS_REPEAT,
      addressV: pc.ADDRESS_REPEAT,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 4,
    })

    const pixels = texture.lock()
    const imageData = ctx.getImageData(0, 0, CAUSTIC_SIZE, CAUSTIC_SIZE)
    pixels.set(imageData.data)
    texture.unlock()

    return texture
  }

  update(dt: number): void {
    if (!this.surface || !this.waterMaterial) return
    this.time += dt

    // Gentle wave bobbing
    const waveY = this.baseY + Math.sin(this.time * 1.2) * 0.06
    const pos = this.surface.getLocalPosition()
    this.surface.setLocalPosition(pos.x, waveY, pos.z)

    // Animate caustic texture offset for shimmer (faster than the old
    // 0.3/0.25 — the shimmer was too slow to register as "water").
    const offsetX = Math.sin(this.time * 0.55) * 0.1
    const offsetY = Math.cos(this.time * 0.45) * 0.08
    this.waterMaterial.diffuseMapOffset.set(offsetX, offsetY)
    this.waterMaterial.update()
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    this.surface = null
    if (this.causticTexture) {
      this.causticTexture.destroy()
      this.causticTexture = null
    }
    if (this.waterMaterial) {
      this.waterMaterial.destroy()
      this.waterMaterial = null
    }
    this.rimTexture?.destroy()
    this.rimTexture = null
    this.rimMaterial?.destroy()
    this.rimMaterial = null
  }
}
