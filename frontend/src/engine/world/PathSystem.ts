// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * PathSystem — Sandy paths with stone stepping connecting zone centers.
 *
 * Each route gets a sand-colored plane strip (soft-edged) underneath,
 * with path_stone GLBs placed on top at regular intervals.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { randRange } from '../utils/MathUtils'

const PATH_ASSET = 'assets/garden/path_stone.glb'
const STONE_SPACING = 1.8
const STONE_SCALE = 1.5
const SAND_WIDTH = 3.0   // width of the sandy strip in world units
const SAND_TEX_SIZE = 128

interface PathRoute {
  fromX: number
  fromZ: number
  toX: number
  toZ: number
}

export class PathSystem {
  private root: pc.Entity | null = null
  private sandTexture: pc.Texture | null = null
  private sandMaterial: pc.StandardMaterial | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    routes: PathRoute[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('PathSystem')

    // Create shared sand texture + material for all path strips
    this.sandTexture = this.createSandTexture(app.app.graphicsDevice)
    this.sandMaterial = new pc.StandardMaterial()
    this.sandMaterial.diffuseMap = this.sandTexture
    this.sandMaterial.diffuse = new pc.Color(1, 1, 1)
    this.sandMaterial.metalness = 0
    this.sandMaterial.gloss = 0.06
    this.sandMaterial.opacityMap = this.sandTexture
    this.sandMaterial.alphaTest = 0.01
    this.sandMaterial.blendType = pc.BLEND_NORMAL
    this.sandMaterial.depthWrite = false
    this.sandMaterial.cull = pc.CULLFACE_NONE
    this.sandMaterial.update()

    const asset = await loader.load(PATH_ASSET)

    for (const route of routes) {
      const dx = route.toX - route.fromX
      const dz = route.toZ - route.fromZ
      const dist = Math.sqrt(dx * dx + dz * dz)
      if (dist < 2) continue

      // Sand strip plane underneath the stones
      this.createSandStrip(route, dist, dx, dz)

      // Stepping stones on top
      const steps = Math.floor(dist / STONE_SPACING)
      if (steps < 2) continue

      const nx = dx / dist
      const nz = dz / dist
      const pathAngle = Math.atan2(nx, nz) * (180 / Math.PI)

      for (let i = 1; i < steps; i++) {
        const t = i / steps
        const sx = route.fromX + dx * t + randRange(-0.15, 0.15)
        const sz = route.fromZ + dz * t + randRange(-0.15, 0.15)

        const stone = loader.instance(asset)
        stone.setPosition(sx, 0.02, sz)
        stone.setLocalEulerAngles(0, pathAngle + randRange(-10, 10), 0)
        const s = STONE_SCALE + randRange(-0.2, 0.2)
        stone.setLocalScale(s, s, s)
        this.root.addChild(stone)
      }
    }

    app.root.addChild(this.root)
    return this.root
  }

  /** Create a sand-colored plane strip along a route. */
  private createSandStrip(
    route: PathRoute,
    dist: number,
    dx: number,
    dz: number,
  ): void {
    const midX = (route.fromX + route.toX) / 2
    const midZ = (route.fromZ + route.toZ) / 2
    const angle = Math.atan2(dx, dz) * (180 / Math.PI)

    const strip = new pc.Entity('SandStrip')
    strip.addComponent('render', { type: 'plane' })
    // Plane is XZ: scale X = width, Z = length
    strip.setLocalScale(SAND_WIDTH, 1, dist * 0.85) // 85% length to avoid poking into zone discs
    strip.setPosition(midX, 0.015, midZ) // just above ground
    strip.setLocalEulerAngles(0, angle, 0)
    strip.render!.meshInstances[0].material = this.sandMaterial!
    this.root!.addChild(strip)
  }

  /** Procedural sand texture with soft alpha edges. */
  private createSandTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = SAND_TEX_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!

    // Base sand color
    ctx.fillStyle = 'rgb(195, 175, 135)'
    ctx.fillRect(0, 0, S, S)

    // Noise patches for variation
    for (let i = 0; i < 40; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 5 + Math.random() * 20
      const dr = Math.floor((Math.random() - 0.5) * 30)
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${195 + dr}, ${175 + dr * 0.8}, ${135 + dr * 0.6}, 0.3)`
      ctx.fill()
    }

    // Small grain dots
    for (let i = 0; i < 300; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const dr = Math.floor((Math.random() - 0.5) * 40)
      ctx.fillStyle = `rgba(${195 + dr}, ${175 + dr * 0.8}, ${135 + dr * 0.6}, 0.2)`
      ctx.fillRect(x, y, 1 + Math.random(), 1 + Math.random())
    }

    // Apply soft alpha fade on the short edges (X direction = path width)
    const imageData = ctx.getImageData(0, 0, S, S)
    const data = imageData.data
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const edgeDist = Math.min(x, S - 1 - x) / (S / 2) // 0 at edges, 1 at center
        let alpha: number
        if (edgeDist < 0.3) {
          // Smooth cubic fade at edges
          const t = edgeDist / 0.3
          alpha = t * t * (3 - 2 * t)
        } else {
          alpha = 1.0
        }
        const idx = (y * S + x) * 4
        data[idx + 3] = Math.floor(data[idx + 3] * alpha)
      }
    }

    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_REPEAT,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 2,
    })

    const pixels = texture.lock()
    pixels.set(data)
    texture.unlock()

    return texture
  }

  /** Generate default routes from orchard center to each building zone. */
  static defaultRoutes(zones: Array<{ name: string; x: number; z: number }>): PathRoute[] {
    const routes: PathRoute[] = []
    const orchard = zones.find(z => z.name === 'orchard')
    if (!orchard) return routes

    for (const zone of zones) {
      if (zone.name === 'orchard') continue
      routes.push({
        fromX: orchard.x,
        fromZ: orchard.z,
        toX: zone.x,
        toZ: zone.z,
      })
    }

    return routes
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    if (this.sandTexture) {
      this.sandTexture.destroy()
      this.sandTexture = null
    }
    if (this.sandMaterial) {
      this.sandMaterial.destroy()
      this.sandMaterial = null
    }
  }
}
