// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
    this.waterMaterial.diffuse = new pc.Color(0.15, 0.55, 0.9)
    this.waterMaterial.emissive = new pc.Color(0.1, 0.35, 0.55)
    this.waterMaterial.opacity = 0.7
    this.waterMaterial.blendType = pc.BLEND_NORMAL
    this.waterMaterial.metalness = 0.15
    this.waterMaterial.gloss = 0.9
    this.waterMaterial.diffuseMap = this.causticTexture
    this.waterMaterial.diffuseMapTiling = new pc.Vec2(3, 3)
    this.waterMaterial.update()

    this.surface.render!.meshInstances[0].material = this.waterMaterial

    this.root.addChild(this.surface)
    app.root.addChild(this.root)
    return this.root
  }

  /** Build pool walls and floor to create the sunken basin. */
  private buildPoolBasin(pool: PoolBounds): void {
    if (!this.root) return

    const hw = pool.width / 2
    const hd = pool.depth / 2
    const wallThickness = 0.3

    // Pool floor (dark blue)
    const floorMat = new pc.StandardMaterial()
    floorMat.diffuse = new pc.Color(0.08, 0.15, 0.35)
    floorMat.metalness = 0
    floorMat.gloss = 0.3
    floorMat.update()

    const floor = new pc.Entity('PoolFloor')
    floor.addComponent('render', { type: 'box' })
    floor.setLocalScale(pool.width, 0.1, pool.depth)
    floor.setLocalPosition(0, -POOL_WALL_DEPTH, 0)
    floor.render!.meshInstances[0].material = floorMat
    this.root.addChild(floor)

    // Pool walls (medium blue tiles)
    const wallMat = new pc.StandardMaterial()
    wallMat.diffuse = new pc.Color(0.12, 0.25, 0.5)
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

    // Deep pool base color
    ctx.fillStyle = 'rgb(30, 90, 110)'
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

    // Animate caustic texture offset for shimmer
    const offsetX = Math.sin(this.time * 0.3) * 0.1
    const offsetY = Math.cos(this.time * 0.25) * 0.08
    this.waterMaterial.diffuseMapOffset = new pc.Vec2(offsetX, offsetY)
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
  }
}
