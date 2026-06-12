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
 * GrassSystem — lush procedural grass tufts + GLB flower accents.
 *
 * Grass is NOT a GLB: each tuft is three crossed alpha-tested quads
 * sharing a painted blade texture (deep-green roots → vibrant tips).
 * Crossed quads read as volume from every camera angle, take the
 * GrassWind transformVS sway (height² — roots anchored, tips travel),
 * and the whole field renders as ONE instanced draw call.
 *
 * Flowers stay GLB scatter (Kenney, instanced per asset) — they're the
 * color accents between tufts.
 *
 * Placement: Poisson-ish rejection scatter, skipping exclusion zones.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_FLOWERS } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'
import {
  buildInstancedGlbs, type GlbScatterGroup, type ScatterTransform,
} from '../utils/GlbInstancing'
import { createInstancedEntity, computeInstanceAabb } from '../treetest/instancing'
import { Theme, toCss } from '../rendering/Theme'
import { GrassWind } from '../effects/GrassWind'

const GRASS_COUNT = 700
const FLOWER_COUNT = 40
const WORLD_HALF = 40 // compact world with TILE_SIZE=1
const MIN_DISTANCE = 1.1 // tighter spacing for lush coverage
const BLADE_TEX_SIZE = 128
/** Tuft footprint in mesh units — instance scale multiplies this. */
const TUFT_WIDTH = 0.9
const TUFT_HEIGHT = 0.65

export class GrassSystem {
  private root: pc.Entity | null = null
  private vbs: pc.VertexBuffer[] = []
  private materials: pc.Material[] = []
  private tuftMesh: pc.Mesh | null = null
  private bladeTexture: pc.Texture | null = null
  private wind = new GrassWind()

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('GrassSystem')
    const device = app.app.graphicsDevice

    // ─── Lush tufts: one instanced batch of crossed alpha quads ───
    const points = this.poissonScatter(GRASS_COUNT, WORLD_HALF, MIN_DISTANCE, exclusionZones)
    if (points.length > 0) {
      this.tuftMesh = this.buildTuftMesh(device)
      this.bladeTexture = this.buildBladeTexture(device)
      const tuftMat = this.buildTuftMaterial(this.bladeTexture)
      this.materials.push(tuftMat)
      this.wind.apply([tuftMat], Theme.SCATTER.grassWindStrength)

      const matrices = new Float32Array(points.length * 16)
      const mat = new pc.Mat4()
      const pos = new pc.Vec3()
      const rot = new pc.Quat()
      const scl = new pc.Vec3()
      for (let i = 0; i < points.length; i++) {
        const p = points[i]
        pos.set(p.x, 0, p.z)
        rot.setFromEulerAngles(0, randRange(0, 360), 0)
        const s = randRange(0.7, 1.45)
        scl.set(s, s * randRange(0.85, 1.25), s)
        mat.setTRS(pos, rot, scl)
        matrices.set(mat.data, i * 16)
      }
      const aabb = computeInstanceAabb(matrices, points.length, TUFT_HEIGHT * 2)
      const { entity, vb } = createInstancedEntity(
        device, this.tuftMesh, tuftMat, matrices, points.length,
        'GrassTufts', { aabb },
      )
      this.root.addChild(entity)
      this.vbs.push(vb)
    }

    // ─── Flower accents: GLB scatter, instanced per asset ───
    const flowerAssets = await loader.loadBatch(SCATTER_FLOWERS)
    const flowerGroups: GlbScatterGroup[] = flowerAssets.map(
      (asset) => ({ asset, transforms: [] }),
    )
    for (const pt of this.poissonScatter(FLOWER_COUNT, WORLD_HALF, 3, exclusionZones)) {
      const transform: ScatterTransform = {
        x: pt.x, y: 0, z: pt.z,
        yawDeg: randRange(0, 360),
        scale:  randRange(2.5, 5.5),
      }
      flowerGroups[Math.floor(Math.random() * flowerGroups.length)].transforms.push(transform)
    }
    const flowers = buildInstancedGlbs(
      device, loader, flowerGroups, { namePrefix: 'FlowerInstanced' },
    )
    for (const e of flowers.entities) this.root.addChild(e)
    this.vbs.push(...flowers.vbs)
    this.materials.push(...flowers.materials)

    app.root.addChild(this.root)
    return this.root
  }

  /** Advance the wind clock — call once per frame. */
  update(dt: number): void {
    this.wind.update(dt)
  }

  /** Three quads crossed at 60° around Y, base at y=0, tip at TUFT_HEIGHT. */
  private buildTuftMesh(device: pc.GraphicsDevice): pc.Mesh {
    const positions: number[] = []
    const normals: number[] = []
    const uvs: number[] = []
    const indices: number[] = []
    const hw = TUFT_WIDTH / 2
    const h = TUFT_HEIGHT

    for (let q = 0; q < 3; q++) {
      const a = (q * Math.PI) / 3
      const dx = Math.cos(a) * hw
      const dz = Math.sin(a) * hw
      const base = q * 4
      positions.push(
        -dx, 0, -dz,   dx, 0, dz,
         dx, h, dz,   -dx, h, -dz,
      )
      // Up-biased normals make the lighting read like a ground covering
      // rather than vertical billboards catching side light.
      for (let v = 0; v < 4; v++) normals.push(0, 1, 0)
      uvs.push(0, 0, 1, 0, 1, 1, 0, 1)
      indices.push(base, base + 1, base + 2, base, base + 2, base + 3)
    }

    const geometry = new pc.Geometry()
    geometry.positions = positions
    geometry.normals = normals
    geometry.uvs = uvs
    geometry.indices = indices
    return pc.Mesh.fromGeometry(device, geometry)
  }

  /** Painted blade silhouettes: deep-green roots fading to vibrant tips. */
  private buildBladeTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = BLADE_TEX_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, S, S)

    const root = Theme.GRASS_BLADES.root
    const tip = Theme.GRASS_BLADES.tip
    const bladeCount = 11
    for (let b = 0; b < bladeCount; b++) {
      const cx = (b + 0.5) * (S / bladeCount) + randRange(-3, 3)
      const w = S / bladeCount * randRange(0.5, 0.85)
      const height = S * randRange(0.55, 0.98)
      const lean = randRange(-S * 0.08, S * 0.08)

      const grad = ctx.createLinearGradient(0, S, 0, S - height)
      grad.addColorStop(0, toCss(root))
      grad.addColorStop(1, toCss(tip))
      ctx.fillStyle = grad
      // Tapered blade: wide base → pointed tip, slight lean.
      ctx.beginPath()
      ctx.moveTo(cx - w / 2, S)
      ctx.quadraticCurveTo(cx - w / 2 + lean * 0.4, S - height * 0.6, cx + lean, S - height)
      ctx.quadraticCurveTo(cx + w / 2 + lean * 0.4, S - height * 0.6, cx + w / 2, S)
      ctx.closePath()
      ctx.fill()
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
      anisotropy: 4,
    })
    const pixels = texture.lock()
    pixels.set(ctx.getImageData(0, 0, S, S).data)
    texture.unlock()
    return texture
  }

  private buildTuftMaterial(texture: pc.Texture): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuseMap = texture
    mat.opacityMap = texture
    mat.opacityMapChannel = 'a'
    mat.alphaTest = 0.45
    mat.cull = pc.CULLFACE_NONE
    mat.twoSidedLighting = true
    mat.metalness = 0
    mat.gloss = 0.1
    mat.update()
    return mat
  }

  /**
   * Simple Poisson-ish scatter: random rejection with minimum distance.
   * Not a true Poisson disc sample, but fast enough for decorative placement.
   */
  private poissonScatter(
    count: number,
    halfExtent: number,
    minDist: number,
    exclusionZones: readonly ExclusionZone[],
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 10
    let attempts = 0

    while (points.length < count && attempts < maxAttempts) {
      attempts++
      const x = randRange(-halfExtent, halfExtent)
      const z = randRange(-halfExtent, halfExtent)

      if (isInsideAnyZone(x, z, exclusionZones as ExclusionZone[])) continue

      let tooClose = false
      const checkCount = Math.min(points.length, 20)
      for (let i = points.length - checkCount; i < points.length; i++) {
        const dx = x - points[i].x
        const dz = z - points[i].z
        if (dx * dx + dz * dz < minDist * minDist) {
          tooClose = true
          break
        }
      }
      if (tooClose) continue

      points.push({ x, z })
    }

    return points
  }

  destroy(): void {
    this.wind.clear()
    for (const vb of this.vbs) vb.destroy()
    this.vbs = []
    for (const mat of this.materials) mat.destroy()
    this.materials = []
    if (this.tuftMesh) {
      this.tuftMesh.vertexBuffer?.destroy()
      this.tuftMesh.indexBuffer?.[0]?.destroy()
      this.tuftMesh = null
    }
    this.bladeTexture?.destroy()
    this.bladeTexture = null
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
